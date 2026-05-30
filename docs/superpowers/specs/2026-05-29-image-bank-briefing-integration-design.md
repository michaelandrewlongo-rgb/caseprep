# Image-Bank → Thrombectomy Briefing Integration — Design

**Date:** 2026-05-29
**Status:** Approved design, ready for implementation plan
**Scope:** One exemplar procedure (mechanical thrombectomy / LVO stroke), image
integration only. Clinical-content completeness is a separate, later cycle
(see "Deferred work" and README → Planned Improvements).

## Problem

The curated image bank (`caseprep/image_bank/bank.db` + `images/`, ~20,296 live
rows, each `is_neurosurgical=1`, `surgical_usefulness ≥ 4`) is completely
disconnected from the briefing pipeline. `grep` confirms nothing outside
`image_bank/` references it. Meanwhile the thrombectomy schema already *declares
what images a briefing needs* as free-text specs, e.g.:

- `imaging_review.images_to_display_in_or = ["NCCT axial ASPECTS/hemorrhage-exclusion images.", ...]`
- rendered headings "Images To Display In OR" / "Images To Display In Angio Suite"

These are descriptions with no actual image attached. This cycle binds real
bank images to those specs, with full source provenance, rendered inline.

## Goals

1. Bind curated bank images to the thrombectomy briefing's existing image-spec
   strings.
2. Every surfaced image is traceable to its source paper (PMCID/PMID + caption);
   nothing is generated or inferred.
3. Render images inline under the section that requested them in Markdown output.
   HTML rendering of bound images is deferred until the product introduces an
   HTML briefing body (currently only resource-links.html exists).
4. Graceful degradation: if the image index is unavailable, the briefing renders
   exactly as it does today (no images, no crash).

## Non-goals (this cycle)

- Clinical-content completeness (e.g. the missing `prognostic_signs` block,
  filling `needs input` placeholders). Deferred — documented in README.
- Other procedure families (aneurysm, AVM, spine, tumor, functional).
- Re-labeling or re-harvesting the bank.
- Embedding/vector search (explicitly deferred — see Decision D2).

## Key decisions

- **D1 — Sidecar index, built offline.** Build a lightweight index over the live
  bank once; rebuild only when the bank changes. No per-case embedding work.
- **D2 — Deterministic lexical matcher for v1, NOT embeddings.** Image specs are
  short controlled phrases; the bank has rich structured labels (`modality`,
  `cluster`, `anatomy`, `procedure`, `keywords`, `caption_summary`). A structured
  prefilter + token-overlap score is more *traceable* (shows which tokens
  matched), carries no heavy model dependency, and is trivially testable. An
  embedding rerank may be added later only if recall proves inadequate.
- **D3 — Precision over recall.** Below the match threshold, attach no image
  rather than a marginal one. A wrong ASPECTS image in a case briefing is worse
  than an absent one.
- **D4 — Images enter the existing `generated → verified` provenance flow.** Each
  bound image is recorded with `value_status: "generated"` and the source
  PMCID/PMID, so a clinician can later mark it `verified` exactly like text.

## Architecture

Three new units + two integration touch-points. Each unit has a single purpose
and a narrow interface.

### Unit 1 — `ImageIndex` (`caseprep/image_bank/image_index.py`)

Builds and loads a deterministic, structured index over the live bank.

- **`build()`**: reads `bank.db` joined `images ⋈ labels`, and for each row with
  an existing `local_path` writes an index record:
  `{fig_id, local_path, pmcid, pmid, cluster, modality, caption_summary,
    keywords (tokenized set), anatomy, procedure}`.
  Persisted as a sidecar JSON/SQLite table next to `bank.db`
  (`image_index.json` or a `image_index` table). Rebuilt only on demand.
- **`load()`**: returns the in-memory index, or signals unavailable (missing
  file → callers degrade to `[]`).
- **Depends on:** `bank.db` only. No network, no model.

### Unit 2 — `ImageBankRetriever` (`caseprep/retrievers/image_bank.py`)

Given an image-spec string + section context, return ranked `ImageMatch`es.

