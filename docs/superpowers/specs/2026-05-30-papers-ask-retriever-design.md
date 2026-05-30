# PAPERS `/v1/ask` → CasePrep evidence retriever — design

**Date:** 2026-05-30
**Status:** Design (awaiting review)
**Branch:** `worktree-papers-ask-integration` (off `origin/main` @ 048ca2c)

## 1. Goal

Let CasePrep draw on the PAPERS corpus (~1.7M papers, behind a local FastAPI
`/v1/ask` RAG service) when building a briefing — **without** weakening
CasePrep's provenance contract.

The integration adds one new retriever, `PapersAskRetriever`, that calls
PAPERS `/v1/ask`, keeps **only the citations** (discarding the DeepSeek-synthesized
prose), and returns `EvidenceRecord`s into the existing core-builder evidence
flow. PAPERS becomes a high-recall retrieval source beside `CorpusRetriever`,
`SemanticCorpusRetriever`, and `PubMedRetriever` — never a section author.

Non-goals (this cycle): using PAPERS's synthesized `answer` text in the
briefing; wiring `/v1/ask-agentic`; the figure-precision cycle (separate work).

## 2. Why citations-only

CasePrep's identity is provenance-first: every claim flows `generated → verified`
with real citations via `enforce_provenance`. PAPERS *also* synthesizes
(DeepSeek v4-flash) — stacking two synthesis layers would blur trust. Taking
only `citations[]` and feeding them through CasePrep's existing enricher/auditor
preserves the single-source-of-truth guarantee: every PAPERS-sourced fact in a
briefing is one CasePrep verified, CasePrep-cited.

This mirrors PAPERS's own epistemics: it already excludes textbook rows
(`work_id` starting `tb:`) from `citations` — citable evidence is kept distinct
from background. The two systems share a spine.

## 3. The contract (verified from PAPERS source)

**Endpoint:** `POST {PAPERS_BASE}/v1/ask` (default `http://127.0.0.1:8000`)

**Request** (`AskRequest`, fields we set):
- `question: str` (required)
- `max_papers: int` (1–50, default 20) — we cap lower (≈8) for briefing use
- `include_figures: false` — figures are a separate CasePrep cycle
- `use_passages: true` (default) — passage-level retrieval
- optional filters: `domain`, `pathology`, `intervention`, `study_type`,
  `year_from/to`, `min_confidence` — populated from the case when available

**Response** (`AskResponse`) — we consume only:
- `retrieved_papers: list[PaperCitation]` — the payload we keep (full retrieved
  set, capped at `max_papers`). **Corrected after live validation:** the running
  service has **no `citations` key** — it exposes `retrieved_papers`, a `papers`
  alias, and a `cited_papers` subset (only what the LLM cited in `answer`). The
  retriever reads `retrieved_papers` → `papers` → legacy `citations` via
  `_citation_list()`, working against the live service and older/mocked shapes.
- `retrieval_count`, `usage`, `status`, `truncated` — logged, not rendered
- `answer`, `cited_papers`, `figure_hits`, `grounded_claims` — **discarded**

Live validation (2026-05-30, container recreated with `ASK_PUBLIC_API_ENABLED=1`):
a no-cookie `POST /v1/ask` for a thrombectomy BP question returned HTTP 200 with
6 `retrieved_papers`, **all carrying PMID + DOI** — landmark thrombectomy trials.
An end-to-end run of the enabled retriever against the live service likewise
returned 6 PMID-identified `EvidenceRecord`s. This retires the earlier
"PMID-coverage gap" worry in §9 (it had been based on misread 401 errors). The
captured response is saved as `tests/fixtures/papers_ask_live_response.json`.

**`PaperCitation` fields:**
`citation_number, pmid, doi, title, journal, pub_year, primary_domain,
study_type_hint, evidence_source ('full_text'|'abstract_only'), passage_count,
scores {bm25,dense,intent,rerank}, why[], score_breakdown`.

## 4. Mapping `PaperCitation` → `EvidenceRecord`

`EvidenceRecord` is `id, source, title, text, metadata{}` with `pmid/doi/year`
read from `metadata`. Mapping:

| EvidenceRecord | from PaperCitation |
|---|---|
| `id` | `papers-ask-{pmid}` if pmid else `papers-ask-{slug(title)}-{pub_year}` |
| `source` | `"papers"` |
| `title` | `title` |
| `text` | `title` + journal/year context — see text-hydration note below |
| `metadata.pmid` | `pmid` |
| `metadata.doi` | `doi` |
| `metadata.year` | `pub_year` |
| `metadata.retrieval_source` | `"papers_ask"` |
| `metadata.evidence_source` | `evidence_source` |
| `metadata.rerank` | `scores.rerank` |
| `metadata.study_type_hint`, `primary_domain`, `journal` | passthrough |

Dedup against other retrievers keys on `pmid` (then `doi`, then title) — the
existing builder dedup convention.

