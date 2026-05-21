# Defect List — Thrombectomy M1 — Iteration 004

## Resolved or materially improved from iteration 003

1. Technique workflow improved from generic scaffold to a reasonable EVT workflow.
2. Evidence section now names landmark evidence/guideline families, although without real retrieved citations.
3. BP/antithrombotic/CT timing framework improved.
4. Right M1 anatomy no longer contains the misleading brainstem-risk claim.

Score improved from 63/100 to 69/100 (+6), and from 13/100 to 69/100 overall.

## P0 remaining defects

1. Known parsed facts still leak as “needs input” in summary/README.
2. No final one-page morning-of-case view.
3. No structured case-specific decision/eligibility table.
4. Evidence retrieval remains weak and repeated low-relevance excerpts clutter output.

## P1 remaining defects

1. “Right right M1” typo/polish issue.
2. M1 procedural anatomy still needs practical detail.
3. Rescue algorithms need stepwise action sequences.
4. Landmark citations are only targets to verify rather than actual verified evidence.

## Iteration 005 implementation target

Given one final loop before the user’s stop condition, focus on improvements likely to move blind usefulness above 75:

- Propagate known parsed facts into summary and README so planned procedure/laterality/target are not marked needs input.
- Add a final one-page morning-of-case view with diagnosis/target, missing go/no-go facts, imaging checklist, access/device plan, first-pass plan, rescue plan, postop plan, and attending questions.
- Add structured thrombectomy decision tables for eligibility, access, first-pass technique, stop/switch/rescue, and post-reperfusion management.
- Fix “Right right M1” wording.
- If feasible, suppress or clearly quarantine low-relevance repeated evidence excerpts from main clinical sections.