- **`retrieve(spec: str, *, section: str, top_k: int = 2) -> list[ImageMatch]`**
- **Algorithm (deterministic):**
  1. **Modality hint** parsed from the spec via a small controlled map:
     `NCCT|CT|noncontrast → CT`; `CTP|perfusion → CT`; `CTA → CT_angiography`;
     `DSA|angiogram|angio → DSA/angiogram`; `MRI|DWI|ADC → MRI`;
     `MRA → MR_angiography`. Unmatched → no modality constraint.
  2. **Cluster prefilter:** restrict to thrombectomy-relevant clusters
     (`stroke_thrombectomy`, `carotid_cervical_vascular`,
     `intracranial_atherosclerosis`, `general_neurointerventional`).
  3. **Lexical score:** token-overlap (Jaccard or weighted overlap) of the
     spec's content tokens against `caption_summary ∪ keywords ∪ anatomy ∪
     procedure`, with modality match as a hard prefilter / strong boost.
  4. **Overlap gate + cap:** require at least `MIN_OVERLAP` (≥2) matched content
     tokens; return top_k ranked by score then surgical usefulness.
- **Graceful degradation:** index unavailable or empty result → return `[]`
  (mirrors `SemanticCorpusRetriever`'s contract).
- **`ImageMatch`** = `{fig_id, local_path, caption, pmcid, pmid, score,
  matched_spec, matched_tokens}`.
- **Depends on:** `ImageIndex`.

### Unit 3 — Binding step (in the core builder, not the static scaffold)

Note: image binding is wired into the core/evidence pipeline (`build_core_case_plan` →
`_write_core_artifacts`). The `generate_caseprep` static-scaffold path intentionally
does not bind images.

For each thrombectomy section carrying image-spec strings, call the retriever
and attach matches to the schema under a new per-section `images` list:

```
schema.<section>.images = [
  {local_path, caption, pmcid, pmid, score, matched_spec}
]
```

For each attached image, write a provenance entry:
`field_path = "sections.<section>.images[i]"`,
`value_status = "generated"`,
`source_ids = ["PMC…", "pmid-…"]`,
`notes = "matched spec '<spec>' via tokens {…} (score 0.NN)"`.

### Touch-point — Renderers (`renderers/markdown.py`)

Under each section that has bound images, emit them in Markdown:
`![caption](local_path)`, caption, and a source link to the PMC article.
No layout changes elsewhere. HTML rendering of bound images is deferred (the
current HTML artifact is only the resource-links search-links page).

## Data flow

```
(offline)  bank.db (images ⋈ labels) ──► ImageIndex.build() ──► image_index sidecar

(per case) thrombectomy schema ──► image-spec strings ("NCCT axial ASPECTS images")
                                          │
                                          ▼
                ImageBankRetriever.retrieve(spec, section)
                = modality hint → cluster prefilter → lexical score → threshold → top_k
                                          │
                                          ▼
            schema.<section>.images[] = [{local_path, caption, pmcid, pmid, score}]
                          ┌───────────────┴───────────────┐
                          ▼                                ▼
              provenance.json entry              Markdown inline render
            (generated, source = PMCID)        (image + caption + PMC source link)
```

## Error handling

| Condition | Behavior |
|---|---|
| Index sidecar missing | `ImageIndex.load()` → unavailable; retriever returns `[]`; builder emits existing "zero records" warning; briefing renders without images. |
| Spec yields no modality hint | Skip modality constraint; score by lexical overlap within clusters only. |
| All matches below `MIN_OVERLAP` (< 2 matched tokens) | Attach no image to that section (precision over recall). |
| `local_path` points to a missing file | Skip that record at index-build time; never bind a broken path. |
| Image is a known-bad file (e.g. 1×1 px) | Index-build filters by minimum file size / dimensions. |

## Testing

- **Unit — modality parsing:** `"NCCT axial ASPECTS images"` → `CT`;
  `"final DSA showing TICI grade"` → `DSA/angiogram`; unknown → no constraint.
- **Unit — overlap gating:** below `MIN_OVERLAP` (< 2 matched tokens) → `[]`.
- **Unit — graceful degradation:** missing index → `[]`, no exception.
- **Unit — index build hygiene:** rows with missing/0-byte/1×1 files excluded.
- **Integration:** fixture thrombectomy schema → the ASPECTS spec binds a
  `CT`-modality image from `stroke_thrombectomy`; assert a provenance entry
  exists carrying that image's PMCID.
- **Render snapshot:** Markdown for a section includes the image and a PMC
  source link (HTML rendering of bound images is deferred).

## Deferred work (next cycle, tracked in README)

**Briefing clinical-content completeness for neuro-IR.** Bring thrombectomy
sections to a complete, fully-sourced standard and close gaps:

- Add a `prognostic_signs` schema block (favorable / unfavorable) — currently
  absent (0 schema hits).
- Audit every thrombectomy section so each clinical claim carries a `source_id`;
  no silent `needs input` where evidence exists.
- Extend the evidence-pack + synthesis pattern across the rest of the neuro-IR
  family (aneurysm coiling, flow diversion, AVM/dAVF embolization, carotid
  stenting, venous).

## Open implementation notes

- Reuse `EvidenceRecord`-style graceful-degradation conventions and the existing
  provenance writer rather than inventing new ones.
- Index sidecar format (JSON vs `image_index` table in `bank.db`) to be settled
  in the implementation plan; both satisfy the offline-build, fast-load contract.
- `MIN_OVERLAP` and `top_k` defaults to be tuned against a handful of real
  thrombectomy specs during implementation; start conservative (high precision).
