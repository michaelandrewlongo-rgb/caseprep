# CasePrep Schema Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace generic case-prep markdown scaffolds with a canonical neurosurgical case dossier schema that renders structured, surgeon-facing markdown while preserving the current file-based workflow.

**Architecture:** Add `caseprep/schema.py` as the source for a versioned `caseprep.yaml` dossier, profile extensions, provenance records, and deterministic markdown rendering. Wire the static generator and MCP `build_caseplan` output through the same schema renderer, keeping legacy filenames as compatibility aliases during the transition. Existing PubMed retrieval and LLM synthesis stay in place, but their output is placed inside the new dossier structure instead of being the only artifact.

**Tech Stack:** Python 3.10+ stdlib, existing `pydantic` dependency only if later validation is needed, pytest, current markdown file outputs. No new runtime dependency is required for YAML; `caseprep.yaml` will be emitted with a small deterministic YAML writer for simple dict/list/scalar values.

---

## Scope Check

This plan implements the first shippable schema slice:

- Canonical machine-readable dossier: `caseprep.yaml`
- Provenance audit file: `provenance.json`
- Canonical markdown files:
  - `README.md`
  - `01-case-summary.md`
  - `02-imaging-review.md`
  - `03-anatomy-at-risk.md`
  - `04-operative-plan.md`
  - `05-risk-and-rescue.md`
  - `06-postop-plan.md`
  - `07-evidence.md`
  - `08-checklists.md`
  - `09-open-questions.md`
  - `resource-links.html`
- Compatibility markdown files:
  - `anatomy.md`
  - `approach.md`
  - `complications.md`
  - `literature.md`

Out of scope for this plan:

- A full web UI redesign.
- Storing the complete dossier in SQLite.
- Full patient-specific data ingestion from EHR, DICOM, or operative reports.
- Deep profile-specific content for every subspecialty. The first version includes profile hooks and one richer `skull_base` extension, with lighter extensions for the other existing profiles.

## File Structure

- Create `caseprep/schema.py`
  - Owns dossier defaults, profile extension defaults, provenance records, YAML/JSON emission, and markdown rendering.
- Modify `caseprep/generator.py`
  - Replaces the old static `TEMPLATES` loop with schema rendering.
  - Keeps the return value as `resource-links.html`.
- Modify `caseprep/mcp_server.py`
  - Uses schema rendering inside `_write_filled_templates`.
  - Maps populated anatomy/approach/complication synthesis into canonical files and legacy aliases.
  - Converts PubMed axis data into evidence citations.
- Modify `caseprep/llm.py`
  - Changes synthesis prompt from prose-only to checklist-compatible output.
  - Extracts prompt construction into a testable helper.
- Modify `tests/test_generator.py`
  - Adds canonical file assertions while preserving legacy file assertions.
- Create `tests/test_case_schema.py`
  - Tests schema creation, rendering, evidence conversion, and provenance output.
- Modify `tests/test_template_population.py`
  - Adds `_write_filled_templates` assertions for canonical files and legacy aliases.
- Modify `tests/test_web.py`
  - Adds a light assertion that build responses expose the output directory and canonical file names in the returned summary.
- Modify `README.md`
  - Documents the new file layout and the status/provenance distinction.

## Canonical Schema Contract

The dossier object is a Python `dict` with this top-level shape:

```python
{
    "schema_version": "0.2",
    "topic": "retrosigmoid vestibular schwannoma",
    "case_profile": "skull_base",
    "status": "draft",
    "case": {
        "case_snapshot": {...},
        "indication_and_decision": {...},
        "patient_context": {...},
        "imaging_review": {...},
        "anatomy_at_risk": {...},
        "operative_plan": {...},
        "risk_and_rescue": {...},
        "postop_plan": {...},
        "evidence": {...},
        "verification": {...},
    },
    "profile_extensions": {
        "skull_base": {...}
    },
    "citations": [],
    "provenance": []
}
```

Every generated value should be visibly one of:

- `generated`: deterministic scaffold or tool-generated content.
- `inferred`: inferred from topic/profile.
- `cited`: supported by a PubMed/corpus citation.
- `user_entered`: entered by clinician/user.
- `verified`: manually verified.
- `needs_verification`: clinical content that must be checked before use.

---

### Task 1: Add Core Schema Builder And Renderer

**Files:**
- Create: `caseprep/schema.py`
- Create: `tests/test_case_schema.py`

- [ ] **Step 1: Write failing schema tests**

Create `tests/test_case_schema.py` with:

```python
"""Tests for the CasePrep v0.2 case dossier schema and renderer."""

from __future__ import annotations

import json

from caseprep.schema import (
    CANONICAL_MARKDOWN_FILES,
    LEGACY_MARKDOWN_ALIASES,
    build_caseprep_schema,
    render_caseprep_files,
)


def test_build_caseprep_schema_has_core_sections():
    schema = build_caseprep_schema(
        "retrosigmoid vestibular schwannoma",
        profile="skull_base",
    )

    assert schema["schema_version"] == "0.2"
    assert schema["topic"] == "retrosigmoid vestibular schwannoma"
    assert schema["case_profile"] == "skull_base"
    assert schema["status"] == "draft"

    case = schema["case"]
    for section in [
        "case_snapshot",
        "indication_and_decision",
        "patient_context",
        "imaging_review",
        "anatomy_at_risk",
        "operative_plan",
        "risk_and_rescue",
        "postop_plan",
        "evidence",
        "verification",
    ]:
        assert section in case

    skull_base = schema["profile_extensions"]["skull_base"]
    assert "cranial_nerves" in skull_base
    assert "facial_nerve_status" in skull_base["cranial_nerves"]
    assert schema["provenance"]
    assert schema["provenance"][0]["value_status"] == "generated"


def test_render_caseprep_files_contains_canonical_and_legacy_files():
    schema = build_caseprep_schema(
        "retrosigmoid vestibular schwannoma",
        profile="skull_base",
    )
    files = render_caseprep_files(schema)

    for filename in CANONICAL_MARKDOWN_FILES:
        assert filename in files, f"missing canonical file {filename}"

    for filename in LEGACY_MARKDOWN_ALIASES:
        assert filename in files, f"missing legacy file {filename}"

    assert "caseprep.yaml" in files
    assert "provenance.json" in files
    assert "## Preparation Status" in files["README.md"]
    assert "## Imaging Review Checklist" in files["02-imaging-review.md"]
    assert "## Anatomy At Risk" in files["03-anatomy-at-risk.md"]
    assert "## Approach Selection Matrix" in files["04-operative-plan.md"]
    assert "## Rescue Triggers" in files["05-risk-and-rescue.md"]
    assert "## Immediate Postop Orders" in files["06-postop-plan.md"]
    assert "## Clinical Questions" in files["07-evidence.md"]
    assert "## Day-Of Safety Checklist" in files["08-checklists.md"]
    assert "## Attending / Team Questions" in files["09-open-questions.md"]

    provenance = json.loads(files["provenance.json"])
    assert provenance[0]["field_path"] == "case.case_snapshot"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_case_schema.py -q
```

