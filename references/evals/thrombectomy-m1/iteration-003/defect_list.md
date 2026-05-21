# Defect List — Thrombectomy M1 — Iteration 003

## Resolved or materially improved from iteration 002

1. Imaging review is now thrombectomy-specific and no longer blank.
2. EVT eligibility/decision-boundary framework was added.
3. Missing imaging/eligibility facts are visibly labeled incomplete/needs input.
4. Readability is now strong enough for checklist use.

Score improved from 52/100 to 63/100 (+11), and from 13/100 to 63/100 overall.

## P0 remaining defects

1. Evidence is still poor/off-target: missing landmark anterior-circulation LVO trials and guidelines.
2. Practical technique plan lacks first-pass/escalation algorithm and device/catheter specifics.
3. Peri-procedural BP/anesthesia/antithrombotic targets are too vague.
4. Right M1 functional/anatomic prep is too generic and contains imprecise brainstem language.

## P1 remaining defects

1. Rescue playbooks need operational step sequences.
2. Parsed facts such as right/M1/procedure should propagate more completely to summary/snapshot fields.
3. Evidence excerpts are too long and not distilled.
4. Source relevance gates should flag M2/AI/rare case report dominance for an M1 case.

## Next implementation slice

Add landmark EVT evidence bundle/relevance synthesis plus actionable right M1 procedure defaults.

Acceptance criteria:
- `07-evidence.md` has a concise thrombectomy evidence bottom line and mentions key landmark evidence/guideline categories for anterior circulation LVO/M1 EVT.
- M2-only, AI detection, rare anomaly, or historical vignette sources are clearly labeled lower applicability or not allowed to dominate the clinical bottom line.
- `04-operative-plan.md` includes a more actionable M1 first-pass/escalation algorithm.
- `06-postop-plan.md` or `05-risk-and-rescue.md` includes typical BP/antithrombotic/CT timing frameworks with local-protocol caveats and no invented patient values.
- Remove or correct “brainstem risk” from right M1 anatomy language.
