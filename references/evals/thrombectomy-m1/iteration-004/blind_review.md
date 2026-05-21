# Blind Clinical Review — Thrombectomy M1 — Iteration 004

Output reviewed: `/tmp/caseprep-live-thrombectomy-v4`

Case input: `mechanical thrombectomy for acute ischemic stroke due to right M1 MCA occlusion`

## Overall score

69/100 — FAIL

Pass threshold: 75/100.

The dossier is not dangerous overall and contains many appropriate thrombectomy safety concepts, but remains too generic, has weak/poorly targeted evidence retrieval, and leaves too many high-value case-prep fields as “needs input.” It would help a junior resident orient to generic right M1 thrombectomy issues, but it is not yet a strong case-specific preoperative/fellow-level thrombectomy preparation document.

## Category scores

- Technique / operative workflow: 20/25
- Anatomy / dangerous structures: 15/20
- Complications / rescue plans: 12/15
- Alternatives / decision boundaries: 7/10
- Evidence quality and relevance: 3/10
- Case-specificity: 6/10
- Readability / usability: 4/5
- Provenance / citation support: 2/5

## Top clinically important missing or weak items

1. Proper landmark evidence support: exact citations and applicability summaries are needed for MR CLEAN, ESCAPE, EXTEND-IA, SWIFT PRIME, REVASCAT, HERMES, DAWN, DEFUSE 3, SELECT2/ANGEL-ASPECT/RESCUE-Japan LIMIT, and guidelines.
2. A real case-specific decision/eligibility table is missing.
3. More practical M1 procedural anatomy is needed: proximal vs distal M1, early bifurcation, lenticulostriate origin zones, anterior temporal/frontal early branches, M2 superior/inferior division involvement, safe trajectory/deployment hazards.
4. Rescue algorithms need stepwise procedural responses.
5. Post-thrombectomy management should be more protocol-ready.

## Unsafe, misleading, or overly generic content

- Evidence section is misleading by volume: repeated irrelevant/truncated abstracts look authoritative while low-applicability to routine right M1 EVT.
- Rare “twig-like MCA” case report is overrepresented.
- M2 meta-analyses and M2 aspiration comparisons are poor evidence anchors for right M1.
- README/case summary leave planned procedure and laterality as needs input despite the prompt specifying them.
- “BADDASS-style strategy” needs caveat as technique preference, not universal standard.
- “Right right M1” typo suggests insufficient clinical polish.

## Would this help a resident/fellow prepare?

Partially. It is useful as a generic pre-puncture cognitive aid, but not sufficient as high-quality fellow-level case prep. A fellow would still need to independently review actual imaging, institutional protocol, landmark evidence/guideline criteria, device plan, and attending preference.

## Recommended next fixes

1. Add thrombectomy-specific evidence retriever or stronger evidence relevance gate.
2. Rank evidence by applicability and remove repeated low-relevance abstracts from major sections.
3. Improve parser-field propagation so known right/M1/mechanical thrombectomy facts do not remain “needs input.”
4. Build structured thrombectomy decision tables.
5. Add M1-specific procedural anatomy module.
6. Convert rescue content into stepwise algorithms.
7. Reduce generic needs-input clutter.
8. Add a final one-page morning-of-case view.
