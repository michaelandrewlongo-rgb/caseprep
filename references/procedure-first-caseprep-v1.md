# Procedure-First CasePrep V1 Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Convert CasePrep from topic-centered literature/template generation into a procedure-first, case-centric operative preparation tool for night-before / morning-of-surgery neurosurgical prep.

**Architecture:** A free-text case string is progressively structured into a canonical `CaseSpec`. The core builder uses that structured case plus a small procedure-family taxonomy to drive retrieval, synthesis, rendering, provenance, and evaluation. `caseprep.yaml` is the source of truth; markdown dossier files are the primary user-facing artifact; the dashboard remains secondary.

**Tech Stack:** Python 3.10+, argparse CLI, existing CasePrep core builder/retriever abstractions, pytest, markdown/YAML rendering, optional OpenRouter LLM synthesis through existing `caseprep.llm` path.

---

## 1. Product Target

CasePrep V1 should optimize for a neurosurgery resident or attending preparing for a booked case. The output should be readable in roughly 10-15 minutes and answer:

- What anatomy matters for this procedure?
- What are the approach-specific steps and danger zones?
- What decisions could change the plan?
- What complications should be anticipated and how should they be rescued?
- What evidence or outcomes data meaningfully affects management?
- What critical case facts are missing?

This is not a generic disease summary or literature review. Literature, citations, evidence tables, and future video/visual resources support the operative briefing; they are not the product itself.

## 2. Explicit Non-Goals / Deferred Work

Deferred until after V1 text-dossier quality is proven:

- Surgical video retrieval and ranking.
- Anatomy atlas / visual figure retrieval and ranking.
- Multimodal image/video summarization.
- Citation auto-repair for LLM source-number misattribution.
- YAML-backed procedure taxonomy.
- Full semantic/RAG retrieval redesign.
- PHI handling beyond warnings and local-only storage.
- ML source ranker.

Citation repair is a saved future idea: if a claim cites the wrong `[S#]` but is supported by another source, repair safely only when overlap is strong; numeric claims require the exact number in the replacement source; repairs should be recorded in provenance.

## 3. V1 Canonical Evaluation Cases

Primary quality eval cases:

1. Spine / approach nuance
   - Input: `C5-6 anterior cervical discectomy and fusion for right C6 radiculopathy from foraminal disc osteophyte complex`
   - Must cover: anterior cervical exposure, localization, discectomy/decompression steps, foraminal/uncinate nuance, graft/cage/plate choices, recurrent laryngeal nerve, esophagus, vertebral artery, dysphagia, and when posterior cervical foraminotomy would be preferred.

2. Supratentorial tumor
   - Input: `right frontal convexity meningioma resection near the superior sagittal sinus`
   - Must cover: edema, sinus invasion vs abutment, arterial supply, cortical/bridging veins, craniotomy planning, dural opening, circumferential devascularization, debulking vs extracapsular dissection, brain/venous preservation, dural management/Simpson grade, venous infarct, seizures, hemorrhage, edema, neurologic deficit, and selected alternatives such as observation/SRS.

3. Chiari decompression
   - Input: `suboccipital craniectomy and C1 laminectomy for Chiari I malformation with syringomyelia`
   - Must cover: foramen magnum anatomy, tonsils, obex, PICA, brainstem, upper cervical cord, decompression extent, C1 laminectomy, bone-only vs duraplasty, arachnoid opening risks/benefits, selective tonsillar reduction, syrinx as a modifier, CSF leak, pseudomeningocele, aseptic meningitis, and craniocervical instability.

4. Endovascular stroke
   - Input: `mechanical thrombectomy for acute ischemic stroke due to right M1 middle cerebral artery occlusion`
   - Must cover: M1/M2 anatomy, lenticulostriate/perforator risk, femoral/radial access acknowledgement, guide catheter / balloon guide / distal access catheter concepts, aspiration vs stent retriever vs combined technique, first-pass effect, TICI/mTICI, time window / imaging selection, vessel perforation, dissection, distal emboli, symptomatic ICH, vasospasm, access complications, IV thrombolysis if eligible, medical management when not eligible, and rescue angioplasty/stenting only in appropriate context.

