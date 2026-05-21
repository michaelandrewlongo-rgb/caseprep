# CasePrep Blind Clinical Review Improvement Loop

CasePrep product quality is judged by generated dossiers, not by tests alone. Every clinically meaningful product change should pass through a live-output loop with independent blind clinical review.

## Loop

1. Select one canonical case.
2. Build a live dossier with `caseprep build`.
3. Run deterministic evaluation checks.
4. Package the generated markdown dossier for blind review.
5. Dispatch an independent reviewer with no implementation context.
6. Convert the review into P0/P1/P2 product defects.
7. Implement one narrow fix.
8. Rebuild the same case.
9. Dispatch a fresh blind review.
10. Compare score delta and remaining defects.
11. Repeat until the case passes.
12. Lock regressions before moving to the next canonical case.

## Blind review rules

The reviewer may see:
- the case input string
- the generated output files
- the scoring rubric
- instructions to review as a strict clinical user

The reviewer must not see:
- previous scores or reviews
- implementation details
- what changed
- expected improvements
- internal architecture or tests
- the current hypothesis about failures

## Rubric

100 points total:
- Technique / operative workflow: 25
- Anatomy / dangerous structures: 20
- Complications / rescue plans: 15
- Alternatives / decision boundaries: 10
- Evidence quality and relevance: 10
- Case-specificity: 10
- Readability / usability: 5
- Provenance / citation support: 5

Pass threshold: 75/100.

## Iteration success gate

An iteration succeeds if:
- deterministic eval still passes, and
- score improves by at least 15 points or a P0 clinical defect is resolved, and
- no new unsafe/misleading content appears.

## Canonical case pass gate

A canonical case passes only when:
- score is at least 75/100,
- no P0 clinical defects remain,
- no wrong-procedure template language appears,
- reviewer says the dossier would help a resident/fellow prepare,
- deterministic eval passes.

## Current active loop

Case: mechanical thrombectomy for acute ischemic stroke due to right M1 MCA occlusion.

Iteration 001 failed at 13/100. The primary product failure was generic/open-surgery scaffold content being used for an endovascular thrombectomy case, with missing thrombectomy workflow, M1 anatomy, complication rescue trees, imaging eligibility, and post-reperfusion ICU plan.

Iteration 002 improved to 52/100 after replacing generic open-surgery scaffold content with thrombectomy-specific dossier sections.

Iteration 003 improved to 63/100 after adding thrombectomy imaging review and EVT eligibility framing.

Iteration 004 improved to 69/100 after adding landmark EVT categories and actionable right M1 management defaults.

Iteration 005 improved to 72/100 but did not meet the strict 75 threshold. Remaining bottleneck: landmark EVT evidence/guidelines were named but not reliably retrieved/cited, while lower-applicability sources cluttered the clinical files.

Iteration 006 passed at 77/100 after evidence-pack forced retrieval, landmark/guideline coverage rendering, and quarantine/lower-applicability separation. Deterministic eval passed with score 100; full suite passed with 284 tests after adding the M2 applicability regression test. Remaining non-blocking bottlenecks: numeric EVT eligibility algorithm, deeper right-M1 technical/rescue checklists, and stronger citation-to-recommendation mapping.
