# Fix CasePrep Pipeline: Make `build_caseplan` Produce Surgically Useful Output

## Goal

Make the `build_caseplan` pipeline produce populated, surgically useful anatomy.md, approach.md, and complications.md files instead of the current state: 67% "Insufficient data" placeholders, blank GBM anatomy, and raw-sentence dumps for complications.

## Current Context

### What works
- PubMed search fetches real papers with abstracts (README.md, literature.md are populated)
- 14 unit tests pass (but none test the template-filling pipeline end-to-end)
- The pipeline runs end-to-end without crashing
- Guardrail footers appear where synthesis succeeds ("All 2 claims verified")
- The `/tmp` outputs from a prior LLM-as-judge evaluation confirm the pipeline actually runs

### What's broken (from prior LLM-as-judge evaluation, May 19)
- **GBM anatomy.md: completely blank** — zero sentences extracted, zero claims synthesized
- **Complications: LLM synthesis fails for ALL 3 topics** — falls back to raw unsorted source sentences
- **67% of subsections say "Insufficient data"** — keyword extraction too narrow
- **Jaccard guardrail provides false confidence** — 0.15 threshold is bag-of-words, not semantic
- **"0/0 claims" pathological message** — when LLM produces no bullet lines
- **Blank templates have no diagnostic signal** — indistinguishable from pre-run scaffolds
- **Duplicate articles across search axes** waste extraction capacity

### Root cause hierarchy (highest → lowest leverage)
1. **Keyword lists are skull-base-biased** — supratentorial/vascular/spinal topics get near-zero extraction
2. **LLM synthesis timeouts** — 30s timeout + 1200 max_tokens too tight for complications
3. **min_score=2 is too strict** — single-keyword sentences discarded even when informative
4. **No topic-aware keyword selection** — static lists regardless of topic domain
5. **Guardrail is cosmetic** — Jaccard 0.15 passes fabricated statistics

## Proposed Approach

Fix in priority order — each fix is independently testable and incrementally improves output quality.

### Phase 1: Keyword extraction (highest leverage)
The keyword lists are the single biggest bottleneck. If sentences aren't extracted, nothing downstream works.

### Phase 2: LLM synthesis reliability
Fix the timeout/token limits so complications synthesis actually completes.

### Phase 3: Extraction tuning
Lower thresholds, increase caps, add fallback retries.

### Phase 4: Guardrail honesty
Make the verification actually meaningful instead of cosmetic.

### Phase 5: Diagnostic signals
Add footers/telemetry so blank outputs aren't silent failures.

## Step-by-Step Plan

### Step 1: Add topic-adaptive keyword profiles
**File:** `caseprep/mcp_server.py` (lines ~876-940)

- Replace the current monolithic `_ANATOMY_KEYWORDS`, `_APPROACH_KEYWORDS`, `_COMPLICATIONS_KEYWORDS` with a **profile system** that selects + merges keywords based on topic classification
- Add these profiles:
  - **skull_base**: current keywords (CPA, temporal bone, CN VII/VIII, petrous, sigmoid, cistern)
  - **supratentorial**: eloquent cortex, frontal/temporal/parietal/occipital lobe, Broca, Wernicke, insula, corpus callosum, basal ganglia, thalamus, corticospinal, arcuate, precentral, postcentral, motor cortex
  - **vascular**: aneurysm, AComA, PComA, MCA, ICA, ACA, basilar, circle of Willis, clip, coil, parent vessel, neck, dome, fundus, SAH
  - **spinal**: vertebra, disc, canal, cord, root, lamina, pedicle, facet, duramater, myelopathy, radiculopathy
  - **posterior_fossa**: cerebellum, brainstem, fourth ventricle, foramen magnum, odontoid, cranial nerve, CN IX/X/XI/XII
- Topic detection: keyword matching in topic string (e.g., "glioblastoma" → supratentorial, "aneurysm" → vascular)
- Base keywords always included; profile keywords merged on top
- **Existing profile files at** `caseprep/profiles/` may already have some of this — check and extend rather than duplicate

### Step 2: Lower extraction thresholds + increase caps
**File:** `caseprep/mcp_server.py` (lines ~945-960)

- Change `min_score` from 2 to 1 (with sentence length filter >= 80 chars to avoid fragments)
- Increase `max_per_article` from 2 to 3
- Increase `max_sentences` from 8 to 12
- Add fallback: if extracted < 4 sentences, retry with `min_score=1` and broader keyword match

### Step 3: Fix LLM synthesis timeout + token limits
**File:** `caseprep/llm.py`

- Increase timeout from 30s to 60s
- Increase `max_tokens` from 1200 to 2000 for complications (largest template with 4 subsections)
- Add retry with exponential backoff (2 attempts, 5s delay)
- Log the specific exception type (timeout vs HTTP error vs empty response) to stderr

### Step 4: Fix guardrail false-confidence issues
**File:** `caseprep/llm.py` (guardrail functions)