Parser/degraded-mode tests:

- `vestibular schwannoma`
- `MCA aneurysm`
- `cervical radiculopathy`
- `Chiari`
- `stroke thrombectomy`

Degraded-mode tests pass if they identify what they can, avoid pretending a procedure/approach is known, list missing critical facts, and label the output as generic/degraded.

## 4. V1 Quality Rubric

Score generated full-case outputs on a 100-point scale:

- 25 pts: Procedure-specific technique — steps, sequence, decisions, technical nuance.
- 20 pts: Anatomy at risk — named structures, approach-relevant relationships, danger zones.
- 15 pts: Complications and rescue — likely/catastrophic complications, prevention, intraop/postop response.
- 10 pts: Alternatives / decision boundaries — why this approach, when plan changes.
- 10 pts: Evidence and outcomes — relevant rates/landmark evidence, cited and not fabricated.
- 10 pts: Case-specificity / missing facts — uses parsed modifiers, flags missing plan-changing details.
- 5 pts: Readability — concise operative prep, not citation dump.
- 5 pts: Source attribution / provenance — citations trace to source, uncertainty labeled.

Pass threshold:

- Overall score >= 75.
- No zero in technique, anatomy, or complications.
- No fabricated numerical claims.
- No blank or generic major section.

Raw extracted snippets may be written as a degraded fallback, but do not count as passing V1 quality. Narrative synthesis is required for a passing V1 dossier.

## 5. Canonical Internal Model

The canonical object is a case, not a topic. The CLI may still accept one free-text string, but internally the builder should operate on a structured case object.

Proposed interfaces:

```python
@dataclass(frozen=True)
class CaseField:
    value: str | None
    confidence: float
    source: str  # extracted | synonym | inferred | llm | missing
    span: str | None = None
    notes: str | None = None

@dataclass(frozen=True)
class CaseSpec:
    raw_input: str
    pathology: CaseField
    procedure: CaseField
    approach: CaseField
    procedure_family: CaseField
    broad_profile: CaseField
    laterality: CaseField
    level_or_segment: CaseField
    size: CaseField
    anatomic_location: CaseField
    patient_modifiers: tuple[CaseField, ...]
    imaging_modifiers: tuple[CaseField, ...]
    missing_critical_facts: tuple[str, ...]
    degraded: bool
    degradation_reason: str | None = None
```

Important rules:

- Preserve `raw_input` in local `caseprep.yaml` for auditability and reproducibility.
- Warn users not to include PHI.
- Do not silently guess uncertain fields.
- Medium-confidence inferred fields may be used for retrieval if marked uncertain.
- Low-confidence/missing procedure or approach should produce a visibly degraded generic build.

## 6. Procedure-Family Taxonomy

Add a small Python taxonomy first. Do not move to YAML until concepts stabilize.

Proposed file:

- Create: `caseprep/procedure_taxonomy.py`

Proposed interface:

```python
@dataclass(frozen=True)
class ProcedureFamily:
    id: str
    display_name: str
    broad_profile: str
    procedure_aliases: tuple[str, ...]
    pathology_aliases: tuple[str, ...]
    approach_aliases: tuple[str, ...]
    required_fields: tuple[str, ...]
    missing_fact_prompts: tuple[str, ...]
    retrieval_templates: dict[str, str]
    section_headings: dict[str, tuple[str, ...]]
    eval_required_concepts: tuple[str, ...]
```

Initial V1 families:

- `spine_acdf` -> broad profile `spine`
- `tumor_convexity_meningioma` -> broad profile `supratentorial_tumor`
- `posterior_fossa_chiari` -> broad profile `posterior_fossa` or `congenital`
- `endovascular_thrombectomy` -> broad profile `vascular`

Each family should contain aliases, required fields, missing-fact prompts, retrieval templates, section headings, and eval-required concepts.

