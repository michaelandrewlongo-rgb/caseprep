# Blind Clinical Review — Thrombectomy M1 — Iteration 005

Output reviewed: `/tmp/caseprep-live-thrombectomy-v5`

Case input: `mechanical thrombectomy for acute ischemic stroke due to right M1 MCA occlusion`

## Overall score

72/100 — FAIL

Pass threshold: 75/100.

This is close to usable and contains many clinically appropriate thrombectomy concepts, but it fails strict review because it is too generic, the evidence/provenance layer is weak and partially irrelevant, and several case-critical operational details remain underspecified. It would help orient a trainee, but is not a complete or reliable pre-case dossier without attending/stroke-team verification.

## Category scores

- Technique / operative workflow: 21/25
- Anatomy / dangerous structures: 15/20
- Complications / rescue plans: 12/15
- Alternatives / decision boundaries: 7/10
- Evidence quality and relevance: 4/10
- Case-specificity: 7/10
- Readability / usability: 4/5
- Provenance / citation support: 2/5

## Top clinically important missing or weak items

1. Landmark evidence not actually cited: needs real citations/PMIDs/DOIs and applicability points for MR CLEAN, ESCAPE, EXTEND-IA, SWIFT PRIME, REVASCAT, HERMES, DAWN, DEFUSE 3, SELECT2, ANGEL-ASPECT, RESCUE-Japan LIMIT, and current guidelines.
2. No operational eligibility thresholds: early/late window, ASPECTS/core, mismatch, disabling deficit, baseline mRS, BP before thrombolysis/EVT, and post-EVT BP by reperfusion/hemorrhage status remain too generic.
3. Rescue stenting / ICAD / tandem lesion plan is too vague.
4. Perforation/extravasation rescue lacks procedural specificity.
5. Evidence appendices still pollute clinical files with low-relevance material.

## Unsafe, misleading, or overly generic content

- No obvious fabricated patient-specific data; unknowns are marked needs input.
- Evidence layer is misleading by volume: many low-applicability sources appear repeatedly.
- Landmark trials are named without exact citations.
- BADDASS/combined technique may be overemphasized relative to balanced operator/institutional practice.
- BP guidance is reasonable but broad and should not be treated as orders.

## Would this help a resident/fellow prepare?

Yes, partially. It would help a trainee remember major pre-puncture checks, anatomy at risk, thrombectomy workflow, complications, and attending questions. The morning-of-case page and operative checklist are useful.

It is still more of a generic thrombectomy safety template than a fully grounded right M1 thrombectomy case guide.

## Recommended next fixes

1. Improve evidence retrieval for canonical procedures: force landmark EVT trials/guidelines before lower-relevance sources.
2. Add evidence hierarchy/filtering: practice-changing evidence, guidelines, technique reviews, edge-case/case reports.
3. Add structured eligibility threshold module.
4. Add procedural rescue algorithms.
5. Make the output more case-specific despite sparse input.
6. Reduce repetition and move low-relevance excerpts to a true appendix.
7. Add attending preference capture fields.
