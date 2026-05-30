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
   - First increment delivered: an opt-in **PAPERS `/v1/ask` retriever** (`CASEPREP_PAPERS_ENABLED=1`) that pulls cited evidence from the local PAPERS corpus service — citations-only, PMID-hydrated, and a no-op when the service is unreachable. See `docs/superpowers/specs/2026-05-30-papers-ask-retriever-design.md`.

2. **Per-family evidence packs** — Extend the evidence-pack pattern (tiered, required-for, conditional) from thrombectomy to all procedure families: ACDF, convexity meningioma, Chiari, functional epilepsy, and future families.

3. **Corpus subdomain expansion** — Add spine surgery, tumor, and functional subdomains to the local corpus, or build procedure-family-specific SQLite databases alongside the pgvector bridge.

4. **Per-family clinical applicability rules** — Each family needs tuned quarantine rules like the ACDF rules added here, keyed off `family.id` in `classify_clinical_applicability()`.

5. **Deterministic eval hardening** — Tighten gates so `needs input` / `needs synthesis` placeholders in evidence sections fail the canonical eval for any family that has completed its evidence pipeline.

## Briefing Completeness (Neuro-IR)

A program to bring each procedure family's briefing to a complete, fully-sourced
standard. Design + plan:
`docs/superpowers/specs/2026-05-30-thrombectomy-briefing-completeness-design.md`.

**Cycle 1 — thrombectomy (in progress):**

1. **`prognostic_signs` block.** Favorable / unfavorable outcome indicators
   (ASPECTS, collaterals, time-to-reperfusion, final mTICI, core size, late-window
   mismatch, etc.), authored and **cited to landmark thrombectomy trials**
   (HERMES, DAWN, DEFUSE-3, SELECT2, AHA/ASA), rendered atop the postop file.
2. **Source-coverage audit.** A deterministic check (`check_source_coverage` in
   `caseprep/evaluation/rubric.py`) that fails the canonical eval when a sourceable
   prognostic claim is left uncited or a `needs synthesis` appears in a sourceable
   section. This is a first, scoped delivery of "Planned Improvements" item 5
   (eval hardening), built family-agnostic via a `SOURCEABLE_SECTIONS` registry.

**Next cycles (2–6):** apply the same pattern to the rest of the neuro-IR family
— aneurysm coiling, flow diversion, AVM/dAVF embolization, carotid stenting, and
venous procedures.

## Inline Figure Hovercards

The briefing can render an interactive `briefing.html` where clinically-salient
words carry a hover superscript revealing the most relevant figure (from the
`image_bank` PMC corpus or the `textbook_figures` corpus), each traceable to its
source. Design + plan:
`docs/superpowers/specs/2026-05-30-inline-figure-hovercards-design.md`.

It is **two-stage**: tag-match decides which words are marked; semantic
similarity decides which single figure pops up. Both run offline against a local
figure store.

**One-time build (needs the Postgres corpus + the embedding model):**

```bash
uv run --with sentence-transformers python -m caseprep.image_bank.figure_build
```

This merges both corpora into `caseprep/image_bank/figure_store.sqlite`
(image_bank captions are embedded with `all-mpnet-base-v2`; textbook figures copy
their existing embedding + image bytes). After it exists, generating a briefing
also emits `briefing.html` with the hovercards. Without the store, the briefing
renders normally (no hovercards) — the export is best-effort and never blocks.
