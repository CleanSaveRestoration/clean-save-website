# WA claim compliance: rules, catches, templates

This folder tracks Washington's insurance claim-handling deadlines (WAC 284-30, including the changes United Policyholders reports as effective 2026-10-18). It flags jobs where the carrier is late and where Clean Save hasn't done its part.

> **Verify first.** The 2026-10-18 rules come from a United Policyholders summary (updated September 2026), not from the adopted WAC text. Each rule in `wa-claims-rules.json` has `"verified": false` until someone checks it against https://apps.leg.wa.gov/wac/default.aspx?cite=284-30 or OIC public notices. Don't quote an unverified citation to a carrier.

## Files

| File | What it is |
|------|------------|
| `wa-claims-rules.json` | The rules database: ID, owner (carrier or Clean Save), citation, clock start, deadline, the catch, the action |
| `claim_compliance_check.py` | Checker. Reads job JSON files and reports findings. Standard-library Python only. |
| `templates/` | Mitigation scope follow-up (we send), pricing data request and claim file request (homeowner sends) |
| `examples/` | Two fictional test jobs: one with problems, one clean |

## Run it

```bash
# every job in the OneDrive jobs folder
python compliance/claim_compliance_check.py --jobs-dir "01_Customer_Jobs" --md Compliance_Report.md

# one job
python compliance/claim_compliance_check.py "01_Customer_Jobs/033_WTR_Smith/033_WTR_Smith.json"
```

The exit code is 1 when any CLEAN SAVE ACTION finding exists. Direct-pay jobs are skipped.

Finding levels:
- **CLEAN SAVE ACTION**: something we need to fix. Fix these first.
- **CARRIER OVERDUE**: the insurer missed a WA deadline. This is leverage for follow-ups and supplements.
- **DUE SOON**: a deadline lands within 2 business days.

Business days skip weekends and Washington state legal holidays (RCW 1.16.050), including the day after Thanksgiving.

## Fields to add to each job JSON

Add a `claim` block to `NNN_TYPE_Lastname.json`. Unknown values stay `null`.

```json
"billing_mode": "insurance",
"start_date": "2026-11-03",
"claim": {
  "carrier": "", "claim_number": "", "adjuster": "",
  "reported_date": null,
  "acknowledged_date": null,
  "proof_of_loss_date": null,
  "mitigation_scope_sent": {"date": null, "method": "email", "to": ""},
  "mitigation_scope_response": {"date": null, "result": null, "reason_given": null, "itemized_disallowed": null},
  "decision_date": null, "decision": null,
  "denial_in_writing": null, "policy_provision_cited": null,
  "status_notices": [],
  "claim_file_requested": null, "claim_file_received": null, "withheld_items_disclosed": null,
  "carrier_cut_by_price_list": false,
  "pricing_data_requested": null, "pricing_data_received": null,
  "carrier_inspection_date": null,
  "permanent_work_started": null, "permanent_repair_approval_written": null,
  "communications": [
    {"date": null, "direction": "out", "contact": "", "method": "email",
     "subject": "", "response_expected": true, "response_date": null}
  ]
}
```

`mitigation_scope_response.result` is one of `approved`, `partial`, `rejected`, or `insurer_scope`. `decision` is one of `accepted`, `partial`, or `denied`.

## Hooking into the cleansave-ops skills

These edits belong in the `cleansave-ops` plugin, which this repository doesn't contain:

- **/new-job**: for insurance jobs, create the `claim` block. Record `reported_date` (ask the homeowner when they called the carrier).
- **/log-day**: on Day 1, ask whether the written mitigation scope went to the adjuster, and log the date. Every day, log carrier contacts into `claim.communications` and run the checker for the job. Report any findings with the day's summary.
- **/supplement**: before building, check `mitigation_scope_response.itemized_disallowed`, `denial_in_writing` and `claim_file_received`. If one is missing, request it first (templates). Add the WAC citations to the escalation ladder.
- **/close-job**: run the checker. Any open CLEAN SAVE ACTION is a gap to report.

## Rule we hold ourselves to: no unlicensed adjusting

Rule `CS-NO-UNLICENSED-ADJUSTING`: Clean Save documents its work, sends its scope and invoices, and follows up on its own scope and pricing. We don't negotiate coverage or settlement for the homeowner. Letters that invoke a policyholder right (claim file, pricing data, denial reasons) are sent or signed by the homeowner. Website copy says we "document" and "help you understand"; it doesn't say we "handle your claim". Confirm the exact limits under RCW 48.17 with counsel.
