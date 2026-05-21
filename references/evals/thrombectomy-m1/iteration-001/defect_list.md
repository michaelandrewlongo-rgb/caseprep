# Defect List — Thrombectomy M1 — Iteration 001

## P0 defects

1. No thrombectomy-specific operative workflow.
2. Generic open-surgery scaffold language appears in an endovascular case.
3. Anatomy-at-risk is essentially blank for right M1 thrombectomy.
4. Risk/rescue content is not thrombectomy-specific.
5. Evidence is not synthesized into actionable guidance.

## P1 defects

1. Poor source targeting: M2-only papers and rare case reports are too prominent for right M1 LVO.
2. Landmark LVO trials and guidelines are missing or not emphasized.
3. Post-reperfusion ICU/neurocritical care plan is missing.
4. Imaging eligibility framework is missing.
5. Open questions are generic rather than thrombectomy-specific.

## Next implementation slice

Create a procedure-family-specific thrombectomy dossier template/rendering path.

Acceptance criteria:
- No “incision,” “levels,” or “subtotal resection” language in thrombectomy output.
- `04-operative-plan.md` contains a thrombectomy workflow scaffold.
- `03-anatomy-at-risk.md` contains M1/lenticulostriate/M2 danger anatomy.
- `05-risk-and-rescue.md` contains thrombectomy-specific complications and rescue actions.
- `06-postop-plan.md` contains post-reperfusion ICU/neurovascular plan.
- `09-open-questions.md` contains thrombectomy-specific missing facts.
- Blind review score improves materially from 13/100.