**Text hydration.** `PaperCitation` carries bibliographic metadata but **no
passage/abstract text** (PAPERS uses passages internally for synthesis, which
we discard). So a raw PAPERS `EvidenceRecord` has thin `text`, which the
auditor needs to verify claims against. Resolution: when a citation has a
`pmid`, CasePrep hydrates abstract/fulltext through its **existing**
`FullTextHandler` / `PubMedRetriever` — PAPERS supplies the *pointer* (PMID),
CasePrep fetches the *evidence text* it already knows how to fetch. Citations
without a pmid/doi (the weak-key case, §9) cannot be hydrated and are flagged
for down-ranking rather than used as firm evidence.

## 5. The retriever (mirrors `SemanticCorpusRetriever`)

New file `caseprep/retrievers/papers_ask.py`:

```
class PapersAskRetriever:
    def __init__(self, *, base_url, auth, max_papers=8, timeout_s=60, enabled=...):
        ...
    def retrieve(self, query, *, subdomain=None, top_n=8) -> list[EvidenceRecord]:
        # 1. if not enabled or base_url unreachable -> return []
        # 2. POST /v1/ask {question, max_papers, include_figures:false}
        # 3. on non-200 (401/429/timeout) -> log warning, return []
        # 4. map citations -> EvidenceRecord, cap at top_n
```

**Graceful degradation is mandatory** (matches `SemanticCorpusRetriever`):
unreachable service, 401, 429 rate-limit, or timeout → return `[]`, never raise.
The builder already warns when a configured retriever returns zero, so silent
skips stay visible without breaking a briefing.

## 6. Auth (pluggable)

PAPERS enforces auth (`CORPUS_AUTH_ENABLED=1`) with two viable client modes:

1. **Public-API bypass (primary):** when PAPERS runs with
   `ASK_PUBLIC_API_ENABLED=1`, `/v1/ask` needs no credential. The
   retriever sends a plain POST. *(Deployment note: the running container must
   be recreated — `docker compose up -d --force-recreate api` — to load the
   flag. As of this writing the live service still 401s because the container
   predates the flag; live validation is pending this step.)*
2. **Cookie session (fallback):** `POST /login` form `password=…` → signed
   `session` cookie (Starlette `SessionMiddleware`) → reuse via
   `requests.Session`. Password from env, never hard-coded.

Modeled as a small `auth` strategy object (`none` | `cookie`) so the live
choice is config, not a code change. Default `none` (public bypass).

## 7. Configuration (env)

| Var | Default | Meaning |
|---|---|---|
| `CASEPREP_PAPERS_ENABLED` | `0` | master on/off |
| `CASEPREP_PAPERS_BASE_URL` | `http://127.0.0.1:8000` | service base |
| `CASEPREP_PAPERS_AUTH` | `none` | `none` \| `cookie` |
| `CASEPREP_PAPERS_PASSWORD` | — | only if auth=cookie |
| `CASEPREP_PAPERS_MAX_PAPERS` | `8` | request cap |
| `CASEPREP_PAPERS_TIMEOUT_S` | `60` | per-call timeout |

Off by default → zero behaviour change until explicitly enabled.

## 8. Wiring into the build

Construct alongside the others in `build_core_case_plan` (builder.py ~L243),
include in the parallel retrieval set, dedup as today. Because it returns
standard `EvidenceRecord`s, the existing enricher → auditor → provenance path
applies unchanged. No new render path; PAPERS evidence surfaces through the
normal evidence/citations sections after audit.

## 9. Open risks / honest unknowns

1. **No `work_id` in `PaperCitation`.** For OpenAlex-sourced works lacking
   both PMID and DOI, there is **no stable provenance key** — only
   `(title, year)`, which is weak. The clean fix is a small PAPERS change:
   expose `work_id`/`openalex_id` on `PaperCitation` (and in
   `_build_paper_citations`). **Documented as a PAPERS-side dependency.**
   Until then, citations without pmid/doi are tagged
   `metadata.provenance_key="title_year_weak"` so the auditor can down-rank
   or quarantine them rather than treat them as firmly cited.
   *(Note: an earlier attempt to measure PMID coverage was invalid — every
   probe call hit the 401 wall — so no coverage numbers are asserted here.
   Measure coverage once live `/v1/ask` works.)*
2. **Latency / cost.** `/v1/ask` runs full DeepSeek synthesis (~30s) even
   though we discard the prose, and is rate-limited (compose default 10/min
   per IP). Acceptable for an opt-in enrichment; if it bites, a future
   PAPERS retrieval-only endpoint (no synthesis) is the fix.
3. **Live validation pending** the container recreate (§6).

## 10. Test plan

- Unit: `PaperCitation`-JSON fixtures → `EvidenceRecord` mapping (pmid-present,
  pmid-absent/weak-key, empty citations).
- Degradation: unreachable host, 401, 429, timeout → all return `[]`, no raise.
- Dedup: a PAPERS citation sharing a PMID with a PubMed record collapses.
- Integration (gated on live service): one real `/v1/ask` call returns
  ≥1 mappable citation; record the raw payload as a fixture.
- Provenance: a PAPERS-sourced claim passes through the auditor and lands with
  a CasePrep citation; weak-key citations are flagged.

## 11. Out of scope

Synthesized-answer rendering; `/v1/ask-agentic`; figure precision cycle;
replacing the planned pgvector path; any PAPERS code change beyond the
optional `work_id` exposure noted in §9.