- **Numeric fidelity sub-check**: Extract all numbers (percentages, n= values, odds ratios, confidence intervals) from each claim using regex. Verify each number appears verbatim in at least one source sentence. Flag claims with numbers not in sources regardless of Jaccard score.
- **Citation-specific verification**: Parse [S*] reference from each claim before stripping. Verify the claim specifically against THAT source sentence. Only fall back to best-match if no citation present.
- Raise Jaccard threshold from 0.15 to 0.25 for a slightly tighter filter.

### Step 5: Fix "0/0 claims" edge case + blank template diagnostics
**File:** `caseprep/mcp_server.py` (lines ~1002-1021 in `_populate_section`)

- When `result.total_count == 0`, emit: "LLM synthesis produced no verifiable claims. Showing raw source sentences instead."
- When `_extract_relevant_sentences` returns 0 hits, add diagnostic footer: `> *No sentences matching [section] keywords found in {N} search results. Consider broadening the search or adding relevant source material.*`
- In `_extract_claims`, add fallback: if no bullet/list lines found, treat every line >= 20 chars (excluding headers) as a claim

### Step 6: Deduplicate articles across search axes
**File:** `caseprep/mcp_server.py` (in `_handle_build_caseplan`)

- Before distributing articles to section keyword extraction, deduplicate by PMID
- For articles appearing in multiple axes, assign to the most relevant section (technique → approach, complication → complications, review → anatomy)

## Files Likely to Change

| File | Changes |
|------|---------|
| `caseprep/mcp_server.py` | Steps 1, 2, 5, 6 — keyword profiles, extraction tuning, diagnostics, dedup |
| `caseprep/llm.py` | Steps 3, 4 — timeout/tokens, guardrail fixes |
| `caseprep/profiles/*.py` or `.yaml` | Step 1 — profile keyword definitions (check existing first) |
| `tests/test_pipeline.py` (new) | End-to-end test for template filling |

## Tests / Validation

After each step:

1. **Unit test**: Run `pytest` — existing 14 tests must still pass
2. **Integration smoke test**: Run `build_caseplan` on one topic and read the 3 template files:
   ```bash
   cd ~/projects/caseprep && python3 -c "
   import asyncio
   from caseprep.mcp_server import _handle_build_caseplan
   async def main():
       await _handle_build_caseplan({'topic': 'glioblastoma resection', 'max_per_category': 3, 'output_dir': '/tmp/gbm-smoke'})
   asyncio.run(main())
   "
   cat /tmp/gbm-smoke/anatomy.md
   cat /tmp/gbm-smoke/approach.md
   cat /tmp/gbm-smoke/complications.md
   ```
3. **Quality regression**: Compare new output against the prior LLM-judge baseline
   - Target: anatomy.md has ≥3 non-blank subsections (vs 0 currently for GBM)
   - Target: complications.md shows synthesized claims, not raw sentences
   - Target: guardrail footers include numeric-fidelity results

4. **Cross-topic validation**: Run `build_caseplan` on at least 2 different domains:
   - Skull-base topic (e.g., "vestibular schwannoma") — should maintain/improve current quality
   - Supratentorial topic (e.g., "glioblastoma resection") — should show dramatic improvement
   - Vascular topic (e.g., "AComA aneurysm clipping") — should show improvement

## Risks and Tradeoffs

| Risk | Mitigation |
|------|------------|
| Lowering min_score to 1 may extract noise/fragments | Add sentence length filter (>=80 chars) |
| More keywords + more sentences = higher LLM cost | Increase is modest (8→12 sentences); cost per call is cents |
| Topic detection heuristics may misclassify | Use conservative keyword matching; fall back to base profile |
| Higher timeout (60s) slows failed cases | Only applies when 30s wasn't enough; retry helps avoid wasted waits |
| Numeric fidelity regex may miss valid number formats | Start with %, n=, CI, OR, HR patterns — extend as needed |
| Guardrail changes may reject previously-passing claims | Raise threshold gradually (0.15→0.25); log rejects for review |

## Open Questions

1. **Should profile keyword lists live in Python code or YAML files?** YAML is more surgeon-editable but adds a file-loading dependency. Python dicts are simpler and already in the codebase.
2. **Should we add a CLI `build` command?** Currently only accessible via MCP or web API. Adding `caseprep build <topic>` to the CLI would make testing easier.
3. **Should the LLM model be configurable?** Currently hardcoded in `llm.py`. Different models have different cost/quality tradeoffs.
4. **Should we persist extracted sentences alongside the templates?** Currently lost after `_populate_section` runs. Storing them would enable re-running synthesis without re-fetching papers.

## Estimated Effort

| Step | Effort | Impact |
|------|--------|--------|
| 1. Topic-adaptive profiles | 2-3h | **Highest** — unlocks all non-skull-base topics |
| 2. Lower thresholds + caps | 30min | High — immediately doubles extraction yield |
| 3. Fix LLM timeouts | 30min | High — fixes complications synthesis entirely |
| 4. Guardrail honesty | 1-2h | Medium — prevents misleading "verified" footers |
| 5. Diagnostics | 30min | Medium — makes silent failures visible |
| 6. Dedup articles | 30min | Low-Medium — modest quality gain |

**Total: ~5-7h.** Steps 1-3 alone (3-4h) would transform the pipeline from mostly-blank to mostly-populated.
