# Defect List — Iteration 006

Case: `mechanical thrombectomy for acute ischemic stroke due to right M1 MCA occlusion`

Output: `/tmp/caseprep-live-thrombectomy-v6`

## Status

- Deterministic eval: PASS (`score=100`, no missing required concepts, no deterministic failures)
- Focused test suite: PASS (`61 passed in 0.31s`)
- Full test suite: PASS (`284 passed in 1.20s`)
- Blind clinical review: PASS (`77/100`, threshold `75/100`)
- Stop reason: strict pass threshold met; no major directly unsafe procedural instruction identified by blind reviewer

## Materially improved / resolved since iteration 005

- Landmark EVT evidence is now actually retrieved and rendered rather than merely named.
- Practice-changing early-window RCTs, HERMES, DAWN/DEFUSE 3, large-core RCTs, and guideline/consensus targets are visible with PMIDs/DOIs.
- Lower-applicability M2-only, AI-workflow, rare-anomaly, case-report, and historical-vignette sources are separated into a quarantined/lower-applicability section rather than dominating the clinical evidence bottom line.
- The generated dossier preserves missing patient-specific facts instead of silently inventing LKW, NIHSS, ASPECTS/core, thrombolytic status, or access anatomy.

## P0 defects blocking pass

None identified in the final blind review.

## P1 defects / next clinical-product bottlenecks

1. **Missing numeric EVT eligibility framework**
   - The dossier needs a practical single-page decision algorithm for LKW/time window, NIHSS/disabling deficit, NCCT/ASPECTS, CTA target, CTP/MRI mismatch, thrombolytic status, large-core selection, baseline mRS/goals, and proceed/no-go decision points.

2. **Technical workflow not fully operator-ready**
   - Add concrete first-pass default, device-positioning logic, guide/BGC/DAC target position, clot-face/crossing rules, stent landing-zone strategy, retrieval under aspiration, maximum pass/switch threshold, anesthesia decision points, and BP handoff by procedural phase.

3. **Right M1 dangerous anatomy needs deeper procedural checklist**
   - Add lenticulostriate perforator zones, early M1 branch incorporation, superior/inferior division consequences, safe M2 landing zone, carotid siphon/cervical ICA hazards, arch/right CCA access issues, and tandem-lesion anatomy.

4. **Rescue algorithms remain broad**
   - Convert perforation/extravasation/SAH, sICH, re-occlusion/ICAD, tandem cervical ICA lesion, vasospasm, distal embolus/new territory embolus, device entrapment, access hemorrhage, and malignant edema into stepwise rescue pathways.

5. **Evidence-to-action linkage is still weak**
   - Landmark evidence is retrieved, but operative/anatomy/complication recommendations are not consistently mapped to citations or translated into bedside evidence pearls.

## P2 cleanup

- De-emphasize repeated MCA symmetry pilot-source appendices in bedside-facing clinical files.
- Rework “Alternatives Considered” from `needs input`/generic placeholders into a practical comparison of EVT + IV thrombolysis, EVT alone, medical management/no EVT, late-window selection, large-core selection, and low-NIHSS monitoring.
- Tighten wording around “No missing evidence-pack items” so it does not imply all technical/anatomic/rescue evidence needs are complete.

## Recommended next narrow slice

Because the canonical case now passes, the next slice is optional rather than blocking. If continuing to improve this case, prioritize:

**Add a single-page EVT go/no-go decision algorithm plus right-M1 technical/rescue checklists, with inline citation anchors for major recommendations.**

Acceptance criteria:

- `00-morning-of-case.md` or `04-operative-plan.md` contains an EVT decision algorithm with time-window, NIHSS/disabling deficit, ASPECTS/core, CTA/CTP, thrombolytic, baseline mRS/goals, and proceed/no-go prompts.
- `03-anatomy-at-risk.md` contains a right M1 dangerous-anatomy checklist covering lenticulostriates, early branches, M2 landing zone, and access-route hazards.
- `05-risk-and-rescue.md` contains stepwise algorithms for perforation/extravasation, ICAD/re-occlusion, tandem lesion, distal embolus, sICH, and malignant edema.
- Key recommendations carry citation anchors or explicit source provenance.
- Low-applicability repeated evidence is moved out of bedside-facing sections.
