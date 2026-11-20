# cleansave-ops patch: WA claim-deadline compliance (v0.6.0)

Paste each block into the named SKILL.md at the location shown, then bump `.claude-plugin/plugin.json` version to `0.6.0`.

All blocks assume the checker and rules from this repo are copied into the workspace at `10_Code_Tech/Compliance/` (`claim_compliance_check.py` + `wa-claims-rules.json` in the same folder). Field definitions: `compliance/README.md`.

---

## 1. new-job/SKILL.md

### a) Step 1 (Take the intake): add to the bullet list

```markdown
- For insurance jobs: carrier, claim number, adjuster name and email, and the date the homeowner reported the claim to the carrier (ask: "what day did you call your insurance?"). If unknown, record null and flag it.
```

### b) Step 3 (Create the job assets), item 2 Job JSON: append

```markdown
   For insurance jobs, add the `claim` block exactly as defined in `10_Code_Tech/Compliance/README.md` (Fields to add to each job JSON). Fill carrier, claim_number, adjuster, reported_date. Set `billing_mode` to "insurance" or "direct". Leave every other claim field null.
```

### c) New step after Step 4

```markdown
## Step 4c: Start the mitigation scope clock

For insurance jobs, remind the user that the written mitigation scope must go to the adjuster by the next business day (rule CS-SCOPE-WRITTEN-DAY1). Under WAC 284-30-330(20) (effective 2026-10-18, verify), the carrier then has 5 business days to approve it or send its own scope. No written scope, no clock. Offer to draft the scope email; never send it. When the user confirms it went out, set `claim.mitigation_scope_sent` and add the message to `claim.communications` with `response_expected: true`.
```

---

## 2. log-day/SKILL.md

### a) Step 3 (Capture the day): add a new paragraph after **Work performed.**

```markdown
**Carrier contacts.** For insurance jobs, ask: "Any calls or emails with the adjuster today?" Log each in the job JSON `claim.communications` with date, direction, contact name, method, subject, response_expected, and response_date. When a carrier reply arrives, set response_date on the original entry. Record carrier milestones as they happen: acknowledged_date, mitigation_scope_response (date, result, reason_given, itemized_disallowed), carrier_inspection_date, status_notices, decision_date and decision. On Day 1, if `claim.mitigation_scope_sent.date` is null, ask whether the written scope went out and flag it if not.
```

### b) Step 4 (Write and report): append

```markdown
For insurance jobs, run `python 10_Code_Tech/Compliance/claim_compliance_check.py <job json>` after writing. Add any CLEAN SAVE ACTION, CARRIER OVERDUE, or DUE SOON findings to the open flags, one line each with the rule ID and due date. If a carrier deadline is overdue, offer the matching template from `10_Code_Tech/Compliance/templates/`. Never send it.
```

---

## 3. supplement/SKILL.md

### a) New step before Step 1

```markdown
## Step 0: Compliance pre-check

Run `python 10_Code_Tech/Compliance/claim_compliance_check.py <job json>`. Before building the supplement, make sure we have:
- The carrier's written reason and itemized disallowed amounts for any mitigation scope cut (WAC 284-30-330(21)). If missing, request them first; that list is the spine of the supplement.
- A written denial citing the policy provision for any denied lines (WAC 284-30-380).
- The carrier's estimate and notes. If not, the homeowner sends `templates/claim-file-request.md` (15 business days, WAC 284-30-340(2)).
- If the carrier cut rates "per price list", the homeowner sends `templates/pricing-data-request.md` (WAC 284-30-330(4); 284-30-380(7)-(8)).

Letters that invoke a policyholder right are sent or signed by the homeowner. Clean Save speaks only to its own scope, pricing, and documentation; never negotiate coverage (rule CS-NO-UNLICENSED-ADJUSTING).
```

### b) Step 3 (Build the supplement packet): append

```markdown
If the carrier missed a WA deadline on this job (checker CARRIER OVERDUE findings), list each in the cover letter as a factual line: the rule, the date it was due, and the date answered or "no response". Only cite rules marked verified in `wa-claims-rules.json`; for unverified ones, describe the timeline without the citation.
```

### c) Step 4 (Escalation ladder): replace the first sentence with

```markdown
Include a short escalation plan in the report, to use only if the documented supplement is refused: re-submit to the adjuster with the evidence, then request a senior adjuster or supervisor review (cite any missed WAC 284-30 deadlines), then the homeowner may file an OIC complaint (800-562-6900, insurance.wa.gov), then consider a licensed public adjuster, then the policy appraisal clause, then legal review (IFCA requires a 20-day written notice to the insurer and OIC before suit).
```

---

## 4. close-job/SKILL.md

### a) Step 2 (Verify the file is complete): add to the checklist

```markdown
- WA claim compliance (insurance jobs): run `python 10_Code_Tech/Compliance/claim_compliance_check.py <job json>`. Any open CLEAN SAVE ACTION is a gap (for example, carrier contacts not logged, or permanent work started before inspection without written approval). List open CARRIER OVERDUE items too; they may still matter for an unpaid balance.
```
