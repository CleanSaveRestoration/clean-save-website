#!/usr/bin/env python3
"""Clean Save WA claim-deadline checker.

Reads one or more job JSON files (the same NNN_TYPE_Lastname.json the
/new-job skill creates) and flags:
  - CARRIER OVERDUE   a WA deadline the insurer missed (leverage for us)
  - CLEAN SAVE ACTION something we must do to stay compliant / protected
  - DUE SOON          a deadline landing within the warning window

Usage:
  python claim_compliance_check.py JOB.json [JOB2.json ...]
  python claim_compliance_check.py --jobs-dir "01_Customer_Jobs"
  python claim_compliance_check.py --jobs-dir ... --today 2026-11-20 --md report.md

Rules and citations live in wa-claims-rules.json next to this file.
Standard library only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RULES_PATH = os.path.join(HERE, "wa-claims-rules.json")
CHANGE_DATE = dt.date(2026, 10, 18)
WARN_DAYS = 2  # business days of warning before a deadline

# --------------------------------------------------------------------------
# Dates
# --------------------------------------------------------------------------

def _d(value):
    if not value:
        return None
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(str(value)[:10])


def _nth_weekday(year, month, weekday, n):
    d = dt.date(year, month, 1)
    d += dt.timedelta(days=(weekday - d.weekday()) % 7)
    return d + dt.timedelta(weeks=n - 1)


def _last_weekday(year, month, weekday):
    d = dt.date(year, month + 1, 1) - dt.timedelta(days=1) if month < 12 else dt.date(year, 12, 31)
    return d - dt.timedelta(days=(d.weekday() - weekday) % 7)


def _observed(d):
    if d.weekday() == 5:
        return d - dt.timedelta(days=1)
    if d.weekday() == 6:
        return d + dt.timedelta(days=1)
    return d


_HOLIDAY_CACHE: dict[int, set] = {}


def wa_holidays(year):
    """Washington state legal holidays (RCW 1.16.050), with weekend observance."""
    if year in _HOLIDAY_CACHE:
        return _HOLIDAY_CACHE[year]
    thanksgiving = _nth_weekday(year, 11, 3, 4)
    days = {
        _observed(dt.date(year, 1, 1)),
        _nth_weekday(year, 1, 0, 3),       # MLK Day
        _nth_weekday(year, 2, 0, 3),       # Presidents' Day
        _last_weekday(year, 5, 0),         # Memorial Day
        _observed(dt.date(year, 6, 19)),   # Juneteenth
        _observed(dt.date(year, 7, 4)),
        _nth_weekday(year, 9, 0, 1),       # Labor Day
        _observed(dt.date(year, 11, 11)),  # Veterans Day
        thanksgiving,
        thanksgiving + dt.timedelta(days=1),  # Native American Heritage Day
        _observed(dt.date(year, 12, 25)),
    }
    _HOLIDAY_CACHE[year] = days
    return days


def is_business_day(d):
    return d.weekday() < 5 and d not in wa_holidays(d.year)


def add_days(start, n, kind):
    if kind == "calendar":
        return start + dt.timedelta(days=n)
    d = start
    added = 0
    while added < n:
        d += dt.timedelta(days=1)
        if is_business_day(d):
            added += 1
    return d


def business_days_between(a, b):
    """Business days after a, up to and including b (0 if b <= a)."""
    if b <= a:
        return 0
    n, d = 0, a
    while d < b:
        d += dt.timedelta(days=1)
        if is_business_day(d):
            n += 1
    return n

# --------------------------------------------------------------------------
# Findings
# --------------------------------------------------------------------------

OVERDUE, ACTION, SOON = "CARRIER OVERDUE", "CLEAN SAVE ACTION", "DUE SOON"
ORDER = {ACTION: 0, OVERDUE: 1, SOON: 2}


class Checker:
    def __init__(self, rules, today):
        self.rules = {r["id"]: r for r in rules["rules"]}
        self.today = today

    def finding(self, level, rule_id, detail, due=None):
        r = self.rules[rule_id]
        return {
            "level": level,
            "rule": rule_id,
            "title": r["title"],
            "citation": r["citation"],
            "verified": r.get("verified", False),
            "detail": detail,
            "due": due.isoformat() if due else None,
            "action": r["action"],
        }

    def deadline(self, rule_id, start, done, label):
        """Generic clock check. Returns a finding or None."""
        if not start:
            return None
        spec = self.rules[rule_id]["deadline"]
        due = add_days(start, spec["days"], spec["type"])
        if done:
            if done > due:
                return self.finding(OVERDUE, rule_id,
                                    f"{label}: answered {done} but was due {due} (late).", due)
            return None
        if self.today > due:
            late = (self.today - due).days
            return self.finding(OVERDUE, rule_id,
                                f"{label}: due {due}, still open ({late} calendar days late).", due)
        if business_days_between(self.today, due) <= WARN_DAYS:
            return self.finding(SOON, rule_id, f"{label}: due {due}.", due)
        return None

    def check_job(self, job):
        out = []
        billing = str(job.get("billing_mode", job.get("billing", "insurance"))).lower()
        claim = job.get("claim")
        if "direct" in billing:
            return out
        if not claim:
            out.append(self.finding(ACTION, "CS-COMMS-LOGGED",
                                    "Insurance job has no 'claim' block. Add carrier, claim number, "
                                    "reported date and a communications log."))
            return out

        reported = _d(claim.get("reported_date"))
        start = _d(job.get("start_date") or job.get("date_of_inspection") or job.get("inspection_date"))

        # Carrier clocks
        f = self.deadline("WA-ACK-10", reported, _d(claim.get("acknowledged_date")), "Claim acknowledgment")
        if f: out.append(f)

        for c in claim.get("communications", []):
            if c.get("direction") == "out" and c.get("response_expected"):
                f = self.deadline("WA-REPLY-10", _d(c.get("date")), _d(c.get("response_date")),
                                  f"Reply to '{c.get('subject', 'message')}' sent {c.get('date')}")
                if f: out.append(f)

        scope = claim.get("mitigation_scope_sent") or {}
        resp = claim.get("mitigation_scope_response") or {}
        scope_date = _d(scope.get("date"))
        if scope_date and (scope_date >= CHANGE_DATE or (reported and reported >= CHANGE_DATE)):
            f = self.deadline("WA-MIT-SCOPE-5", scope_date, _d(resp.get("date")),
                              "Mitigation scope approval")
            if f: out.append(f)
        if resp.get("result") in ("rejected", "partial"):
            missing = [k for k, lbl in (("reason_given", "written reason"),
                                         ("itemized_disallowed", "itemized disallowed amounts"))
                       if not resp.get(k)]
            if missing:
                out.append(self.finding(OVERDUE, "WA-MIT-REJECT-ITEMIZED",
                                        f"Scope {resp['result']} without: {', '.join(missing)}."))

        decision = _d(claim.get("decision_date"))
        if reported:
            notices = sorted(_d(n) for n in claim.get("status_notices", []) if n)
            inv_due = add_days(reported, 30, "calendar")
            if not decision and self.today > inv_due and not any(n <= self.today for n in notices):
                out.append(self.finding(OVERDUE, "WA-INVESTIGATE-30",
                                        f"Day 30 was {inv_due}; no decision and no written status notice.",
                                        inv_due))
            if reported >= CHANGE_DATE:
                f = self.deadline("WA-DECIDE-30", reported, decision, "Accept/deny decision")
                if f: out.append(f)
            else:
                f = self.deadline("WA-DECIDE-15-LEGACY", _d(claim.get("proof_of_loss_date")),
                                  decision, "Accept/deny after proof of loss")
                if f: out.append(f)

        if claim.get("decision") in ("denied", "partial"):
            if not (claim.get("denial_in_writing") and claim.get("policy_provision_cited")):
                out.append(self.finding(OVERDUE, "WA-DENIAL-WRITTEN",
                                        f"Decision '{claim['decision']}' lacks a written denial citing the policy."))

        f = self.deadline("WA-FILE-15", _d(claim.get("claim_file_requested")),
                          _d(claim.get("claim_file_received")), "Claim file request")
        if f: out.append(f)
        if claim.get("claim_file_received") and claim.get("withheld_items_disclosed") is False:
            out.append(self.finding(OVERDUE, "WA-FILE-15", "Claim file arrived but withheld items were not disclosed."))

        f = self.deadline("WA-PRICING-SOURCE", _d(claim.get("pricing_data_requested")),
                          _d(claim.get("pricing_data_received")), "Pricing source data request")
        if f: out.append(f)
        if claim.get("carrier_cut_by_price_list") and not claim.get("pricing_data_requested"):
            out.append(self.finding(ACTION, "WA-PRICING-SOURCE",
                                    "Carrier cut pricing by price list/software and we have not asked for its source data."))

        # Clean Save's own obligations
        if start and not scope_date:
            due = add_days(start, 1, "business")
            level = ACTION if self.today > due else SOON
            out.append(self.finding(level, "CS-SCOPE-WRITTEN-DAY1",
                                    f"Job started {start}; no written mitigation scope sent to the carrier "
                                    f"(target {due}). The 5-day approval clock has not started.", due))
        elif start and scope_date:
            due = add_days(start, 1, "business")
            if scope_date > due:
                out.append(self.finding(ACTION, "CS-SCOPE-WRITTEN-DAY1",
                                        f"Scope sent {scope_date}, later than the next-business-day target {due}."))

        comms = claim.get("communications", [])
        if not comms:
            out.append(self.finding(ACTION, "CS-COMMS-LOGGED", "No carrier communications logged."))
        else:
            bad = [c for c in comms if not c.get("date") or not c.get("contact")]
            if bad:
                out.append(self.finding(ACTION, "CS-COMMS-LOGGED",
                                        f"{len(bad)} communication entries missing a date or contact name."))

        perm = _d(claim.get("permanent_work_started"))
        if perm:
            insp = _d(claim.get("carrier_inspection_date"))
            approved = claim.get("permanent_repair_approval_written")
            if not approved and (not insp or insp > perm):
                out.append(self.finding(ACTION, "CS-NO-PERMANENT-BEFORE-INSPECTION",
                                        f"Permanent work started {perm} before carrier inspection "
                                        f"({insp or 'none logged'}) with no written approval on file."))

        out.sort(key=lambda x: (ORDER[x["level"]], x["due"] or "9999"))
        return out


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def job_label(job, path):
    return job.get("job") or job.get("job_number") or job.get("estimate_number") or os.path.basename(path)


def find_jobs(jobs_dir):
    paths = []
    for p in sorted(glob.glob(os.path.join(jobs_dir, "*", "*.json"))):
        name = os.path.basename(p)
        if name in ("field_log.json",) or name.startswith("_"):
            continue
        paths.append(p)
    return paths


def render_md(results, today):
    lines = [f"# WA claim compliance check, {today}", ""]
    totals = {ACTION: 0, OVERDUE: 0, SOON: 0}
    for _, _, fs in results:
        for f in fs:
            totals[f["level"]] += 1
    lines.append(f"**{totals[ACTION]}** Clean Save actions, **{totals[OVERDUE]}** carrier overdue, "
                 f"**{totals[SOON]}** due soon.")
    lines.append("")
    lines.append("Rules marked (unverified) come from the United Policyholders summary of the "
                 "2026-10-18 changes. Confirm against WAC 284-30 before citing to a carrier.")
    for label, path, fs in results:
        lines += ["", f"## {label}", ""]
        if not fs:
            lines.append("No issues.")
            continue
        for f in fs:
            v = "" if f["verified"] else " (unverified)"
            due = f" Due {f['due']}." if f["due"] else ""
            lines.append(f"- **{f['level']}** [{f['rule']}] {f['title']}, {f['citation']}{v}.{due}")
            lines.append(f"  - {f['detail']}")
            lines.append(f"  - Do: {f['action']}")
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("jobs", nargs="*", help="Job JSON files")
    ap.add_argument("--jobs-dir", help="Folder of job folders (01_Customer_Jobs)")
    ap.add_argument("--today", help="Override today's date (YYYY-MM-DD)")
    ap.add_argument("--md", help="Also write a Markdown report here")
    ap.add_argument("--json", action="store_true", help="Print findings as JSON")
    args = ap.parse_args(argv)

    today = _d(args.today) if args.today else dt.date.today()
    with open(RULES_PATH) as fh:
        checker = Checker(json.load(fh), today)

    paths = list(args.jobs)
    if args.jobs_dir:
        paths += find_jobs(args.jobs_dir)
    if not paths:
        ap.error("give job JSON files or --jobs-dir")

    results = []
    for p in paths:
        with open(p) as fh:
            job = json.load(fh)
        results.append((job_label(job, p), p, checker.check_job(job)))

    if args.json:
        print(json.dumps([{"job": l, "path": p, "findings": f} for l, p, f in results], indent=2))
    else:
        print(render_md(results, today))
    if args.md:
        with open(args.md, "w") as fh:
            fh.write(render_md(results, today))
    worst = any(f["level"] == ACTION for _, _, fs in results for f in fs)
    return 1 if worst else 0


if __name__ == "__main__":
    sys.exit(main())