Expected: failure with `ModuleNotFoundError: No module named 'caseprep.schema'`.

- [ ] **Step 3: Create schema module**

Create `caseprep/schema.py` with:

```python
"""CasePrep v0.2 structured case dossier schema and markdown renderer."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any


SCHEMA_VERSION = "0.2"
DEFAULT_STATUS = "draft"

CANONICAL_MARKDOWN_FILES = [
    "README.md",
    "01-case-summary.md",
    "02-imaging-review.md",
    "03-anatomy-at-risk.md",
    "04-operative-plan.md",
    "05-risk-and-rescue.md",
    "06-postop-plan.md",
    "07-evidence.md",
    "08-checklists.md",
    "09-open-questions.md",
]

LEGACY_MARKDOWN_ALIASES = {
    "anatomy.md": "03-anatomy-at-risk.md",
    "approach.md": "04-operative-plan.md",
    "complications.md": "05-risk-and-rescue.md",
    "literature.md": "07-evidence.md",
}


def _empty_source_refs() -> list[str]:
    return []


def _generated_at() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _profile_extensions(profile: str) -> dict[str, Any]:
    extensions: dict[str, dict[str, Any]] = {
        "skull_base": {
            "classifications": {
                "koos_grade": "",
                "samii_grade": "",
                "cpa_extension": "",
            },
            "cranial_nerves": {
                "facial_nerve_status": "",
                "hearing_status": "",
                "trigeminal_status": "",
                "lower_cranial_nerve_risk": [],
            },
            "approach_selection": {
                "retrosigmoid": {"advantages": [], "concerns": []},
                "translabyrinthine": {"advantages": [], "concerns": []},
                "middle_fossa": {"advantages": [], "concerns": []},
                "endonasal_or_transcranial": {"advantages": [], "concerns": []},
            },
            "reconstruction": {
                "csf_leak_prevention": [],
                "fat_graft_or_flap": "",
                "lumbar_drain_plan": "",
            },
        },
        "supratentorial_tumor": {
            "eloquence": {
                "motor": "",
                "language": "",
                "visual_pathways": "",
                "insula_or_deep_nuclei": "",
            },
            "mapping_plan": {
                "awake_mapping": "",
                "dti": "",
                "cortical_stimulation": "",
                "subcortical_stimulation": "",
            },
            "oncologic_plan": {
                "extent_of_resection_goal": "",
                "frozen_section_plan": "",
                "adjuvant_therapy_considerations": [],
            },
        },
        "spine": {
            "levels": [],
            "alignment": {
                "sagittal_balance": "",
                "coronal_balance": "",
                "instability": "",
            },
            "decompression_plan": [],
            "fusion_plan": {
                "levels": [],
                "instrumentation": [],
                "biologics": [],
            },
            "approach_risks": {
                "anterior": [],
                "posterior": [],
                "lateral": [],
            },
        },
        "vascular": {
            "lesion_type": "",
            "rupture_status": "",
            "grading": {
                "hunt_hess": "",
                "modified_fisher": "",
                "spetzler_martin": "",
                "cognard_borden": "",
            },
            "vascular_anatomy": {
                "feeders": [],
                "drainers": [],
                "perforators_at_risk": [],
                "venous_constraints": [],
            },
            "treatment_options": {
                "clipping": {"advantages": [], "concerns": []},
                "endovascular": {"advantages": [], "concerns": []},
                "bypass": {"advantages": [], "concerns": []},
                "observation": {"advantages": [], "concerns": []},
            },
        },
        "functional": {
            "indication": "",
            "target": "",
            "laterality": "",
            "programming_considerations": [],
            "device_or_implant": [],
            "outcome_scales": [],
        },
        "pediatric": {
            "age_specific_risks": [],
            "growth_or_development_considerations": [],
            "family_counseling_points": [],
            "radiation_sparing_considerations": [],
            "congenital_or_syndromic_context": [],
        },
    }
    return {profile: deepcopy(extensions.get(profile, {}))}


def build_caseprep_schema(topic: str, profile: str = "general") -> dict[str, Any]:
    """Build an empty but clinically structured CasePrep dossier."""
    topic = topic.strip()
    generated_at = _generated_at()
    schema: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "topic": topic,
        "case_profile": profile,
        "status": DEFAULT_STATUS,
        "generated_at": generated_at,
        "case": {
            "case_snapshot": {
                "diagnosis": topic,
                "planned_procedure": "",
                "laterality": "",
                "operative_objective": "",
                "one_line_thesis": "",
                "urgency": "",
                "anticipated_disposition": "",
            },
            "indication_and_decision": {
                "indication": "",
                "management_options": [],
                "selected_plan_rationale": "",
                "alternatives_considered": [],
                "thresholds_that_change_plan": [],
            },
            "patient_context": {
                "symptoms": [],
                "baseline_exam": [],
                "relevant_history": [],
                "prior_treatment": [],
                "anticoagulation_antiplatelets": [],
                "anesthesia_medical_issues": [],
                "consent_specific_risks": [],
            },
            "imaging_review": {
                "required_studies": [],
                "key_findings": [],
                "measurements": [],
                "anatomic_relationships": [],
                "red_flags": [],
                "images_to_display_in_or": [],
            },
            "anatomy_at_risk": {
                "surgical_corridor": [],
                "landmarks_in_order": [],
                "neural_structures": [],
                "arteries_perforators_veins_sinuses": [],
                "functional_structures": [],
                "variants": [],
                "no_fly_zones": [],
            },
            "operative_plan": {
                "positioning": "",
                "exposure": [],
                "critical_steps": [],
                "decision_points": [],
                "stop_points": [],
                "closure_reconstruction": [],
                "monitoring": [],
                "equipment_adjuncts": [],
                "attending_preferences_questions": [],
            },
            "risk_and_rescue": {
                "likely_complications": [],
                "catastrophic_complications": [],
                "mitigation": [],
                "rescue_triggers": [],
            },
            "postop_plan": {
                "destination": "",
                "neuro_checks": "",
                "bp_goals": "",
                "imaging_timing": "",
                "medications": [],
                "drains_devices": [],
                "labs_monitoring": [],
                "dvt_prophylaxis": "",
                "discharge_criteria": [],
                "follow_up": [],
            },
            "evidence": {
                "clinical_questions": [],
                "bottom_line": "",
                "confidence": "",
                "key_sources": [],
                "outcome_metrics": [],
                "complication_rates": [],
                "applicability_to_this_case": "",
                "uncertainty_gaps": [],
            },
            "verification": {
                "overall_status": DEFAULT_STATUS,
                "reviewed_by": "",
                "reviewed_at": "",
                "limitations": [
                    "Generated case-prep material requires clinician verification before use.",
                    "Empty fields indicate information not supplied to CasePrep.",
                ],
            },
        },
        "profile_extensions": _profile_extensions(profile),
        "citations": [],
        "provenance": [
            {
                "field_path": "case.case_snapshot",
                "value_status": "generated",
                "source_ids": [],
                "generated_by": "caseprep",
                "generated_at": generated_at,
                "verifier": "",
                "notes": "Initial scaffold generated from topic string.",
            }
        ],
    }
    return schema


def _yaml_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if text == "":
        return '""'
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def dump_yaml(data: Any, indent: int = 0) -> str:
    """Dump simple dict/list/scalar data as deterministic YAML."""
    spaces = " " * indent
    if isinstance(data, dict):
        lines: list[str] = []
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                lines.append(f"{spaces}{key}:")
                rendered = dump_yaml(value, indent + 2)
                if rendered:
                    lines.append(rendered)
                elif isinstance(value, list):
                    lines.append(f"{' ' * (indent + 2)}[]")
            else:
                lines.append(f"{spaces}{key}: {_yaml_scalar(value)}")
        return "\n".join(lines)
    if isinstance(data, list):
        lines = []
        for item in data:
            if isinstance(item, dict):
                lines.append(f"{spaces}-")
                lines.append(dump_yaml(item, indent + 2))
            elif isinstance(item, list):
                lines.append(f"{spaces}-")
                lines.append(dump_yaml(item, indent + 2))
            else:
                lines.append(f"{spaces}- {_yaml_scalar(item)}")
        return "\n".join(lines)
    return f"{spaces}{_yaml_scalar(data)}"


def _list_block(items: list[Any], empty: str = "- `needs input`") -> str:
    if not items:
        return empty
    return "\n".join(f"- {item}" for item in items)


def _status_line(schema: dict[str, Any]) -> str:
    status = schema.get("status", DEFAULT_STATUS)
    return f"`{status}` `needs clinician verification`"


def _render_readme(schema: dict[str, Any]) -> str:
    topic = schema["topic"]
    profile = schema["case_profile"]
    snapshot = schema["case"]["case_snapshot"]
    evidence = schema["case"]["evidence"]
    return f"""# {topic} Case Prep

## One-Line Case

{snapshot.get("one_line_thesis") or "`needs input`: one-line operative thesis"}

## Preparation Status

- Overall: {_status_line(schema)}
- Profile: `{profile}`
- Evidence sources included: {len(evidence.get("key_sources", []))}
- Unverified fields remain visible as `needs input`.

## Key Decisions

- Management question: `needs input`
- Candidate approaches: `needs input`
- Main risk tradeoff: `needs input`

## Files

{_list_block(CANONICAL_MARKDOWN_FILES[1:])}
"""


def _render_case_summary(schema: dict[str, Any]) -> str:
    case = schema["case"]
    snapshot = case["case_snapshot"]
    decision = case["indication_and_decision"]
    patient = case["patient_context"]
    return f"""# Case Summary — {schema["topic"]}

## Snapshot

- Diagnosis: {snapshot.get("diagnosis") or "`needs input`"}
- Planned procedure: {snapshot.get("planned_procedure") or "`needs input`"}
- Laterality: {snapshot.get("laterality") or "`needs input`"}
- Operative objective: {snapshot.get("operative_objective") or "`needs input`"}
- Urgency: {snapshot.get("urgency") or "`needs input`"}
- Anticipated disposition: {snapshot.get("anticipated_disposition") or "`needs input`"}

## Indication And Decision Frame

- Indication: {decision.get("indication") or "`needs input`"}
- Selected-plan rationale: {decision.get("selected_plan_rationale") or "`needs input`"}

## Alternatives Considered

{_list_block(decision.get("alternatives_considered", []))}

## Patient-Specific Context

- Symptoms: {_list_block(patient.get("symptoms", []), "`needs input`")}
- Baseline exam: {_list_block(patient.get("baseline_exam", []), "`needs input`")}
- Prior treatment: {_list_block(patient.get("prior_treatment", []), "`needs input`")}
- Anticoagulation / antiplatelets: {_list_block(patient.get("anticoagulation_antiplatelets", []), "`needs input`")}
- Consent-specific risks: {_list_block(patient.get("consent_specific_risks", []), "`needs input`")}
"""


def _render_imaging(schema: dict[str, Any]) -> str:
    imaging = schema["case"]["imaging_review"]
    return f"""# Imaging Review — {schema["topic"]}

## Imaging Review Checklist

- Required studies: {_list_block(imaging.get("required_studies", []), "`needs input`")}
- Key findings: {_list_block(imaging.get("key_findings", []), "`needs input`")}
- Measurements: {_list_block(imaging.get("measurements", []), "`needs input`")}
- Anatomic relationships: {_list_block(imaging.get("anatomic_relationships", []), "`needs input`")}
- Red flags: {_list_block(imaging.get("red_flags", []), "`needs input`")}
- Images to display in OR: {_list_block(imaging.get("images_to_display_in_or", []), "`needs input`")}
"""


def _render_anatomy(schema: dict[str, Any], generated_body: str | None = None) -> str:
    anatomy = schema["case"]["anatomy_at_risk"]
    generated = f"\n## Evidence-Derived Notes\n\n{generated_body.strip()}\n" if generated_body else ""
    return f"""# Anatomy At Risk — {schema["topic"]}

## Anatomy At Risk

- Surgical corridor: {_list_block(anatomy.get("surgical_corridor", []), "`needs input`")}
- Landmarks in order: {_list_block(anatomy.get("landmarks_in_order", []), "`needs input`")}
- Neural structures: {_list_block(anatomy.get("neural_structures", []), "`needs input`")}
- Arteries / perforators / veins / sinuses: {_list_block(anatomy.get("arteries_perforators_veins_sinuses", []), "`needs input`")}
- Functional structures: {_list_block(anatomy.get("functional_structures", []), "`needs input`")}
- Variants: {_list_block(anatomy.get("variants", []), "`needs input`")}
- No-fly zones: {_list_block(anatomy.get("no_fly_zones", []), "`needs input`")}
{generated}"""


def _render_operative_plan(schema: dict[str, Any], generated_body: str | None = None) -> str:
    plan = schema["case"]["operative_plan"]
    generated = f"\n## Evidence-Derived Notes\n\n{generated_body.strip()}\n" if generated_body else ""
    return f"""# Operative Plan — {schema["topic"]}

## Selected Approach

- Approach: `needs input`
- Rationale: `needs input`
- Verification: `needs clinician verification`

## Approach Selection Matrix

| Option | Advantages | Disadvantages | Best Fit | Concern |
|---|---|---|---|---|
| Primary plan | `needs input` | `needs input` | `needs input` | `needs input` |
| Alternative | `needs input` | `needs input` | `needs input` | `needs input` |

## Setup

- Positioning: {plan.get("positioning") or "`needs input`"}
- Monitoring: {_list_block(plan.get("monitoring", []), "`needs input`")}
- Equipment / adjuncts: {_list_block(plan.get("equipment_adjuncts", []), "`needs input`")}

## Critical Steps

{_list_block(plan.get("critical_steps", []))}

## Intraoperative Decision Points

{_list_block(plan.get("decision_points", []))}

## Bailout / Stop Points

{_list_block(plan.get("stop_points", []))}
{generated}"""


def _render_risk(schema: dict[str, Any], generated_body: str | None = None) -> str:
    risk = schema["case"]["risk_and_rescue"]
    generated = f"\n## Evidence-Derived Notes\n\n{generated_body.strip()}\n" if generated_body else ""
    return f"""# Risk And Rescue — {schema["topic"]}

## Likely Complications

{_list_block(risk.get("likely_complications", []))}

## Catastrophic Complications

{_list_block(risk.get("catastrophic_complications", []))}

## Mitigation

{_list_block(risk.get("mitigation", []))}

## Rescue Triggers

| Finding | Immediate Action | Notify | Likely Tests / Imaging |
|---|---|---|---|
| New focal deficit | ABCs, focused neuro exam, urgent surgeon notification | Neurosurgery attending / chief | CT/CTA as clinically appropriate |
| Declining mental status | ABCs, glucose, medication review, urgent evaluation | Neurosurgery and anesthesia/ICU | CT head and labs as clinically appropriate |
{generated}"""


def _render_postop(schema: dict[str, Any]) -> str:
    postop = schema["case"]["postop_plan"]
    return f"""# Postop Plan — {schema["topic"]}

## Immediate Postop Orders

- Destination: {postop.get("destination") or "`needs input`"}
- Neuro checks: {postop.get("neuro_checks") or "`needs input`"}
- BP goals: {postop.get("bp_goals") or "`needs input`"}
- Imaging timing: {postop.get("imaging_timing") or "`needs input`"}
- DVT prophylaxis: {postop.get("dvt_prophylaxis") or "`needs input`"}

## Medications

{_list_block(postop.get("medications", []))}

## Drains / Devices

{_list_block(postop.get("drains_devices", []))}

## Labs / Monitoring

{_list_block(postop.get("labs_monitoring", []))}

## Discharge Criteria

{_list_block(postop.get("discharge_criteria", []))}
"""


def _render_evidence(schema: dict[str, Any], literature_summary: str | None = None) -> str:
    evidence = schema["case"]["evidence"]
    rows = []
    for source in evidence.get("key_sources", []):
        rows.append(
            "| {id} | {title} | {year} | {evidence_level} | {relevance} | {status} |".format(
                id=source.get("id", ""),
                title=source.get("title", ""),
                year=source.get("year", ""),
                evidence_level=source.get("evidence_level", ""),
                relevance=source.get("relevance", ""),
                status=source.get("verification", "cited"),
            )
        )
    table = "\n".join(rows) if rows else "| `needs input` | `needs input` |  |  |  |  |"
    appendix = f"\n## Search Appendix\n\n{literature_summary.strip()}\n" if literature_summary else ""
    return f"""# Evidence — {schema["topic"]}

## Clinical Questions

{_list_block(evidence.get("clinical_questions", []))}

## Bottom Line

{evidence.get("bottom_line") or "`needs synthesis`: evidence has not been distilled into a case-specific bottom line."}

## Key Sources

| ID | Source | Year | Evidence Type | Relevance | Verification |
|---|---|---:|---|---|---|
{table}

## Applicability To This Case

{evidence.get("applicability_to_this_case") or "`needs input`"}

## Uncertainty / Evidence Gaps

{_list_block(evidence.get("uncertainty_gaps", []))}
{appendix}"""


def _render_checklists(schema: dict[str, Any]) -> str:
    return f"""# Checklists — {schema["topic"]}

## Day-Of Safety Checklist

- Confirm patient, site, procedure, and consent.
- Confirm laterality and levels when applicable.
- Confirm essential imaging is displayed.
- Confirm antibiotic plan and redosing interval.
- Confirm anticipated critical steps, duration, and blood loss.
- Confirm special equipment, implants, navigation, monitoring, and backup plans.
- Confirm postop destination and recovery concerns.

## Must-Review Before Incision

- Imaging: `needs input`
- Equipment: `needs input`
- Consent-specific risks: `needs input`
- Team alerts: `needs input`
- Open questions: see `09-open-questions.md`
"""


def _render_open_questions(schema: dict[str, Any]) -> str:
    return f"""# Open Questions — {schema["topic"]}

## Patient-Specific Missing Data

- Baseline neurologic exam details?
- Relevant imaging measurements?
- Prior treatment history?
- Anticoagulation / antiplatelet timing?

## Attending / Team Questions

- Preferred approach and exposure limits?
- First structure or landmark to identify?
- Stop point for subtotal resection or alternate strategy?
- Drain, steroids, antibiotics, antiepileptic, and postop imaging plan?
- Overnight call parameters?

## Safety-Critical Unknowns

- Blood plan?
- ICU bed or stepdown need?
- Monitoring availability?
- Special equipment availability?
"""


def render_caseprep_files(
    schema: dict[str, Any],
    *,
    literature_summary: str | None = None,
    anatomy_body: str | None = None,
    operative_body: str | None = None,
    risk_body: str | None = None,
) -> dict[str, str]:
    """Render the dossier schema into canonical and compatibility files."""
    files = {
        "caseprep.yaml": dump_yaml(schema) + "\n",
        "provenance.json": json.dumps(schema.get("provenance", []), indent=2) + "\n",
        "README.md": _render_readme(schema),
        "01-case-summary.md": _render_case_summary(schema),
        "02-imaging-review.md": _render_imaging(schema),
        "03-anatomy-at-risk.md": _render_anatomy(schema, anatomy_body),
        "04-operative-plan.md": _render_operative_plan(schema, operative_body),
        "05-risk-and-rescue.md": _render_risk(schema, risk_body),
        "06-postop-plan.md": _render_postop(schema),
        "07-evidence.md": _render_evidence(schema, literature_summary),
        "08-checklists.md": _render_checklists(schema),
        "09-open-questions.md": _render_open_questions(schema),
    }
    for legacy, canonical in LEGACY_MARKDOWN_ALIASES.items():
        files[legacy] = files[canonical]
    return files
```