## 7. Hybrid Parser Strategy

Add deterministic parsing first; add LLM enrichment as optional/fallback later in the same seam.

Proposed file:

- Create: `caseprep/case_parser.py`

Proposed functions:

```python
def parse_case_input(raw_input: str, *, use_llm: bool = False) -> CaseSpec:
    """Parse free-text procedure/case input into CaseSpec."""


def deterministic_parse_case(raw_input: str) -> CaseSpec:
    """Extract high-confidence fields via aliases, regex, and taxonomy."""


def select_procedure_family(case: CaseSpec) -> ProcedureFamily | None:
    """Select the best procedure family from parsed procedure/pathology/approach."""
```

Deterministic parser should extract:

- Procedures/approaches: ACDF, anterior cervical, posterior foraminotomy, craniotomy/resection, suboccipital decompression, C1 laminectomy, mechanical thrombectomy.
- Pathologies: cervical radiculopathy, disc osteophyte complex, convexity meningioma, Chiari I, syringomyelia, acute ischemic stroke, M1 occlusion.
- Laterality: right, left, bilateral.
- Levels/segments: C5-6, C6, M1, frontal convexity.
- Modifiers: near superior sagittal sinus, syringomyelia, serviceable hearing, ruptured/unruptured, foraminal, etc.

LLM parser/enricher, when added, must return confidence/provenance and must not overwrite high-confidence deterministic fields unless explicitly better and traceable.

## 8. Build Request / Core Builder Integration

Modify the core path, not the legacy MCP handler, for new procedure-first work.

Relevant files:

- Modify: `caseprep/core/contracts.py`
- Modify: `caseprep/core/builder.py`
- Modify: `caseprep/schema.py`
- Modify: `caseprep/renderers/markdown.py` if needed
- Modify: `caseprep/adapters/caseplan.py` if MCP/web adapter conversion is needed

`BuildCasePlanRequest` should remain backward compatible but gain a case-input seam:

```python
@dataclass(frozen=True)
class BuildCasePlanRequest:
    topic: str | None = None
    case_input: str | None = None
    output_dir: Path | None = None
    max_per_category: int = 3
    profile_hint: str | None = None
    # existing fields preserved
```

Builder behavior:

1. Resolve raw case input:
   - `case_input` if present.
   - else `topic` for compatibility.
2. Parse into `CaseSpec`.
3. Select procedure family.
4. Derive broad profile from procedure family, not from topic-only profile classifier when possible.
5. Generate retrieval axes from `CaseSpec` + `ProcedureFamily`.
6. Retrieve evidence.
7. Apply simple surgical-usefulness source ranking.
8. Synthesize sections.
9. Render `caseprep.yaml`, markdown dossier, and provenance.
10. Persist if configured.

## 9. Procedure-Aware Retrieval

Minimum V1 retrieval changes should use `CaseSpec`; do not rebuild the retriever stack.

Proposed function:

```python
@dataclass(frozen=True)
class RetrievalAxis:
    id: str
    label: str
    query: str
    filter_type: str | None = None


def build_case_queries(case: CaseSpec, family: ProcedureFamily | None) -> list[RetrievalAxis]:
    """Build PubMed/corpus query axes from structured case fields."""
```

Axes should include:

- Anatomy / relevant structures.
- Outcomes / evidence.
- Surgical technique.
- Complications.
- Reviews / landmarks.

Use procedure-family templates such as:

- anatomy: `{approach} {pathology} anatomy {anatomic_location}`
- technique: `{procedure} {approach} technique operative steps`
- complications: `{procedure} {pathology} complications`
- outcomes: `{pathology} {procedure} outcomes`
- reviews: `{pathology} {procedure} systematic review`

Evidence records should carry metadata:

- axis
- query
- procedure_family
- broad_profile
- surgical_usefulness_score
- score_reasons

## 10. Surgical-Usefulness Ranking

Start with simple inspectable heuristics. Do not add an ML ranker in V1.

Proposed file:

- Create or modify: `caseprep/scoring.py`

