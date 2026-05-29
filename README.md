# caseprep

Generate structured neurosurgical case prep materials from a topic string.

## Install

```bash
pip install -e ".[dev]"
```

## Usage

```bash
caseprep "vestibular schwannoma"
caseprep "acoustic neuroma" --open
caseprep "pituitary adenoma" -o ~/cases/pa --local-pdfs ~/papers/
```

## Output

```
vestibular-schwannoma-caseprep/
├── caseprep.yaml
├── provenance.json
├── README.md
├── 01-case-summary.md
├── 02-imaging-review.md
├── 03-anatomy-at-risk.md
├── 04-operative-plan.md
├── 05-risk-and-rescue.md
├── 06-postop-plan.md
├── 07-evidence.md
├── 08-checklists.md
├── 09-open-questions.md
└── resource-links.html
```

The canonical source of truth is `caseprep.yaml`. Markdown files are rendered
from that schema for quick review. `provenance.json` records whether content is
generated, inferred, cited, user-entered, or verified. Generated clinical
content should be treated as draft material until reviewed by a clinician.

## MCP Tools

```
search_pubmed       — PubMed search with clinical filters, optional abstracts
build_caseplan      — 4-axis search → filled templates + PMC full text
generate_caseprep   — blank (fill-in-the-blanks) template scaffold
get_fulltext        — 3-tier: PMC → structured → plain abstract for a PMID
search_local_pdfs   — PyMuPDF search of local PDF files
search_radiology    — Open-i (NIH) radiology images: MRI, CT, X-ray, ultrasound
```

## Run tests

```bash
pytest -v
```

## Planned Improvements

CasePrep was initially developed for neurointerventional (thrombectomy) cases, which have the most mature pipeline: procedure-specific evidence packs, dedicated corpus subdomain coverage, and tuned clinical applicability scoring.

The goal is to bring **all** procedure families to the same level of output quality:

| Capability | Neurointerventional | Spine / ACDF | Tumor / Functional / Other |
|---|---|---|---|
| Procedure-specific evidence packs | ✅ Full (tiered packs) | 🔄 Planned | 🔄 Planned |
| Corpus subdomain coverage | ✅ 17 dedicated subdomains | 🔄 Needs spine surgery subdomains | 🔄 Needs expansion |
| Clinical applicability quarantine | ✅ Tuned M1/M2/posterior rules | ✅ Added | 🔄 Per-family |
| Dedicated retrieval templates | ✅ Thrombectomy-optimized | ✅ Added (procedure_taxonomy.py) | 🔄 Per-family |
| pgvector (full 1.7M papers) | ✅ Queried via evidence packs | 🔄 Planned | 🔄 Planned |
| Blind review scoring | ✅ 8-9/10 verified | ✅ Template defaults pass, evidence needs pgvector | ❌ Not yet tested |

**Planned work:**

1. **pgvector corpus integration** — Route non-neurointerventional family queries (spine, tumor, functional, Chiari) to the PostgreSQL/pgvector corpus with 1.7M papers instead of relying solely on the lean neurointerventional SQLite database. This will unlock ACDF technique/outcome papers and all other spine surgery literature that doesn't exist in the current local corpus.

2. **Per-family evidence packs** — Extend the evidence-pack pattern (tiered, required-for, conditional) from thrombectomy to all procedure families: ACDF, convexity meningioma, Chiari, functional epilepsy, and future families.

3. **Corpus subdomain expansion** — Add spine surgery, tumor, and functional subdomains to the local corpus, or build procedure-family-specific SQLite databases alongside the pgvector bridge.

4. **Per-family clinical applicability rules** — Each family needs tuned quarantine rules like the ACDF rules added here, keyed off `family.id` in `classify_clinical_applicability()`.

5. **Deterministic eval hardening** — Tighten gates so `needs input` / `needs synthesis` placeholders in evidence sections fail the canonical eval for any family that has completed its evidence pipeline.

## Image Bank Integration

The curated image bank (`caseprep/image_bank/`, ~20k neurosurgically-relevant
figures with structured labels) feeds prep images into briefings.

**In progress — thrombectomy exemplar** (design:
`docs/superpowers/specs/2026-05-29-image-bank-briefing-integration-design.md`):
bind curated bank images to the thrombectomy schema's existing image-spec
strings (e.g. `images_to_display_in_or`) via a deterministic
structured-filter + lexical matcher, with full source provenance (each image
traceable to its PMCID/PMID + caption) and inline Markdown/HTML rendering.
Precision over recall: below threshold, no image rather than a wrong one.

**Next — briefing clinical-content completeness for neuro-IR.** Bring the
thrombectomy briefing to a complete, fully-sourced standard:

1. **Add a `prognostic_signs` schema block** (favorable / unfavorable outcome
   indicators) — currently not modeled.
2. **Source-coverage audit** — every clinical claim in each section carries a
   `source_id`; no silent `needs input` where evidence exists.
3. **Extend across the neuro-IR family** — apply the same completeness +
   image-integration bar to aneurysm coiling, flow diversion, AVM/dAVF
   embolization, carotid stenting, and venous procedures.