- [ ] **Step 4: Run focused schema tests**

Run:

```bash
uv run pytest tests/test_case_schema.py -q
```

Expected: all tests in `tests/test_case_schema.py` pass.

- [ ] **Step 5: Commit schema module**

Run:

```bash
git add caseprep/schema.py tests/test_case_schema.py
git commit -m "Add structured caseprep dossier schema"
```

Expected: commit succeeds and includes only `caseprep/schema.py` and `tests/test_case_schema.py`.

---

### Task 2: Wire Static Generator To Schema Renderer

**Files:**
- Modify: `caseprep/generator.py`
- Modify: `tests/test_generator.py`

- [ ] **Step 1: Add failing generator tests for canonical files**

Append these tests to `tests/test_generator.py`:

```python
    def test_creates_caseprep_schema_files(self, tmp_dir):
        out = tmp_dir / "test-case"
        generate_caseprep("vestibular schwannoma", out)
        expected = [
            "caseprep.yaml",
            "provenance.json",
            "01-case-summary.md",
            "02-imaging-review.md",
            "03-anatomy-at-risk.md",
            "04-operative-plan.md",
            "05-risk-and-rescue.md",
            "06-postop-plan.md",
            "07-evidence.md",
            "08-checklists.md",
            "09-open-questions.md",
        ]
        for filename in expected:
            assert (out / filename).is_file(), f"missing {filename}"

    def test_readme_uses_case_dossier_status(self, tmp_dir):
        out = tmp_dir / "test-case"
        generate_caseprep("vestibular schwannoma", out)
        readme = (out / "README.md").read_text()
        assert "## Preparation Status" in readme
        assert "`needs clinician verification`" in readme
        assert "01-case-summary.md" in readme

    def test_legacy_files_are_schema_aliases(self, tmp_dir):
        out = tmp_dir / "test-case"
        generate_caseprep("vestibular schwannoma", out)
        assert (out / "anatomy.md").read_text() == (out / "03-anatomy-at-risk.md").read_text()
        assert (out / "approach.md").read_text() == (out / "04-operative-plan.md").read_text()
        assert (out / "complications.md").read_text() == (out / "05-risk-and-rescue.md").read_text()
        assert (out / "literature.md").read_text() == (out / "07-evidence.md").read_text()
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_generator.py -q
```