Proposed function:

```python
def surgical_usefulness_score(
    record: EvidenceRecord,
    case: CaseSpec,
    family: ProcedureFamily | None,
    axis: str,
) -> tuple[int, list[str]]:
    """Return transparent source-usefulness score and reasons."""
```

Suggested features:

- +30 exact procedure/approach phrase in title.
- +20 pathology phrase in title.
- +15 technique terms in title/abstract.
- +15 complication/outcome terms when matching that axis.
- +10 anatomy/location terms.
- +10 technical note / operative series / review depending on axis.
- -20 off-domain drug-only/basic-science content.
- -20 irrelevant non-neurosurgical context.

## 11. CLI Build Command

Add an explicit build command. Do not overload `generate`.

Relevant file:

- Modify: `caseprep/cli.py`

Desired command:

```bash
caseprep build "C5-6 anterior cervical discectomy and fusion for right C6 radiculopathy from foraminal disc osteophyte complex" -o ~/cases/acdf
```

Behavior:

- Parses free-text case string into `CaseSpec`.
- Runs core builder.
- Writes populated dossier folder.
- Writes `caseprep.yaml` and `provenance.json`.
- Prints:
  - output path
  - pathology/procedure/approach/profile/family
  - missing critical facts
  - source counts
  - warnings/degradation status
  - quality/eval status if available

Compatibility:

- `caseprep generate <topic>` remains blank scaffold.
- Bare `caseprep <topic>` may remain `generate` for now to avoid breaking existing behavior.
- MCP/web should later call the same core builder path.

## 12. Rendering Requirements

`caseprep.yaml` should include the structured case object.

Markdown should include a clear case summary section containing:

- Raw case input.
- Parsed pathology.
- Parsed procedure.
- Parsed approach.
- Procedure family.
- Broad profile.
- Parsed modifiers.
- Missing critical facts.
- Degradation status, if any.

If procedure/approach is missing or low-confidence:

- Label as generic/degraded.
- Do not imply the system knows the booked approach.
- Retrieval should avoid over-specific approach terms.

## 13. LLM Synthesis and Degradation Policy

V1 passing output requires narrative synthesis.

If LLM synthesis succeeds and guardrails pass:

- Write coherent procedure-specific prose explaining HOW/WHY.
- Ground claims with citations.
- Avoid citation-dump factoids.

If LLM unavailable, too slow, or guardrails reject:

- Build should still complete.
- Write parsed case summary, evidence table, extracted source snippets, missing critical facts, and quality/degradation report.
- Label clearly:
  - `Synthesis unavailable` or `Synthesis rejected by guardrail`.
  - `This is not a finished operative briefing`.
- CLI prints warning.
- Eval harness treats this as V1 quality fail even though runtime degradation is acceptable.

Citation repair is not implemented in V1. Citation failures remain visible diagnostics.

## 14. Evaluation Harness

Make evaluation first-class in the repo.

Proposed files:

- Create: `caseprep/evaluation/__init__.py`
- Create: `caseprep/evaluation/canonical_cases.py`
- Create: `caseprep/evaluation/rubric.py`
- Create: `caseprep/evaluation/fixtures/`
- Create: `tests/test_case_parser.py`
- Create: `tests/test_procedure_taxonomy.py`
- Create: `tests/test_canonical_eval.py`

Proposed interfaces:

```python
@dataclass(frozen=True)
class CanonicalCase:
    id: str
    input_text: str
    expected_family: str | None
    required_concepts: tuple[str, ...]
    degraded: bool = False

@dataclass(frozen=True)
class EvalReport:
    case_id: str
    passed: bool
    score: int | None
    missing_required_concepts: tuple[str, ...]
    deterministic_failures: tuple[str, ...]
    degradation_status: str | None
    output_dir: str | None


def evaluate_case_output(output_dir: Path, canonical_case: CanonicalCase) -> EvalReport:
    """Run deterministic output checks for a generated dossier."""
```

Minimum deterministic checks:

- No blank placeholder text in major rendered sections.
- Parsed family matches expected family for full canonical cases.
- Degraded parser cases are labeled degraded.
- Required concepts appear in the relevant output files.
- Evidence table is non-empty for full canonical cases.
- Missing critical facts section exists.
- No fabricated numbers according to existing numeric guardrail where applicable.

For major pipeline changes, run blind neurosurgeon-style subagent review with no prior context. Optionally run ML-engineer review for retrieval/token/eval design.

## 15. Implementation Tasks

### Task 1: Add procedure taxonomy module

**Objective:** Create the small V1 procedure-family taxonomy.

**Files:**
- Create: `caseprep/procedure_taxonomy.py`
- Test: `tests/test_procedure_taxonomy.py`

**Steps:**
1. Write tests asserting the four V1 family IDs exist.
2. Write tests asserting each family has broad profile, aliases, missing-fact prompts, retrieval templates, and eval concepts.
3. Implement `ProcedureFamily` and taxonomy constants.
4. Add lookup helpers by alias/family ID.
5. Run `python3 -m pytest tests/test_procedure_taxonomy.py -v`.

### Task 2: Add deterministic case parser

**Objective:** Parse free-text case inputs into `CaseSpec` with confidence/provenance.

**Files:**
- Create: `caseprep/case_parser.py`
- Test: `tests/test_case_parser.py`

**Steps:**
1. Write parser tests for the four canonical full cases.
2. Write degraded-input tests for topic-only strings.
3. Implement `CaseField`, `CaseSpec`, deterministic regex/alias extraction, and family selection.
4. Ensure no-silent-guessing behavior for missing procedure/approach.
5. Run `python3 -m pytest tests/test_case_parser.py -v`.

### Task 3: Extend core contracts for case input

**Objective:** Allow `BuildCasePlanRequest` to carry `case_input` while preserving compatibility.

**Files:**
- Modify: `caseprep/core/contracts.py`
- Test: `tests/test_core_engine.py` or `tests/test_core_builder.py`

**Steps:**
1. Write tests for `BuildCasePlanRequest(case_input=...)`.
2. Write tests that `topic` still works as fallback.
3. Add new field and validation rules.
4. Run relevant core tests.

### Task 4: Integrate parser into core builder

**Objective:** Make `build_core_case_plan()` parse the case and use family/profile from `CaseSpec`.

**Files:**
- Modify: `caseprep/core/builder.py`
- Test: `tests/test_core_builder.py`

**Steps:**
1. Add tests using fixture retrievers to assert structured case appears in `result.structured`.
2. Add tests that family-derived profile overrides topic-only broad classifier when available.
3. Add parser call near the start of `build_core_case_plan()`.
4. Add `case` and `procedure_family` to structured output.
5. Run `python3 -m pytest tests/test_core_builder.py -v`.

### Task 5: Add procedure-aware retrieval axes

**Objective:** Generate PubMed/corpus query axes from `CaseSpec` + `ProcedureFamily`.

**Files:**
- Modify: `caseprep/core/builder.py` or create `caseprep/retrieval_planning.py`
- Test: `tests/test_core_builder.py` or new `tests/test_retrieval_planning.py`

**Steps:**
1. Write tests for query generation for each canonical case.
2. Implement `RetrievalAxis` and `build_case_queries()`.
3. Replace raw-topic axis construction in core builder with procedure-aware axes.
4. Preserve existing filters where appropriate.
5. Run tests.

### Task 6: Add surgical-usefulness scoring

**Objective:** Score and sort evidence with transparent reasons.

**Files:**
- Modify: `caseprep/scoring.py`
- Modify: `caseprep/core/builder.py`
- Test: `tests/test_scoring.py` or `tests/test_core_builder.py`

**Steps:**
1. Write tests where exact procedure title outranks generic disease title.
2. Implement scoring function returning score and reasons.
3. Attach score metadata to records.
4. Sort records within axes by score where possible.
5. Run scoring/core tests.

### Task 7: Render structured case summary

