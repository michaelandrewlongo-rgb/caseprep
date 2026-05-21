# Blind Clinical Review — Thrombectomy M1 — Iteration 001

Output reviewed: `/tmp/caseprep-live-thrombectomy`

Case input: `mechanical thrombectomy for acute ischemic stroke due to right M1 MCA occlusion`

## Overall score

13/100 — FAIL

Pass threshold: 75/100.

The dossier is not clinically usable as a night-before or morning-of preparation document for a right M1 MCA thrombectomy. It is largely an empty template with scattered undigested literature excerpts. It identifies the broad procedure family and laterality/segment in the parser output, but almost all clinically actionable thrombectomy content is missing.

## Category scores

- Technique / operative workflow: 2/25
- Anatomy / dangerous structures: 2/20
- Complications / rescue plans: 2/15
- Alternatives / decision boundaries: 1/10
- Evidence quality and relevance: 3/10
- Case-specificity: 2/10
- Readability / usability: 2/5
- Provenance / citation support: 1/5

## Top clinically important missing or weak items

1. Imaging selection and eligibility framework: NCCT/ASPECTS, CTA right M1 confirmation, CTP/core-penumbra if late window, collaterals, hemorrhage exclusion, tandem lesion/access anatomy.
2. Stepwise thrombectomy workflow: access, catheter stack, guide/BGC or distal access catheter, aspiration vs stent retriever vs combined first-pass plan, roadmap strategy, clot crossing, pass limits, mTICI target, final checks.
3. Anatomy and danger zones: M1 perforators/lenticulostriates, early branches, M2 bifurcation anatomy, hidden distal vessel course, ICA terminus/ACA involvement, blind microwire crossing risk, tandem/cervical carotid disease.
4. Complication-specific rescue plans: perforation/SAH, dissection, embolus to new territory, vasospasm, failed recanalization, re-occlusion, symptomatic hemorrhage, access-site complications, malignant edema.
5. Post-procedure neurocritical care plan: BP targets, neuro checks, CT timing, antithrombotic timing, groin/radial checks, ICU destination, hemorrhagic transformation surveillance, decompressive hemicraniectomy triggers.

## Unsafe, misleading, or overly generic content

- Generic open-surgery language appears in a thrombectomy dossier, including “before incision,” “levels,” and “subtotal resection.”
- Routine antibiotic redosing and generic drain/device language distract from stroke/endovascular checks.
- Alternatives and decision boundaries are blank.
- The evidence section may overemphasize M2 literature and rare case reports for an M1 case.
- Major sections still contain “needs input” or generic scaffolding.

No obvious fabricated citations were identified, but citation selection and relevance were poor, and evidence was not clinically synthesized.

## Would this help a resident/fellow prepare?

Only minimally. It may remind the user that key facts are missing and that the case is a vascular/endovascular thrombectomy for right M1 occlusion, but it would not meaningfully prepare a resident/fellow to participate in or present the case.

## Recommended fixes

1. Add a thrombectomy-specific template pathway.
2. Replace generic neurosurgery placeholders with endovascular-specific fields.
3. Improve evidence relevance filtering toward landmark LVO/M1 thrombectomy trials and guidelines.
4. Force synthesis into actionable notes instead of pasted abstracts.
5. Add hard safety-critical minimum content before marking a dossier clinically usable.
6. Add case-specific open questions for time window, NIHSS, ASPECTS/core, thrombolytic status, baseline mRS, access, anesthesia, and BP plan.
7. Add thrombectomy complication/rescue decision trees.