Expected: the new tests fail because `generate_caseprep` does not yet write `caseprep.yaml`, canonical numbered files, or schema status text.

- [ ] **Step 3: Update `caseprep/generator.py` imports**

At the top of `caseprep/generator.py`, replace:

```python
from .links import build_search_links
```

with:

```python
from .links import build_search_links
from .schema import build_caseprep_schema, render_caseprep_files
```

- [ ] **Step 4: Replace template writing loop with schema renderer**

In `generate_caseprep`, replace the current loop:

```python
    for filename, template in TEMPLATES.items():
        if filename == "literature.md":
            content = template.format(
                topic=topic,
                search_links=_search_links_markdown(links),
            )
        else:
            content = template.format(topic=topic)
        (out / filename).write_text(content, encoding="utf-8")
```

with:

```python
    schema = build_caseprep_schema(topic)
    rendered_files = render_caseprep_files(schema)
    for filename, content in rendered_files.items():
        (out / filename).write_text(content, encoding="utf-8")
```

Keep the existing `resource-links.html` writing block after this change.

- [ ] **Step 5: Keep legacy helper functions for compatibility**

Leave `_link_items_html` and `_search_links_markdown` in place for now. `_search_links_markdown` may be unused after this task, but removing it can be a later cleanup after the build pipeline is migrated.