**Objective:** Include parsed case and missing facts in `caseprep.yaml` and markdown.

**Files:**
- Modify: `caseprep/schema.py`
- Modify: `caseprep/renderers/markdown.py`
- Test: `tests/test_renderers.py` and/or `tests/test_core_builder.py`

**Steps:**
1. Write tests asserting `caseprep.yaml` contains the structured case object.
2. Write tests asserting markdown includes parsed procedure/family/missing facts.
3. Implement schema additions and renderer output.
4. Run renderer/core tests.

### Task 8: Add explicit CLI build command

**Objective:** Add `caseprep build "..."` that invokes the core builder.

**Files:**
- Modify: `caseprep/cli.py`
- Test: `tests/test_cli.py`

**Steps:**
1. Write CLI tests for `build` argument parsing.
2. Mock core builder and assert it receives `case_input` and `output_dir`.
3. Implement `_cmd_build` and parser subcommand.
4. Keep `generate` and bare topic compatibility unchanged.
5. Run `python3 -m pytest tests/test_cli.py -v`.

### Task 9: Add canonical eval harness

**Objective:** Make canonical cases and deterministic output checks first-class.

**Files:**
- Create: `caseprep/evaluation/__init__.py`
- Create: `caseprep/evaluation/canonical_cases.py`
- Create: `caseprep/evaluation/rubric.py`
- Test: `tests/test_canonical_eval.py`

**Steps:**
1. Define `CanonicalCase` constants for four full cases and degraded parser cases.
2. Implement deterministic checks for placeholders, required concepts, evidence table, degradation labels, and missing facts.
3. Write tests against small temp output folders.
4. Run `python3 -m pytest tests/test_canonical_eval.py -v`.

### Task 10: End-to-end smoke with fixture retrievers

**Objective:** Verify the pipeline can generate deterministic dossier outputs for the four canonical cases.

**Files:**
- Modify/Create tests as needed under `tests/`
- Optional fixture files under `caseprep/evaluation/fixtures/`

**Steps:**
1. Create fixture retrievers returning stable records for each canonical case.
2. Run `build_core_case_plan()` into `tmp_path` for each case.
3. Run eval harness against the generated folder.
4. Assert no blank/generic major section and required concepts present.
5. Run `python3 -m pytest tests/test_canonical_eval.py tests/test_core_builder.py -v`.

## 16. Verification Commands

During implementation, run targeted tests after each task. Before declaring V1 slice complete, run:

```bash
cd /home/michael/projects/caseprep
python3 -m pytest tests/test_case_parser.py tests/test_procedure_taxonomy.py tests/test_core_builder.py tests/test_cli.py tests/test_canonical_eval.py -v
python3 -m pytest -v
```

For real output quality after implementation, run live builds for the four canonical cases and inspect the generated markdown, not just test results.

## 17. Acceptance Criteria

V1 implementation is accepted when:

- `caseprep build "..."` exists and invokes the core builder.
- The four canonical full-case strings parse into the expected procedure families.
- Degraded topic-only strings are labeled degraded and list missing critical facts.
- `caseprep.yaml` includes structured case data and provenance.
- Markdown dossier includes parsed case summary, missing facts, evidence table, and procedure-specific sections.
- Retrieval queries are generated from `CaseSpec` + procedure family, not raw topic alone.
- Evidence records include transparent surgical-usefulness scores/reasons.
- Fixture-backed canonical eval runs deterministically.
- LLM unavailable/guardrail failure completes as degraded output, not a crash.
- Passing V1 quality requires narrative synthesized output, not raw snippets.

## 18. Implementation Guidance

Keep implementation small and sequential:

1. Taxonomy.
2. Parser.
3. Core request seam.
4. Builder integration.
5. Retrieval planning.
6. Source scoring.
7. Rendering.
8. CLI build.
9. Eval harness.
10. Fixture-backed end-to-end checks.

Do not mix in deferred video/visual retrieval, citation repair, YAML taxonomy, or RAG redesign while implementing this plan.
