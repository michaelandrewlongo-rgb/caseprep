# Defect List — Thrombectomy M1 — Iteration 002

## Resolved or materially improved from iteration 001

1. Wrong-procedure open-surgery scaffold mostly removed from thrombectomy output.
2. Operative workflow now includes a useful generic thrombectomy skeleton.
3. Anatomy-at-risk now includes MCA/M1 route anatomy and danger structures.
4. Risk/rescue now includes thrombectomy-specific complications.
5. Postop plan and open questions are more thrombectomy-specific.

Score improved from 13/100 to 52/100 (+39).

## P0 remaining defects

1. Imaging review is essentially absent.
2. EVT eligibility/decision-boundary framework is missing or too thin.
3. Evidence selection is off-target and misses landmark LVO/M1 thrombectomy trials/guidelines.
4. Main dossier still relies on placeholders/needs-input fields for core clinical facts.

## P1 remaining defects

1. Procedural workflow remains generic and needs M1/device-specific detail.
2. Rescue plans need action sequences rather than only complication labels.
3. BP/post-reperfusion management needs common decision logic/ranges rather than only local-protocol deferral.
4. Evidence excerpts are too long and not distilled into applicability notes.
5. Attending-preference capture is missing.

## Next implementation slice

Add a mandatory thrombectomy imaging review + EVT eligibility section.

Acceptance criteria:
- `02-imaging-review.md` is not blank for thrombectomy.
- It contains structured prompts for NCCT/ASPECTS, hemorrhage exclusion, CTA occlusion site, ICA terminus/tandem lesion, collaterals, CTP/core-penumbra if applicable, arch/cervical access anatomy, and suspected ICAD/dissection.
- `01-case-summary.md` or `04-operative-plan.md` includes an EVT eligibility/decision frame: LKW/time window, NIHSS/disabling deficit, baseline mRS, IV tPA/TNK, early vs late window, large core, low NIHSS LVO, and medical-management boundaries.
- Missing critical imaging/eligibility facts are prominently labeled as incomplete rather than quietly deferred.
- Avoid fake patient-specific values.