- [ ] **Step 6: Run generator tests**

Run:

```bash
uv run pytest tests/test_generator.py -q
```

Expected: all generator tests pass.

- [ ] **Step 7: Commit generator wiring**

Run:

```bash
git add caseprep/generator.py tests/test_generator.py
git commit -m "Render static caseprep folders from schema"
```

Expected: commit succeeds and includes only `caseprep/generator.py` and `tests/test_generator.py`.

---

### Task 3: Convert PubMed Axis Data Into Evidence Sources

**Files:**
- Modify: `caseprep/schema.py`
- Modify: `tests/test_case_schema.py`

- [ ] **Step 1: Add failing evidence conversion tests**

Append these tests to `tests/test_case_schema.py`:

```python
from caseprep.schema import build_caseprep_schema_from_axis_data


def test_build_schema_from_axis_data_adds_evidence_sources():
    axis_data = {
        "Surgical Technique": [
            {
                "pmid": "12345",
                "title": "Retrosigmoid Approach Study",
                "authors": "Doe J et al.",
                "source": "J Neurosurg",
                "pubdate": "2024 Sep",
                "doi": "10.1000/test",
                "url": "https://pubmed.ncbi.nlm.nih.gov/12345/",
                "_abstract": "The retrosigmoid approach provides exposure of the cerebellopontine angle.",
                "_structured": {},
            }
        ],
        "Complications": [
            {
                "pmid": "67890",
                "title": "CSF Leak After Skull Base Surgery",
                "authors": "Roe A et al.",
                "source": "World Neurosurg",
                "pubdate": "2023",
                "doi": "",
                "url": "https://pubmed.ncbi.nlm.nih.gov/67890/",
                "_abstract": "CSF leak is a postoperative complication.",
                "_structured": {},
            }
        ],
    }

    schema = build_caseprep_schema_from_axis_data(
        "retrosigmoid vestibular schwannoma",
        axis_data,
        profile="skull_base",
    )

    evidence = schema["case"]["evidence"]
    assert evidence["clinical_questions"]
    assert evidence["key_sources"][0]["id"] == "pmid-12345"
    assert evidence["key_sources"][0]["relevance"] == "surgical technique"
    assert evidence["key_sources"][1]["id"] == "pmid-67890"
    assert evidence["key_sources"][1]["relevance"] == "complications"
    assert schema["citations"][0]["pmid"] == "12345"
    assert any(p["field_path"] == "case.evidence.key_sources" for p in schema["provenance"])


def test_build_schema_from_axis_data_deduplicates_pmids():
    paper = {
        "pmid": "12345",
        "title": "Retrosigmoid Approach Study",
        "authors": "Doe J et al.",
        "source": "J Neurosurg",
        "pubdate": "2024 Sep",
        "doi": "10.1000/test",
        "url": "https://pubmed.ncbi.nlm.nih.gov/12345/",
        "_abstract": "The retrosigmoid approach provides exposure.",
        "_structured": {},
    }
    schema = build_caseprep_schema_from_axis_data(
        "retrosigmoid vestibular schwannoma",
        {
            "Surgical Technique": [paper],
            "Reviews / Landmarks": [paper],
        },
        profile="skull_base",
    )

    assert len(schema["case"]["evidence"]["key_sources"]) == 1
    assert len(schema["citations"]) == 1
```

- [ ] **Step 2: Run schema tests to verify they fail**

Run:

```bash
uv run pytest tests/test_case_schema.py -q
```

Expected: failure with `ImportError` or `AttributeError` for `build_caseprep_schema_from_axis_data`.

- [ ] **Step 3: Add evidence conversion helpers**

Append this code to `caseprep/schema.py`:

```python
AXIS_RELEVANCE = {
    "Anatomy / Relevant Structures": "anatomy",
    "Outcomes / Evidence": "outcomes",
    "Surgical Technique": "surgical technique",
    "Complications": "complications",
    "Reviews / Landmarks": "review or landmark",
}


def _pub_year(pubdate: str) -> str:
    for token in str(pubdate).split():
        if token.isdigit() and len(token) == 4:
            return token
    return ""


def article_to_citation(article: dict[str, Any], axis: str) -> dict[str, Any]:
    """Convert an enriched PubMed article dict into a CasePrep citation."""
    pmid = str(article.get("pmid", "")).strip()
    citation_id = f"pmid-{pmid}" if pmid else f"source-{abs(hash(article.get('title', '')))}"
    return {
        "id": citation_id,
        "type": "journal_article",
        "title": article.get("title", ""),
        "authors": article.get("authors", ""),
        "journal": article.get("source", ""),
        "year": _pub_year(article.get("pubdate", "")),
        "source": "PubMed",
        "url": article.get("url", ""),
        "pmid": pmid,
        "doi": article.get("doi", ""),
        "evidence_level": "",
        "relevance": AXIS_RELEVANCE.get(axis, axis.lower()),
        "summary": article.get("_abstract", "")[:500],
        "quoted_text": "",
        "verification": "cited",
    }


def _default_clinical_questions(topic: str) -> list[str]:
    return [
        f"What operative approach and setup best fit {topic}?",
        f"What anatomy and imaging findings should change the plan for {topic}?",
        f"What complications and rescue plans are most important for {topic}?",
    ]


def build_caseprep_schema_from_axis_data(
    topic: str,
    axis_data: dict[str, list[dict]],
    profile: str = "general",
) -> dict[str, Any]:
    """Build a dossier and populate evidence sources from PubMed axis data."""
    schema = build_caseprep_schema(topic, profile=profile)
    seen_pmids: set[str] = set()
    key_sources: list[dict[str, Any]] = []
    citations: list[dict[str, Any]] = []

    for axis, articles in axis_data.items():
        for article in articles:
            pmid = str(article.get("pmid", "")).strip()
            dedupe_key = pmid or str(article.get("title", "")).strip().lower()
            if dedupe_key in seen_pmids:
                continue
            seen_pmids.add(dedupe_key)
            citation = article_to_citation(article, axis)
            citations.append(citation)
            key_sources.append({
                "id": citation["id"],
                "title": citation["title"],
                "year": citation["year"],
                "evidence_level": citation["evidence_level"],
                "relevance": citation["relevance"],
                "verification": citation["verification"],
            })

    schema["citations"] = citations
    schema["case"]["evidence"]["key_sources"] = key_sources
    schema["case"]["evidence"]["clinical_questions"] = _default_clinical_questions(topic)
    if citations:
        schema["provenance"].append({
            "field_path": "case.evidence.key_sources",
            "value_status": "cited",
            "source_ids": [c["id"] for c in citations],
            "generated_by": "caseprep",
            "generated_at": schema["generated_at"],
            "verifier": "",
            "notes": "Evidence sources converted from PubMed search axes.",
        })
    return schema
```

- [ ] **Step 4: Run schema tests**

Run:

```bash
uv run pytest tests/test_case_schema.py -q
```

Expected: all schema tests pass.

- [ ] **Step 5: Commit evidence conversion**

Run:

```bash
git add caseprep/schema.py tests/test_case_schema.py
git commit -m "Map PubMed axes into caseprep evidence schema"
```

Expected: commit succeeds and includes only `caseprep/schema.py` and `tests/test_case_schema.py`.

---

### Task 4: Wire MCP Template Population To Canonical Files

**Files:**
- Modify: `caseprep/mcp_server.py`
- Modify: `tests/test_template_population.py`

- [ ] **Step 1: Add failing `_write_filled_templates` test**

Append this test to `tests/test_template_population.py`:

```python
class TestStructuredCaseDossierOutput:
    @pytest.mark.asyncio
    async def test_write_filled_templates_writes_canonical_schema_files(self, tmp_path):
        from caseprep.mcp_server import _write_filled_templates

        axis_data = {
            "Anatomy / Relevant Structures": [
                {
                    "pmid": "12345",
                    "title": "CPA Anatomy",
                    "authors": "Doe J",
                    "source": "J Neurosurg",
                    "pubdate": "2024",
                    "doi": "",
                    "url": "https://pubmed.ncbi.nlm.nih.gov/12345/",
                    "_abstract": "The cerebellopontine angle contains cranial nerves and vascular structures.",
                    "_structured": {},
                }
            ],
            "Surgical Technique": [],
            "Reviews / Landmarks": [],
            "Outcomes / Evidence": [],
            "Complications": [],
        }

        async def fake_populate(**kwargs):
            return f"# {kwargs['section_title']} — {kwargs['topic']}\n\nGenerated section body."

        with patch("caseprep.mcp_server._populate_section", side_effect=fake_populate):
            await _write_filled_templates(
                tmp_path,
                "retrosigmoid vestibular schwannoma",
                "# Case Plan\n\nPaper summary",
                axis_data,
            )

        for filename in [
            "caseprep.yaml",
            "provenance.json",
            "README.md",
            "01-case-summary.md",
            "02-imaging-review.md",
            "03-anatomy-at-risk.md",
            "04-operative-plan.md",
            "05-risk-and-rescue.md",
            "06-postop-plan.md",
            "07-evidence.md",
            "08-checklists.md",
            "09-open-questions.md",
        ]:
            assert (tmp_path / filename).is_file(), f"missing {filename}"

        assert "Preparation Status" in (tmp_path / "README.md").read_text()
        assert "pmid-12345" in (tmp_path / "07-evidence.md").read_text()
        assert (tmp_path / "anatomy.md").read_text() == (tmp_path / "03-anatomy-at-risk.md").read_text()
        assert (tmp_path / "approach.md").read_text() == (tmp_path / "04-operative-plan.md").read_text()
        assert (tmp_path / "complications.md").read_text() == (tmp_path / "05-risk-and-rescue.md").read_text()
        assert (tmp_path / "literature.md").read_text() == (tmp_path / "07-evidence.md").read_text()
```

- [ ] **Step 2: Run focused test to verify it fails**

Run:

```bash
uv run pytest tests/test_template_population.py::TestStructuredCaseDossierOutput::test_write_filled_templates_writes_canonical_schema_files -q
```

Expected: failure because `_write_filled_templates` does not yet write the canonical numbered files.

- [ ] **Step 3: Import schema helpers in MCP server**

In `caseprep/mcp_server.py`, add this import near the existing local imports:

```python
from caseprep.schema import (
    build_caseprep_schema,
    build_caseprep_schema_from_axis_data,
    render_caseprep_files,
)
```

- [ ] **Step 4: Replace initial README/literature writes in `_write_filled_templates`**

In `_write_filled_templates`, replace:

```python
    (out_dir / "README.md").write_text(
        f"# {topic}\n\n"
        f"## Case Overview\n\n"
        f"- **Topic:** {topic}\n"
        f"- **Date:** (fill in)\n"
        f"- **Presenter:** (fill in)\n\n"
        f"## Literature Summary\n\n"
        f"{summary}\n",
        encoding="utf-8",
    )

    (out_dir / "literature.md").write_text(
        f"# Literature Review — {topic}\n\n{summary}\n",
        encoding="utf-8",
    )
```

