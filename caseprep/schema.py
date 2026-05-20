"""CasePrep v0.2 structured case dossier schema and markdown renderer."""

from __future__ import annotations

import json
import hashlib
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
    return {
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
            if isinstance(item, (dict, list)):
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


def _inline_status(schema: dict[str, Any]) -> str:
    return f"`{schema.get('status', DEFAULT_STATUS)}` `needs clinician verification`"


def _render_readme(schema: dict[str, Any]) -> str:
    topic = schema["topic"]
    profile = schema["case_profile"]
    snapshot = schema["case"]["case_snapshot"]
    evidence = schema["case"]["evidence"]
    return f"""# {topic} Case Prep

## One-Line Case

{snapshot.get("one_line_thesis") or "`needs input`: one-line operative thesis"}

## Preparation Status

- Overall: {_inline_status(schema)}
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
    return f"""# Case Summary - {schema["topic"]}

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

### Symptoms

{_list_block(patient.get("symptoms", []))}

### Baseline Exam

{_list_block(patient.get("baseline_exam", []))}

### Prior Treatment

{_list_block(patient.get("prior_treatment", []))}

### Anticoagulation / Antiplatelets

{_list_block(patient.get("anticoagulation_antiplatelets", []))}

### Consent-Specific Risks

{_list_block(patient.get("consent_specific_risks", []))}
"""


def _render_imaging(schema: dict[str, Any]) -> str:
    imaging = schema["case"]["imaging_review"]
    return f"""# Imaging Review - {schema["topic"]}

## Imaging Review Checklist

### Required Studies

{_list_block(imaging.get("required_studies", []))}

### Key Findings

{_list_block(imaging.get("key_findings", []))}

### Measurements

{_list_block(imaging.get("measurements", []))}

### Anatomic Relationships

{_list_block(imaging.get("anatomic_relationships", []))}

### Red Flags

{_list_block(imaging.get("red_flags", []))}

### Images To Display In OR

{_list_block(imaging.get("images_to_display_in_or", []))}
"""


def _generated_section(title: str, generated_body: str | None) -> str:
    if not generated_body:
        return ""
    return f"\n## Evidence-Derived Notes\n\n{generated_body.strip()}\n"


def _render_anatomy(schema: dict[str, Any], generated_body: str | None = None) -> str:
    anatomy = schema["case"]["anatomy_at_risk"]
    return f"""# Anatomy At Risk - {schema["topic"]}

## Anatomy At Risk

### Surgical Corridor

{_list_block(anatomy.get("surgical_corridor", []))}

### Landmarks In Order

{_list_block(anatomy.get("landmarks_in_order", []))}

### Neural Structures

{_list_block(anatomy.get("neural_structures", []))}

### Arteries / Perforators / Veins / Sinuses

{_list_block(anatomy.get("arteries_perforators_veins_sinuses", []))}

### Functional Structures

{_list_block(anatomy.get("functional_structures", []))}

### Variants

{_list_block(anatomy.get("variants", []))}

### No-Fly Zones

{_list_block(anatomy.get("no_fly_zones", []))}
{_generated_section("Evidence-Derived Notes", generated_body)}"""


def _render_operative_plan(
    schema: dict[str, Any],
    generated_body: str | None = None,
) -> str:
    plan = schema["case"]["operative_plan"]
    return f"""# Operative Plan - {schema["topic"]}

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

### Monitoring

{_list_block(plan.get("monitoring", []))}

### Equipment / Adjuncts

{_list_block(plan.get("equipment_adjuncts", []))}

## Critical Steps

{_list_block(plan.get("critical_steps", []))}

## Intraoperative Decision Points

{_list_block(plan.get("decision_points", []))}

## Bailout / Stop Points

{_list_block(plan.get("stop_points", []))}
{_generated_section("Evidence-Derived Notes", generated_body)}"""


def _render_risk(schema: dict[str, Any], generated_body: str | None = None) -> str:
    risk = schema["case"]["risk_and_rescue"]
    return f"""# Risk And Rescue - {schema["topic"]}

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
{_generated_section("Evidence-Derived Notes", generated_body)}"""


def _render_postop(schema: dict[str, Any]) -> str:
    postop = schema["case"]["postop_plan"]
    return f"""# Postop Plan - {schema["topic"]}

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
    return f"""# Evidence - {schema["topic"]}

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
    return f"""# Checklists - {schema["topic"]}

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
    return f"""# Open Questions - {schema["topic"]}

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


def _fallback_source_id(title: str) -> str:
    digest = hashlib.sha1(title.encode("utf-8")).hexdigest()[:10]
    return f"source-{digest}"


def article_to_citation(article: dict[str, Any], axis: str) -> dict[str, Any]:
    """Convert an enriched PubMed article dict into a CasePrep citation."""
    pmid = str(article.get("pmid", "")).strip()
    title = article.get("title", "")
    citation_id = f"pmid-{pmid}" if pmid else _fallback_source_id(str(title))
    # Extract evidence level from _evidence_grade if available
    _eg = article.get("_evidence_grade")
    evidence_level = _eg.label if _eg else ""
    return {
        "id": citation_id,
        "type": "journal_article",
        "title": title,
        "authors": article.get("authors", ""),
        "journal": article.get("source", ""),
        "year": _pub_year(article.get("pubdate", "")),
        "source": "PubMed",
        "url": article.get("url", ""),
        "pmid": pmid,
        "doi": article.get("doi", ""),
        "evidence_level": evidence_level,
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
    seen_sources: set[str] = set()
    key_sources: list[dict[str, Any]] = []
    citations: list[dict[str, Any]] = []

    for axis, articles in axis_data.items():
        for article in articles:
            pmid = str(article.get("pmid", "")).strip()
            dedupe_key = pmid or str(article.get("title", "")).strip().lower()
            if not dedupe_key or dedupe_key in seen_sources:
                continue
            seen_sources.add(dedupe_key)
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

    evidence = schema["case"]["evidence"]
    evidence["key_sources"] = key_sources
    evidence["clinical_questions"] = _default_clinical_questions(topic)
    schema["citations"] = citations
    if citations:
        schema["provenance"].append({
            "field_path": "case.evidence.key_sources",
            "value_status": "cited",
            "source_ids": [citation["id"] for citation in citations],
            "generated_by": "caseprep",
            "generated_at": schema["generated_at"],
            "verifier": "",
            "notes": "Evidence sources converted from PubMed search axes.",
        })
    return schema