with:

```python
    profile_name, profile_confidence = _detect_profile(topic)
    if axis_data:
        schema = build_caseprep_schema_from_axis_data(
            topic,
            axis_data,
            profile=profile_name,
        )
    else:
        schema = build_caseprep_schema(topic, profile=profile_name)

    rendered_files = render_caseprep_files(
        schema,
        literature_summary=summary,
    )
    for filename, content in rendered_files.items():
        (out_dir / filename).write_text(content, encoding="utf-8")
```

- [ ] **Step 5: Replace no-axis fallback**

In the `if not axis_data:` branch, replace the loop that writes three blank templates with:

```python
    if not axis_data:
        return
```

Rationale: the schema renderer already wrote all canonical and legacy files for the no-data case.

- [ ] **Step 6: Remove duplicate profile detection inside `_write_filled_templates`**

Below the `if not axis_data` branch, remove this duplicate block:

```python
    # Detect domain profile and build keywords
    profile_name, profile_confidence = _detect_profile(topic)
    kw = _build_keywords(profile_name)
```

Replace it with:

```python
    kw = _build_keywords(profile_name)
```

Keep the existing `conf_str` logging block because it uses `profile_confidence`.

- [ ] **Step 7: After LLM population, write canonical generated bodies**

After computing `anatomy_text`, `approach_text`, and `complications_text`, replace the three direct writes:

```python
    (out_dir / "anatomy.md").write_text(anatomy_text, encoding="utf-8")
    ...
    (out_dir / "approach.md").write_text(approach_text, encoding="utf-8")
    ...
    (out_dir / "complications.md").write_text(complications_text, encoding="utf-8")
```

with:

```python
    rendered_files = render_caseprep_files(
        schema,
        literature_summary=summary,
        anatomy_body=anatomy_text,
        operative_body=approach_text,
        risk_body=complications_text,
    )
    for filename, content in rendered_files.items():
        (out_dir / filename).write_text(content, encoding="utf-8")
```

- [ ] **Step 8: Run focused template-population tests**

Run:

```bash
uv run pytest tests/test_template_population.py -q
```

Expected: all template-population tests pass.

- [ ] **Step 9: Commit MCP schema wiring**

Run:

```bash
git add caseprep/mcp_server.py tests/test_template_population.py
git commit -m "Write build_caseplan output as structured dossier"
```

Expected: commit succeeds and includes only `caseprep/mcp_server.py` and `tests/test_template_population.py`.

---

### Task 5: Make LLM Synthesis Checklist-Compatible

**Files:**
- Modify: `caseprep/llm.py`
- Create: `tests/test_llm_prompt.py`

- [ ] **Step 1: Write failing prompt tests**

Create `tests/test_llm_prompt.py` with:

```python
"""Tests for LLM synthesis prompt construction."""

from caseprep.llm import _build_synthesis_user_prompt


def test_synthesis_prompt_allows_checklists_and_tables():
    prompt = _build_synthesis_user_prompt(
        template_sections=[
            ("Operative Plan", "- Positioning:\n- Critical steps:"),
        ],
        source_sentences=[
            "The retrosigmoid approach provides access to the cerebellopontine angle.",
        ],
        topic="retrosigmoid vestibular schwannoma",
    )

    assert "checklists, short tables, or compact prose" in prompt
    assert "No bullet lists" not in prompt
    assert "[S1] The retrosigmoid approach" in prompt
    assert "Mark unsupported fields as `needs input`" in prompt


def test_synthesis_prompt_preserves_number_integrity_rules():
    prompt = _build_synthesis_user_prompt(
        template_sections=[("Complications", "- Risk:\n- Rescue:")],
        source_sentences=["CSF leak occurred in 8% of cases."],
        topic="vestibular schwannoma",
    )

    assert "A number" in prompt
    assert "VERBATIM" in prompt
    assert "do NOT invent one" in prompt
```

- [ ] **Step 2: Run prompt tests to verify they fail**

Run:

```bash
uv run pytest tests/test_llm_prompt.py -q
```

Expected: failure because `_build_synthesis_user_prompt` does not exist.

- [ ] **Step 3: Extract prompt helper and update wording**

In `caseprep/llm.py`, add this helper above `_synthesize_call`:

```python
def _build_synthesis_user_prompt(
    template_sections: list[tuple[str, str]],
    source_sentences: list[str],
    topic: str,
) -> str:
    """Build the user prompt for section synthesis."""
    sources_block = "\n".join(
        f"[S{i+1}] {s}" for i, s in enumerate(source_sentences)
    )
    sections_block = "\n\n".join(
        f"## {name}\n{placeholder}" for name, placeholder in template_sections
    )
    return f"""\
Topic: {topic}

SOURCE SENTENCES (use these as evidence):
{sources_block}

TEMPLATE TO FILL:
{sections_block}

For each section above, write surgeon-facing case-prep content using checklists,
short tables, or compact prose as appropriate. Prefer structured bullets for
operative setup, imaging review, complications, rescue triggers, and postop
plans. Weave citations [S1], [S2] into factual claims. Mark unsupported fields
as `needs input` rather than inventing missing patient-specific details.

CITATION RULES:
- Every factual claim must cite at least one source [S#].
- If a claim draws on multiple sources, cite ALL of them: [S4, S18].
- A number (percentage, rate, n=) MUST appear in the cited source VERBATIM.
- Never combine numbers from different sources into one claim unless you cite all sources.
- If you cannot find a number in any source, do NOT invent one — write `needs input`.
"""
```

- [ ] **Step 4: Use prompt helper in `_synthesize_call`**

In `_synthesize_call`, replace the `sources_block`, `sections_block`, and `user_prompt = f"""..."""` construction with:

```python
    user_prompt = _build_synthesis_user_prompt(
        template_sections=template_sections,
        source_sentences=source_sentences,
        topic=topic,
    )
```

- [ ] **Step 5: Update system prompt line 6**

In `SYNTHESIS_SYSTEM_PROMPT`, replace:

```python
6. Write in compact prose — 2-4 sentences per section is usually enough. No bullet lists, no filler.
```

with:

```python
6. Use the format that serves the section: checklists for preparation tasks, short tables for tradeoffs or rescue triggers, and compact prose for evidence interpretation. Avoid filler.
```

- [ ] **Step 6: Run prompt tests**

Run:

```bash
uv run pytest tests/test_llm_prompt.py -q
```

Expected: all prompt tests pass.

- [ ] **Step 7: Run existing guardrail tests**

Run:

```bash
uv run pytest tests/test_template_population.py::TestGuardrailVerify -q
```

Expected: existing guardrail tests pass because prompt construction does not change verification behavior.

- [ ] **Step 8: Commit prompt update**

Run:

```bash
git add caseprep/llm.py tests/test_llm_prompt.py
git commit -m "Make synthesis prompt support caseprep checklists"
```

Expected: commit succeeds and includes only `caseprep/llm.py` and `tests/test_llm_prompt.py`.

---

### Task 6: Update Web Build Smoke Expectations

**Files:**
- Modify: `tests/test_web.py`
- Modify: `caseprep/web.py` only if the test reveals the response omits needed output-path context.

- [ ] **Step 1: Add web response expectation**

Modify `test_build_caseplan_mocked` in `tests/test_web.py` to:

```python
def test_build_caseplan_mocked(client):
    with patch("caseprep.web._handle_build_caseplan", new_callable=AsyncMock) as mock:
        mock.return_value = (
            "## Case Plan\n\n"
            "Outcomes: 3 papers found\n\n"
            "---\n"
            "Case plan written to /tmp/vestibular-schwannoma-caseprep/\n"
            "Canonical files: caseprep.yaml, 01-case-summary.md"
        )
        resp = client.post("/api/build?topic=vestibular+schwannoma")
        assert resp.status_code == 200
        data = resp.json()
        assert data["slug"] == "vestibular-schwannoma"
        assert "Case Plan" in data["summary"]
        assert data["output_dir"].endswith("vestibular-schwannoma-caseprep")
        assert "caseprep.yaml" in data["summary"]
```

- [ ] **Step 2: Run web tests**

Run:

```bash
uv run pytest tests/test_web.py -q
```

Expected: web tests pass. If they fail because `output_dir` does not match, inspect `api_build_caseplan` and keep the API response fields consistent with this test.

- [ ] **Step 3: Commit web test update**

Run:

```bash
git add tests/test_web.py
git commit -m "Assert build response mentions schema output"
```

Expected: commit succeeds and includes only `tests/test_web.py`, unless `caseprep/web.py` required a small response-field fix.

---

### Task 7: Document The New Dossier Layout

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README output section**

Replace the current output tree in `README.md`:

```markdown
vestibular-schwannoma-caseprep/
├── README.md
├── anatomy.md
├── approach.md
├── literature.md
├── complications.md
└── resource-links.html
```

with:

```markdown
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
├── anatomy.md          # compatibility alias for 03-anatomy-at-risk.md
├── approach.md         # compatibility alias for 04-operative-plan.md
├── literature.md       # compatibility alias for 07-evidence.md
├── complications.md    # compatibility alias for 05-risk-and-rescue.md
└── resource-links.html
```

- [ ] **Step 2: Add provenance note**

After the output tree, add:

```markdown
The canonical source of truth is `caseprep.yaml`. Markdown files are rendered
from that schema for quick review. `provenance.json` records whether content is
generated, inferred, cited, user-entered, or verified. Generated clinical
content should be treated as draft material until reviewed by a clinician.
```

- [ ] **Step 3: Run README-related tests**

Run:

```bash
uv run pytest tests/test_generator.py tests/test_cli.py -q
```

Expected: generator and CLI tests pass.

- [ ] **Step 4: Commit documentation**

Run:

```bash
git add README.md
git commit -m "Document structured caseprep dossier output"
```

Expected: commit succeeds and includes only `README.md`.

---

### Task 8: Full Verification And Manual Smoke Test

**Files:**
- No code files should be changed in this task.

- [ ] **Step 1: Run full test suite**

Run:

```bash
uv run pytest -q
```

Expected: all tests pass.

- [ ] **Step 2: Generate a static case folder**

Run:

```bash
uv run caseprep generate "retrosigmoid vestibular schwannoma" -o /tmp/caseprep-schema-static
```

Expected output includes:

```text
Case prep generated
Resource links
```

- [ ] **Step 3: Inspect generated static files**

Run:

```bash
ls /tmp/caseprep-schema-static
sed -n '1,120p' /tmp/caseprep-schema-static/README.md
sed -n '1,160p' /tmp/caseprep-schema-static/04-operative-plan.md
```

Expected:

- `caseprep.yaml` exists.
- `provenance.json` exists.
- `README.md` contains `## Preparation Status`.
- `04-operative-plan.md` contains `## Approach Selection Matrix`.
- Legacy `approach.md` matches `04-operative-plan.md`.

- [ ] **Step 4: Build an MCP caseplan smoke test without requiring LLM success**

Run this command:

```bash
uv run python - <<'PY'
import asyncio
from pathlib import Path
from unittest.mock import patch

from caseprep.mcp_server import _write_filled_templates

async def fake_populate(**kwargs):
    return f"# {kwargs['section_title']} — {kwargs['topic']}\n\nGenerated test body."

axis_data = {
    "Anatomy / Relevant Structures": [{
        "pmid": "12345",
        "title": "CPA Anatomy",
        "authors": "Doe J",
        "source": "J Neurosurg",
        "pubdate": "2024",
        "doi": "",
        "url": "https://pubmed.ncbi.nlm.nih.gov/12345/",
        "_abstract": "The cerebellopontine angle contains cranial nerves and vascular structures.",
        "_structured": {},
    }],
    "Surgical Technique": [],
    "Reviews / Landmarks": [],
    "Outcomes / Evidence": [],
    "Complications": [],
}

out = Path("/tmp/caseprep-schema-build")
out.mkdir(parents=True, exist_ok=True)
with patch("caseprep.mcp_server._populate_section", side_effect=fake_populate):
    asyncio.run(_write_filled_templates(
        out,
        "retrosigmoid vestibular schwannoma",
        "# Case Plan\n\nPaper summary",
        axis_data,
    ))
print((out / "README.md").read_text()[:300])
print((out / "07-evidence.md").read_text()[:300])
PY
```

Expected:

- Printed README excerpt contains `Preparation Status`.
- Printed evidence excerpt contains `pmid-12345`.

- [ ] **Step 5: Check diff hygiene**

Run:

```bash
git status --short
git diff --check
```

Expected:

- `git diff --check` exits cleanly.
- Only intended files are modified if commits were not created during execution.

---

## Self-Review Checklist

- Spec coverage:
  - Core schema: Task 1.
  - Canonical and legacy file rendering: Tasks 1, 2, 4.
  - Evidence and provenance: Tasks 1, 3, 4.
  - Static generator path: Task 2.
  - MCP `build_caseplan` path: Task 4.
  - Checklist-compatible LLM output: Task 5.
  - Web response smoke coverage: Task 6.
  - Documentation: Task 7.
  - Full verification: Task 8.
- Placeholder scan:
  - The plan intentionally uses empty strings and `needs input` as generated application output values.
  - There are no unassigned implementation tasks.
- Type consistency:
  - The schema helper names are consistent across tasks:
    - `build_caseprep_schema`
    - `build_caseprep_schema_from_axis_data`
    - `render_caseprep_files`
    - `article_to_citation`
    - `_build_synthesis_user_prompt`
  - File constants are consistent:
    - `CANONICAL_MARKDOWN_FILES`
    - `LEGACY_MARKDOWN_ALIASES`
