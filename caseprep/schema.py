"""CasePrep v0.2 structured case dossier schema and markdown renderer."""

from __future__ import annotations

import json
import hashlib
import re
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from caseprep.fact_projection import fact_line, has_known_fact, missing_or_confirm_line


SCHEMA_VERSION = "0.2"
DEFAULT_STATUS = "draft"

CANONICAL_MARKDOWN_FILES = [
    "README.md",
    "00-morning-of-case.md",
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
        "posterior_fossa": {
            "chiari_features": {
                "tonsillar_descent": "",
                "syrinx": "",
                "basilar_invagination": "",
                "craniocervical_instability": "",
            },
            "decompression_plan": {
                "suboccipital_craniectomy": "",
                "c1_laminectomy": "",
                "duraplasty": "",
                "tonsillar_reduction": "",
            },
            "posterior_fossa_risks": {
                "csf_leak_or_pseudomeningocele": [],
                "vertebral_or_pica_injury": [],
                "brainstem_or_lower_cranial_nerve": [],
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


def build_caseprep_schema(
    topic: str,
    profile: str = "general",
    *,
    structured_case: dict[str, Any] | None = None,
    procedure_family: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an empty but clinically structured CasePrep dossier."""
    topic = topic.strip()
    generated_at = _generated_at()
    schema = {
        "schema_version": SCHEMA_VERSION,
        "topic": topic,
        "case_profile": profile,
        "structured_case": deepcopy(structured_case) if structured_case is not None else {},
        "procedure_family": deepcopy(procedure_family),
        "status": DEFAULT_STATUS,
        "generated_at": generated_at,
        "case": {
            "facts": _structured_case_facts(structured_case),
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
                "evidence_pack": None,
                "quarantined_sources": [],
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
    _propagate_structured_case_snapshot(schema)
    return schema


def _structured_case_facts(structured_case: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(structured_case, dict):
        return {}
    facts = structured_case.get("facts")
    return deepcopy(facts) if isinstance(facts, dict) else {}


def _case_facts(schema: dict[str, Any]) -> dict[str, Any]:
    case_section = schema.setdefault("case", {})
    if not isinstance(case_section, dict):
        return {}
    facts = case_section.get("facts")
    if not isinstance(facts, dict):
        facts = {}
        case_section["facts"] = facts
    return facts


def _propagate_structured_case_snapshot(schema: dict[str, Any]) -> None:
    """Fill high-confidence parsed facts into the visible case snapshot."""
    structured_case = schema.get("structured_case") or {}
    if not isinstance(structured_case, dict) or not structured_case:
        return
    snapshot = schema.get("case", {}).get("case_snapshot", {})
    if not isinstance(snapshot, dict):
        return

    pathology = _structured_case_value(schema, "pathology")
    procedure = _structured_case_value(schema, "procedure")
    laterality = _structured_case_value(schema, "laterality")
    if pathology:
        snapshot["diagnosis"] = pathology
    if procedure:
        snapshot["planned_procedure"] = procedure
    if laterality:
        snapshot["laterality"] = laterality

    if _procedure_family_id(schema) == "endovascular_thrombectomy":
        ctx = _thrombectomy_target_context(schema)
        target = str(ctx["target"])
        planned = procedure or "mechanical thrombectomy"
        snapshot["planned_procedure"] = planned
        if laterality:
            snapshot["laterality"] = laterality
        snapshot["operative_objective"] = f"Reperfuse {target} with safe mTICI 2b/2c/3 goal."
        snapshot["urgency"] = "Emergent stroke thrombectomy workflow."
        snapshot["anticipated_disposition"] = "Neuro-ICU/stroke unit after EVT."
        snapshot["one_line_thesis"] = _thrombectomy_one_line_thesis(schema, target, planned)
    elif _procedure_family_id(schema) == "spine_acdf":
        ctx = _acdf_context(schema)
        planned = procedure or ctx["procedure"]
        snapshot["diagnosis"] = ctx["diagnosis"]
        snapshot["planned_procedure"] = planned
        if laterality:
            snapshot["laterality"] = laterality
        snapshot["operative_objective"] = (
            f"Decompress the {ctx['root_target']} at {ctx['level']}, remove foraminal disc-osteophyte compression, "
            "and achieve stable fusion."
        )
        snapshot["urgency"] = "Elective/urgent spine workflow; verify neurologic deficit severity and myelopathy status."
        snapshot["anticipated_disposition"] = "PACU then floor or higher-acuity monitoring if airway/myelopathy/comorbidity risk."
        snapshot["one_line_thesis"] = (
            f"{ctx['diagnosis']} planned for {planned} at {ctx['level']}; key prep is level localization, "
            "anterior corridor safety, decompression target, and implant/fusion construct verification."
        )
    elif _procedure_family_id(schema) == "tumor_convexity_meningioma":
        ctx = _meningioma_context(schema)
        planned = procedure or "meningioma resection / craniotomy prep domain"
        snapshot["diagnosis"] = ctx["diagnosis"]
        snapshot["planned_procedure"] = planned
        if laterality:
            snapshot["laterality"] = laterality
        snapshot["operative_objective"] = (
            f"Prepare for safe {ctx['corridor']} and resection strategy while preserving {ctx['sinus']} and cortical venous drainage."
        )
        snapshot["urgency"] = "Elective/urgent tumor workflow; verify symptoms, edema, venous imaging, and booked operative plan."
        snapshot["anticipated_disposition"] = "PACU then floor/ICU depending on edema, venous sinus manipulation, and neurologic risk."
        snapshot["one_line_thesis"] = (
            f"{ctx['diagnosis']}; key prep is MRV/CTV-defined venous anatomy, abutment-vs-invasion uncertainty, "
            "cortical/bridging vein preservation, and extent-of-resection stop points."
        )


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


def _markdown_sections(*sections: str) -> str:
    """Join optional markdown sections with clean blank lines."""
    rendered = "\n\n".join(section.strip() for section in sections if section.strip())
    return f"{rendered}\n\n" if rendered else ""


def _procedure_family_id(schema: dict[str, Any]) -> str:
    """Return the canonical procedure-family ID when present."""
    procedure_family = schema.get("procedure_family")
    if isinstance(procedure_family, dict) and procedure_family.get("id"):
        return str(procedure_family["id"])
    structured_case = schema.get("structured_case") or {}
    if isinstance(structured_case, dict):
        family_field = structured_case.get("procedure_family")
        if isinstance(family_field, dict) and family_field.get("value"):
            return str(family_field["value"])
    return ""


def _is_thrombectomy(schema: dict[str, Any]) -> bool:
    return _procedure_family_id(schema) == "endovascular_thrombectomy"


def _known_fact_value(facts: dict[str, Any], key: str) -> str:
    """Return a fact value only when fact_projection considers it known."""
    if not has_known_fact(facts, key):
        return ""
    fact = facts.get(key)
    if isinstance(fact, dict) and fact.get("value"):
        return str(fact["value"])
    return ""


def _thrombectomy_one_line_thesis(schema: dict[str, Any], target: str, planned: str) -> str:
    """Render the thrombectomy thesis without marking known facts as pending."""
    facts = _case_facts(schema)
    nihss = _known_fact_value(facts, "nihss")
    aspects = _known_fact_value(facts, "aspects")
    lkw = _known_fact_value(facts, "last_known_well")
    perfusion = _known_fact_value(facts, "perfusion_selection")

    supplied: list[str] = []
    if nihss:
        supplied.append(f"NIHSS {nihss}")
    if aspects:
        supplied.append(f"ASPECTS {aspects}")
    if lkw:
        supplied.append(f"LKW {lkw}")
    if perfusion:
        supplied.append(perfusion)
    supplied_clause = f" with supplied {', '.join(supplied)}" if supplied else ""

    pending: list[str] = []
    if not lkw and not nihss:
        pending.append("LKW/NIHSS")
    else:
        if not lkw:
            pending.append("LKW")
        if not nihss:
            pending.append("NIHSS")
    pending.append("hemorrhage exclusion")
    if not aspects and not perfusion:
        pending.append("ASPECTS/core")
    else:
        if not aspects:
            pending.append("ASPECTS")
        if not perfusion:
            pending.append("core/perfusion profile")
    pending.extend(["thrombolytic status", "goals-of-care verification"])

    return f"Acute ischemic stroke from {target}{supplied_clause}; planned {planned} pending {_join_sentence_items(pending)}."


def _join_sentence_items(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return f"{', '.join(items[:-1])}, and {items[-1]}"


def _fact_status_line(
    facts: dict[str, Any],
    key: str,
    *,
    label: str | None = None,
    missing_text: str = "incomplete/needs input",
) -> str:
    """Render a status-aware fact line while preserving existing missing wording."""
    line = missing_or_confirm_line(facts, key, label=label)
    missing_suffix = "missing/needs input"
    if line.endswith(missing_suffix):
        return f"{line[: -len(missing_suffix)]}{missing_text}"
    return line


def _render_thrombectomy_known_facts(schema: dict[str, Any]) -> str:
    facts = _case_facts(schema)
    lines = [
        missing_or_confirm_line(facts, "nihss"),
        missing_or_confirm_line(facts, "aspects"),
        missing_or_confirm_line(facts, "last_known_well"),
        missing_or_confirm_line(facts, "perfusion_selection"),
        missing_or_confirm_line(facts, "access_route"),
    ]
    for key in ("balloon_guide", "aspiration", "stent_retriever"):
        if has_known_fact(facts, key):
            lines.append(fact_line(facts, key))
    return f"""## Patient-Specific Fact Status

{_list_block(lines)}

"""


def _render_thrombectomy_supplied_technique(schema: dict[str, Any]) -> str:
    facts = _case_facts(schema)
    lines: list[str] = []
    if has_known_fact(facts, "access_route"):
        lines.append(fact_line(facts, "access_route"))
    for key in ("balloon_guide", "aspiration", "stent_retriever"):
        if has_known_fact(facts, key):
            lines.append(fact_line(facts, key))
    if not lines:
        return ""
    return f"""## Supplied Technique Facts

{_list_block(lines)}

"""


def _thrombectomy_imaging_selection_status(facts: dict[str, Any], target: str) -> str:
    supplied: list[str] = []
    aspects = _known_fact_value(facts, "aspects")
    perfusion = _known_fact_value(facts, "perfusion_selection")
    if aspects:
        supplied.append(f"ASPECTS {aspects} supplied")
    if perfusion:
        supplied.append(f"{perfusion} supplied")
    if supplied:
        return (
            f"Imaging selection: {'; '.join(supplied)}; still confirm NCCT hemorrhage exclusion, "
            f"CTA-confirmed {target}, collaterals, involved ASPECTS regions, and quantitative core-penumbra values when relevant."
        )
    return (
        f"Imaging selection: incomplete/needs input; NCCT hemorrhage exclusion, ASPECTS, "
        f"CTA-confirmed {target}, collaterals, and CTP/core-penumbra profile when late/unknown window."
    )


def _render_thrombectomy_imaging_fact_status(schema: dict[str, Any]) -> str:
    facts = _case_facts(schema)
    has_supplied_imaging = any(
        has_known_fact(facts, key) for key in ("aspects", "perfusion_selection")
    )
    title = "Supplied Imaging Facts" if has_supplied_imaging else "Imaging Fact Status"
    lines = [
        missing_or_confirm_line(facts, "aspects"),
        missing_or_confirm_line(facts, "perfusion_selection"),
    ]
    return f"""### {title}

{_list_block(lines)}
"""


def _thrombectomy_required_studies(schema: dict[str, Any]) -> list[str]:
    facts = _case_facts(schema)
    aspects = _known_fact_value(facts, "aspects")
    perfusion = _known_fact_value(facts, "perfusion_selection")
    items: list[str] = []
    for item in _section_list(schema, "imaging_review", "required_studies"):
        text = str(item)
        if aspects and text.startswith("NCCT head:"):
            items.append(
                f"NCCT head: ASPECTS {aspects} supplied; still confirm hemorrhage exclusion, involved ASPECTS regions, early ischemic change, mass effect, and large established infarct."
            )
        elif perfusion and text.startswith("CTP or MR diffusion/perfusion"):
            items.append(
                f"CTP/MR perfusion selection: {perfusion} supplied; document source images/maps, core volume, penumbra/hypoperfusion volume, mismatch ratio, and whether selection is trial-aligned."
            )
        else:
            items.append(text)
    return items


def _thrombectomy_imaging_key_findings(schema: dict[str, Any]) -> list[str]:
    facts = _case_facts(schema)
    aspects = _known_fact_value(facts, "aspects")
    perfusion = _known_fact_value(facts, "perfusion_selection")
    items: list[str] = []
    for item in _section_list(schema, "imaging_review", "key_findings"):
        text = str(item)
        if aspects and text.startswith("ASPECTS:"):
            items.append(
                f"ASPECTS: {aspects} supplied; confirm affected-territory regions, mass effect, edema, and whether large-core considerations apply."
            )
        elif perfusion and text.startswith("CTP/core-penumbra"):
            items.append(
                f"CTP/core-penumbra selection: {perfusion} supplied; document ischemic core volume, penumbra/hypoperfusion volume, mismatch ratio, and trial-aligned selection details."
            )
        else:
            items.append(text)
    return items


def _thrombectomy_imaging_measurements(schema: dict[str, Any]) -> list[str]:
    facts = _case_facts(schema)
    aspects = _known_fact_value(facts, "aspects")
    perfusion = _known_fact_value(facts, "perfusion_selection")
    items: list[str] = []
    for item in _section_list(schema, "imaging_review", "measurements"):
        text = str(item)
        if aspects and text.startswith("ASPECTS numeric score"):
            items.append(
                f"ASPECTS numeric score: {aspects} supplied; confirm involved ASPECTS regions."
            )
        elif perfusion and text.startswith("Core volume"):
            items.append(
                f"Perfusion/core/penumbra selection: {perfusion} supplied; document core volume (mL), hypoperfusion/penumbra volume (mL), mismatch ratio, and Tmax/CBF thresholds if CTP used."
            )
        else:
            items.append(text)
    return items


def _is_acdf(schema: dict[str, Any]) -> bool:
    return _procedure_family_id(schema) == "spine_acdf"


def _is_convexity_meningioma(schema: dict[str, Any]) -> bool:
    return _procedure_family_id(schema) == "tumor_convexity_meningioma"


def _is_parasagittal_sss_meningioma(schema: dict[str, Any]) -> bool:
    if not _is_convexity_meningioma(schema):
        return False
    ctx = _meningioma_context(schema)
    haystack = " ".join(
        str(part)
        for part in (
            schema.get("topic", ""),
            ctx.get("location", ""),
            ctx.get("diagnosis", ""),
            ctx.get("sinus", ""),
        )
    ).casefold()
    return any(term in haystack for term in ("parasagittal", "superior sagittal", "sss", "sagittal sinus"))


def _acdf_context(schema: dict[str, Any]) -> dict[str, str]:
    """Derive ACDF case wording from structured facts without inventing specifics."""
    topic = str(schema.get("topic", ""))
    level = _structured_case_value(schema, "level_or_segment") or "cervical level"
    laterality = _structured_case_value(schema, "laterality").strip().casefold()
    side = laterality if laterality in {"right", "left", "bilateral"} else ""
    procedure = _structured_case_value(schema, "procedure") or "anterior cervical discectomy and fusion"
    pathology = _structured_case_value(schema, "pathology") or "cervical radiculopathy"
    haystack = " ".join(part for part in (topic, pathology, level) if part)

    nerve_root = ""
    radiculopathy_match = re.search(r"\b(C[3-8])\s+radiculopathy\b", haystack, re.IGNORECASE)
    if radiculopathy_match:
        nerve_root = radiculopathy_match.group(1).upper()
    else:
        level_match = re.search(r"\bC(\d+)\s*[-/]\s*(\d+)\b", level, re.IGNORECASE)
        if level_match:
            nerve_root = f"C{level_match.group(2)}"

    if nerve_root:
        root_target = f"{side} {nerve_root} nerve root".strip()
    elif side:
        root_target = f"{side} symptomatic nerve root"
    else:
        root_target = "symptomatic nerve root"

    if side and nerve_root:
        diagnosis = f"{side} {nerve_root} radiculopathy"
        if "disc osteophyte" in haystack.casefold():
            diagnosis += " from foraminal disc osteophyte complex"
    else:
        diagnosis = pathology

    return {
        "level": level,
        "side": side or "symptomatic side needs input",
        "nerve_root": nerve_root or "nerve root needs input",
        "root_target": root_target,
        "procedure": procedure,
        "pathology": pathology,
        "diagnosis": diagnosis,
    }


def _acdf_defaults(schema: dict[str, Any]) -> dict[str, dict[str, Any]]:
    ctx = _acdf_context(schema)
    level = ctx["level"]
    root_target = ctx["root_target"]
    return {
        "imaging_review": {
            "required_studies": [
                f"MRI cervical spine confirming {level} foraminal/lateral recess compression and cord status.",
                f"Lateral and AP cervical radiographs or fluoroscopy plan for side/site/level localization at {level}.",
                "CT only if osteophyte/OPLL, calcified disc, prior fusion, or bony anatomy changes the decompression/implant plan.",
            ],
            "key_findings": [
                f"Confirm the symptomatic level is {level} and matches the clinical {root_target} syndrome.",
                "Define central canal stenosis, foraminal stenosis, disc-osteophyte complex, uncinate hypertrophy, and cord signal change.",
            ],
            "measurements": [
                "Disc height/collapse, segmental alignment/kyphosis, osteophyte burden, and foraminal dimensions that affect distraction and cage sizing.",
            ],
            "anatomic_relationships": [
                "Map vertebral artery course/laterality risk near the uncovertebral joint and foramen before aggressive lateral decompression.",
                "Review prevertebral soft tissue, prior surgery, and esophagus/trachea corridor constraints.",
            ],
            "red_flags": [
                "Wrong-level risk if level localization is not explicitly confirmed with fluoroscopy before discectomy.",
                "OPLL/calcified disc, severe kyphosis/instability, myelopathy, infection/tumor, or multilevel disease may change the plan.",
            ],
            "images_to_display_in_or": [
                f"Sagittal and axial MRI through {level}; lateral fluoroscopic localization image; AP/lateral final construct image.",
            ],
        },
        "anatomy_at_risk": {
            "surgical_corridor": [
                "Anterior cervical exposure through the interval between sternocleidomastoid/carotid sheath laterally and tracheoesophageal complex medially.",
                "Protect the esophagus and trachea medially; use atraumatic retraction and release periodically if prolonged.",
                "Stay on the anterior spine after platysma and prevertebral fascia opening; elevate longus colli subperiosteally for retractor placement.",
            ],
            "landmarks_in_order": [
                "Skin crease incision and platysma; identify sternocleidomastoid and carotid sheath lateral boundary.",
                f"Prevertebral fascia, longus colli, disc space, and fluoroscopic level localization at {level} before annulotomy/discectomy.",
                "Anterior osteophytes, annulus, disc space, posterior longitudinal ligament, uncinate joints, foramen, endplates, graft/cage, and plate/screws if used.",
            ],
            "neural_structures": [
                "Recurrent laryngeal nerve is at risk during anterior cervical exposure/retraction; document baseline voice and approach-side considerations.",
                f"{root_target.capitalize()} decompression target: follow disc-osteophyte/uncinate pathology to the foramen while avoiding over-distraction or traction injury.",
                "Spinal cord and exiting nerve root are protected during posterior longitudinal ligament opening and foraminal decompression.",
            ],
            "arteries_perforators_veins_sinuses": [
                "Vertebral artery lies lateral to the uncovertebral joint/transverse foramen; avoid overly lateral uncinate drilling or instrument passage.",
                "Carotid sheath contents remain lateral in the approach corridor; avoid carotid/jugular/vagus injury during exposure and retractor placement.",
            ],
            "functional_structures": [
                "Swallowing and voice function: esophagus, pharyngeal plexus/superior laryngeal region, and recurrent laryngeal nerve irritation can cause dysphagia or dysphonia.",
            ],
            "variants": [
                "Prior anterior neck surgery, large osteophytes/OPLL, high-riding vertebral artery, obesity/short neck, or multilevel disease may change exposure and implant strategy.",
            ],
            "no_fly_zones": [
                "Do not start discectomy until side/site/level localization is confirmed fluoroscopically.",
                "Do not chase lateral uncinate/foraminal decompression beyond safe bony boundaries without rechecking vertebral artery risk.",
            ],
        },
        "operative_plan": {
            "positioning": "Supine on radiolucent table with neck neutral/slight extension as tolerated; shoulders taped only enough for lateral fluoroscopy; confirm airway and neuromonitoring plan per surgeon/anesthesia.",
            "monitoring": [
                "Baseline neurologic exam, voice/swallow symptoms, and myelopathy/radiculopathy findings documented preoperatively.",
                "Fluoroscopy available for initial level localization, implant sizing, plate/screw trajectory, and final AP/lateral confirmation.",
            ],
            "equipment_adjuncts": [
                "Anterior cervical retractors, Caspar pins/distraction system, microscope/loupes, high-speed drill, curettes, Kerrisons, nerve hooks, graft/cage trials, graft/cage, plate/screws or stand-alone device per attending plan.",
            ],
            "critical_steps": [
                "Anterior cervical exposure: skin/platysma opening, develop medial sternocleidomastoid-carotid sheath and lateral tracheoesophageal interval, reach prevertebral fascia, and elevate longus colli.",
                f"Level localization: confirm {level} with fluoroscopy before annulotomy; repeat if anatomy or exposure is ambiguous.",
                "Caspar pin placement/distraction only after level confirmation; avoid excessive distraction, endplate violation, or wrong-level trajectory.",
                "Discectomy and decompression: remove disc and posterior osteophytes, open posterior longitudinal ligament when indicated, decompress central canal and foraminal pathology.",
                f"Foraminal decompression: address uncinate/disc-osteophyte complex until the {root_target} is decompressed, while respecting vertebral artery lateral boundary.",
                "Endplate preparation: remove cartilaginous endplate while preserving bony endplate to reduce subsidence/pseudarthrosis risk.",
                "Trial, place graft/cage with appropriate height/lordosis, then plate/screws or stand-alone fixation per implant / fusion construct plan; verify with fluoroscopy.",
                "Hemostasis, irrigation, esophagus/trachea inspection if concern, drain decision, layered closure, and final neurologic/airway handoff.",
            ],
            "decision_points": [
                "Confirm whether the implant / fusion construct is cage/graft alone, plate/screws, zero-profile, or stand-alone device before incision.",
                "If decompression is primarily lateral foraminal/uncinate, define how far to drill before vertebral artery risk outweighs incremental decompression.",
                "Consider posterior cervical foraminotomy as an alternative/rescue discussion for isolated foraminal radiculopathy without instability/kyphosis or need for anterior fusion.",
            ],
            "stop_points": [
                "Stop and re-localize if fluoroscopy does not clearly confirm the intended level.",
                "Stop lateral decompression if vertebral artery boundary is uncertain, bleeding is atypical, or the foramen cannot be safely defined.",
                "Escalate immediately for airway-threatening hematoma, esophageal/tracheal injury concern, CSF leak, or neuromonitoring/new deficit concern.",
            ],
            "closure_reconstruction": [
                "Confirm final AP/lateral fluoroscopy, hemostasis after retractor release, drain/collar plan, and wound closure layers.",
            ],
            "attending_preferences_questions": [
                "Approach side and rationale, implant / fusion construct, use of plate/screws vs stand-alone cage, PLL opening threshold, drain/collar preferences, and postop imaging timing.",
            ],
        },
        "risk_and_rescue": {
            "likely_complications": [
                "Dysphagia/odynophagia from esophageal and pharyngeal retraction; document baseline swallowing and minimize retraction time/force.",
                "Hoarseness or recurrent laryngeal nerve palsy from traction or approach-side risk; document baseline voice and evaluate persistent dysphonia.",
                "C5 palsy or new radiculopathy/myelopathy, graft/cage subsidence, pseudarthrosis, adjacent segment stress, and wound issues.",
            ],
            "catastrophic_complications": [
                "Hematoma/airway compromise: neck swelling, stridor, respiratory distress, or rapidly progressive dysphagia requires immediate airway/surgeon response and possible wound opening.",
                "Esophageal injury: suspect with violation, deep infection, severe dysphagia, fever, or mediastinal concern; stop, inspect, repair/consult as needed.",
                "Vertebral artery injury during lateral uncinate/foraminal decompression: pack/tamponade, maintain exposure, call vascular/endovascular help, and avoid blind instrumentation.",
                "Spinal cord or nerve root injury during PLL opening, posterior osteophyte removal, or foraminal decompression.",
            ],
            "mitigation": [
                "Fluoroscopic side/site/level localization before discectomy and final AP/lateral imaging after graft/cage/plate/screws.",
                "Subperiosteal longus colli elevation and retractor placement under muscle, with periodic release and esophagus/trachea protection.",
                "Preserve bony endplates, avoid excessive distraction, and select graft/cage/plate construct deliberately to reduce subsidence and pseudarthrosis.",
            ],
            "rescue_triggers": [
                "Airway symptoms or expanding hematoma: call anesthesia/surgeon immediately, prepare wound opening and airway control.",
                "Voice change, dysphagia, fever, crepitus, or wound drainage: evaluate for RLN/esophageal injury and infection.",
                "New neurologic deficit: urgent exam, imaging, and decompression/hematoma/implant-position assessment.",
            ],
        },
        "postop_plan": {
            "destination": "PACU with airway/neck hematoma vigilance; floor vs higher-acuity bed per comorbidities, myelopathy, airway risk, and surgeon preference.",
            "neuro_checks": "Serial motor/sensory checks focused on deltoid/biceps/wrist extension, triceps/hand function, gait/myelopathy signs if present, and the decompressed nerve-root distribution.",
            "bp_goals": "Avoid severe hypertension that could worsen neck hematoma risk; maintain cord/nerve perfusion per anesthesia/surgeon plan.",
            "imaging_timing": "Upright cervical x-rays or AP/lateral radiographs per surgeon protocol to confirm graft/cage/plate/screws alignment and level.",
            "medications": [
                "Analgesia, antiemetics, bowel regimen, and steroid/antibiotic plan only if ordered by surgeon/protocol.",
                "Anticoagulation/antiplatelet restart timing individualized to bleeding risk and indication.",
            ],
            "drains_devices": [
                "Drain management and removal threshold if used; collar plan if prescribed by surgeon.",
            ],
            "labs_monitoring": [
                "Monitor airway, dysphagia, voice change, neck swelling, wound drainage, fever, new radiculopathy/myelopathy, and signs of hematoma.",
            ],
            "dvt_prophylaxis": "Mechanical prophylaxis immediately; chemoprophylaxis timing per surgeon and bleeding risk.",
            "discharge_criteria": [
                "Stable airway, tolerating diet/swallowing plan, pain controlled, ambulatory/safe disposition, stable neurologic exam, and drain/collar/fusion precautions understood.",
            ],
            "follow_up": [
                "Fusion precautions, wound check, activity/lifting limits, tobacco/NSAID guidance per surgeon, and follow-up imaging schedule.",
            ],
        },
    }


def _structured_case_value(schema: dict[str, Any], key: str) -> str:
    structured_case = schema.get("structured_case") or {}
    if not isinstance(structured_case, dict):
        return ""
    field = structured_case.get(key)
    if isinstance(field, dict) and field.get("value"):
        return str(field["value"])
    # Some callers use "segment" rather than the parser's canonical
    # "level_or_segment" key.
    if key == "level_or_segment":
        field = structured_case.get("segment")
        if isinstance(field, dict) and field.get("value"):
            return str(field["value"])
    return ""


def _thrombectomy_target_context(schema: dict[str, Any]) -> dict[str, str | bool]:
    """Derive EVT target wording without assuming every case is right M1/MCA."""
    laterality = _structured_case_value(schema, "laterality").strip().casefold()
    side = laterality if laterality in {"right", "left", "bilateral"} else ""
    segment = _structured_case_value(schema, "level_or_segment").strip()
    location = _structured_case_value(schema, "anatomic_location").strip()
    pathology = _structured_case_value(schema, "pathology").strip()
    haystack = " ".join(
        part for part in (segment, location, pathology, schema.get("topic", "")) if part
    ).casefold()

    is_basilar = "basilar" in haystack
    is_mca = any(term in haystack for term in ("m1", "m2", "mca", "middle cerebral"))
    is_ica = any(term in haystack for term in ("ica terminus", "carotid terminus", "internal carotid"))
    is_aca = "aca" in haystack or "anterior cerebral" in haystack
    is_pca = "pca" in haystack or "posterior cerebral" in haystack

    if is_basilar:
        vessel = "basilar artery"
        target = "basilar artery occlusion"
        territory = "posterior circulation / brainstem-cerebellar territory"
        circulation = "posterior circulation"
        access_target = "vertebral-basilar circulation"
        landmarks = [
            "Aortic arch and subclavian/vertebral origins; identify tortuosity, stenosis, or dissection risk.",
            "Dominant vertebral artery route to V4 and vertebrobasilar junction.",
            "Basilar artery course, perforator-rich trunk, AICA/SCA/PCA branch anatomy, and clot extent.",
            "Posterior circulation collateral pattern including posterior communicating arteries when visible.",
        ]
        perforators = [
            "Basilar trunk perforators and branch ostia are at risk during wire/device crossing and retrieval.",
            "AICA, SCA, and PCA origins can be hidden by thrombus and may be embolized during passes.",
        ]
    elif is_mca:
        segment_text = "M1" if "m1" in haystack else "M2" if "m2" in haystack else "MCA"
        side_prefix = f"{side} " if side in {"right", "left"} else ""
        vessel = f"{side_prefix}{segment_text} MCA" if segment_text in {"M1", "M2"} else f"{side_prefix}MCA"
        target = f"{vessel} occlusion".strip()
        territory = f"{side_prefix}MCA territory".strip() if side_prefix else "MCA territory"
        circulation = f"{side_prefix}anterior circulation".strip() if side_prefix else "anterior circulation"
        access_target = circulation
        landmarks = [
            "Aortic arch and great-vessel takeoff; identify tortuosity, bovine arch, stenosis, or dissection risk.",
            "Cervical carotid and petrous/cavernous/supraclinoid ICA to ICA terminus.",
            f"{vessel} course from ICA terminus toward downstream division anatomy.",
            f"Early frontal/temporal {segment_text} branches and final M2 division anatomy on working projections.",
        ]
        perforators = [
            f"ICA terminus and {vessel} are the target inflow/occlusion anatomy; confirm whether clot extends into ICA terminus.",
            "Lenticulostriate perforators from M1 when involved: avoid wire/device prolapse, subintimal passage, or traction injury.",
            f"Early frontal and temporal {segment_text} branches can be hidden by thrombus and may be injured or embolized during passes.",
            "M2 bifurcation/trifurcation branch pattern determines safe distal access-catheter position and stent-retriever landing zone.",
        ]
    elif is_ica or is_aca or is_pca:
        if is_ica:
            vessel = "ICA terminus"
            circulation = f"{side} anterior circulation" if side in {"right", "left"} else "anterior circulation"
            territory = "affected anterior-circulation territory"
        elif is_aca:
            vessel = f"{side} ACA" if side in {"right", "left"} else "ACA"
            circulation = f"{side} anterior circulation" if side in {"right", "left"} else "anterior circulation"
            territory = "ACA territory"
        else:
            vessel = f"{side} PCA" if side in {"right", "left"} else "PCA"
            circulation = "posterior circulation"
            territory = "PCA territory"
        target = f"{vessel} occlusion"
        access_target = circulation
        landmarks = [
            "Aortic arch and great-vessel takeoff; identify tortuosity, stenosis, or dissection risk.",
            f"Catheter route to the {vessel} target vessel with angiographic definition of clot extent and downstream branches.",
            "Branch anatomy and collateral pattern on working projections before device deployment.",
        ]
        perforators = [
            f"{vessel} and adjacent branch/perforator anatomy are at risk during clot crossing and retrieval.",
            "Confirm whether there is tandem cervical disease, underlying stenosis, or more distal embolic branch occlusion.",
        ]
    else:
        vessel = "target vessel"
        target = "target LVO"
        territory = "affected territory"
        circulation = "affected circulation"
        access_target = "access/occlusion anatomy needs input"
        landmarks = [
            "Aortic arch and great-vessel takeoff; identify tortuosity, stenosis, or dissection risk.",
            "Access/occlusion anatomy needs input: confirm cervical route, intracranial target vessel, clot extent, and downstream branch anatomy on CTA/DSA.",
            "Working projections should define the target vessel, distal landing zone, branch anatomy, and collateral pattern before device deployment.",
        ]
        perforators = [
            "Target vessel and adjacent perforator/branch anatomy need input before clot crossing and retrieval.",
            "Confirm whether there is ICA terminus, M1/M2, basilar, tandem cervical, underlying stenosis, or distal embolic anatomy.",
        ]

    return {
        "side": side,
        "vessel": vessel,
        "target": target,
        "territory": territory,
        "circulation": circulation,
        "access_target": access_target,
        "known": bool(is_basilar or is_mca or is_ica or is_aca or is_pca),
        "is_mca": is_mca,
        "is_basilar": is_basilar,
        "landmarks": landmarks,
        "perforators": perforators,
    }


def _thrombectomy_cta_boundary_text(schema: dict[str, Any]) -> str:
    ctx = _thrombectomy_target_context(schema)
    target = str(ctx["target"])
    if bool(ctx["is_mca"]):
        side = str(ctx["side"])
        side_prefix = f"{side} " if side in {"right", "left"} else ""
        return (
            f"{side_prefix}M1 vs ICA terminus, M2 extension/distal branch occlusion, "
            "tandem cervical ICA lesion, or alternate LVO"
        )
    if bool(ctx["is_basilar"]):
        return (
            "basilar trunk vs vertebral artery extension, PCA/SCA/AICA branch involvement, "
            "vertebral tandem lesion, dissection, or alternate posterior-circulation LVO"
        )
    if not bool(ctx["known"]):
        return (
            "target vessel, laterality, proximal vs distal clot extent, tandem cervical lesion, "
            "dissection/ICAD, or alternate LVO"
        )
    return f"{target}, distal branch extension, tandem cervical lesion, dissection/ICAD, or alternate LVO"


def _thrombectomy_combined_strategy_fit(schema: dict[str, Any]) -> str:
    ctx = _thrombectomy_target_context(schema)
    if bool(ctx["is_mca"]):
        return "Large clot burden, ICA terminus/M1 anatomy, need proximal flow control or operator preference."
    if bool(ctx["is_basilar"]):
        return "Large clot burden, vertebral-basilar trunk anatomy, need stable proximal support or operator preference."
    return "Large clot burden, confirmed proximal LVO anatomy, need proximal flow control or operator preference."


def _thrombectomy_defaults(schema: dict[str, Any]) -> dict[str, dict[str, Any]]:
    ctx = _thrombectomy_target_context(schema)
    vessel = str(ctx["vessel"])
    target = str(ctx["target"])
    territory = str(ctx["territory"])
    circulation = str(ctx["circulation"])
    access_target = str(ctx["access_target"])
    known = bool(ctx["known"])
    if bool(ctx["is_mca"]):
        vessel_without_side = vessel
        if str(ctx["side"]) in {"right", "left"} and vessel_without_side.casefold().startswith(f"{ctx['side']} "):
            vessel_without_side = vessel_without_side.split(" ", 1)[1]
        if str(ctx["side"]) == "right":
            mca_note = (
                f"Right {vessel_without_side} syndrome prep: left face/arm > leg weakness or sensory loss, right gaze preference, "
                "left visual field cut and left neglect/extinction; aphasia is not expected unless right-hemisphere language dominance/crossed dominance is present."
            )
        elif str(ctx["side"]) == "left":
            mca_note = (
                f"Left {vessel_without_side} syndrome prep: right face/arm > leg weakness or sensory loss, left gaze preference, "
                "right visual field cut, and aphasia if language-dominant; neglect can occur but is less typical than with nondominant MCA strokes."
            )
        else:
            mca_note = (
                "MCA syndrome prep: contralateral face/arm-predominant motor/sensory deficits, gaze preference, visual field cut, "
                "neglect for nondominant hemisphere, and aphasia for dominant hemisphere involvement."
            )
    else:
        mca_note = "Perforator/branch risk and malignant edema watch depend on the confirmed target vessel and affected territory."
    edema_watch = "malignant MCA edema" if bool(ctx["is_mca"]) else "malignant edema in the affected territory"
    neural_risk = (
        "Lenticulostriate/internal capsule and basal ganglia risk for M1 occlusions; not a brainstem target unless posterior-circulation anatomy is identified."
        if bool(ctx["is_mca"])
        else "Deep perforator and eloquent downstream-territory risk depends on the confirmed occlusion segment; brainstem risk applies to posterior-circulation targets such as basilar occlusion."
    )
    unknown_prompt = "; access/occlusion anatomy needs input" if not known else ""
    cta_boundary = _thrombectomy_cta_boundary_text(schema)
    target_relationship = (
        f"Target-vessel relationship: {target} in the {circulation}; define ICA terminus inflow, M1 perforator segment, M2 division involvement, and downstream branch territory before device landing."
        if bool(ctx["is_mca"])
        else f"Target-vessel relationship: {target} in the {circulation}; define proximal inflow, clot extent, distal branch involvement, perforator/branch anatomy, and downstream territory before device landing."
    )
    cta_display = (
        "CTA head/neck with arch-to-vertex route, clot face, ICA terminus/M1/M2 anatomy, tandem lesion assessment, and collateral views."
        if bool(ctx["is_mca"])
        else "CTA head/neck with arch-to-vertex route, clot face, target-vessel/branch anatomy, tandem lesion or dissection assessment, and collateral views."
    )
    return {
        "imaging_review": {
            "required_studies": [
                "NCCT head: incomplete/needs input for hemorrhage exclusion, early ischemic change, ASPECTS, mass effect, and large established infarct.",
                "CTA head/neck from arch through vertex: incomplete/needs input for occlusion site, clot extent, collaterals, tandem/cervical lesion, arch/cervical access anatomy, and dissection/ICAD clues.",
                "CTP or MR diffusion/perfusion if late window, unknown onset, wake-up stroke, or mismatch/core selection is required; incomplete/needs input for core-penumbra volumes.",
                "Baseline labs/clinical data that change imaging decision: glucose mimic check, anticoagulation/coagulopathy, and IV tPA/TNK timing/status remain incomplete/need input.",
            ],
            "key_findings": [
                "NCCT hemorrhage exclusion: confirm no intracranial hemorrhage, SAH, tumor/abscess mimic, or large completed infarct before EVT/thrombolysis decisions; patient-specific result incomplete/needs input.",
                f"ASPECTS: document affected-territory ASPECTS for anterior-circulation selection; patient-specific score incomplete/needs input for {territory}.",
                f"CTA occlusion site: verify {target}; specifically distinguish {cta_boundary}; patient-specific clot extent incomplete/needs input.",
                "Collateral status: grade pial/leptomeningeal collaterals and delayed filling on CTA/CTP/angiography; poor collaterals increase infarct-core and hemorrhage risk; patient-specific grade incomplete/needs input.",
                "CTP/core-penumbra if late/unknown window: document ischemic core volume, penumbra/hypoperfusion volume, mismatch ratio, and whether profile supports EVT; patient-specific values incomplete/need input.",
                "Arch/cervical access anatomy: review aortic arch type, great-vessel takeoff, carotid/vertebral tortuosity, stenosis/occlusion, calcification, prior stent/endarterectomy, and femoral/radial route feasibility; incomplete/needs input.",
                "Suspected ICAD/dissection: look for fixed focal stenosis, tapered occlusion/flame sign, intimal flap, pseudoaneurysm, re-occlusion tendency, calcified plaque, or truncal-type occlusion that may change rescue angioplasty/stenting and antiplatelet decisions; incomplete/needs input.",
            ],
            "measurements": [
                "ASPECTS numeric score and involved regions: incomplete/needs input.",
                "Core volume (mL), penumbra/hypoperfusion volume (mL), mismatch ratio, and Tmax/CBF thresholds if CTP used: incomplete/needs input.",
                "Clot location/length and distal branch involvement including ICA terminus, M1, M2 extension, or tandem lesion: incomplete/needs input.",
                "Collateral grade and symmetry: incomplete/needs input.",
                "Access measurements/constraints: arch type, cervical ICA stenosis/tortuosity, carotid origin angle, radial/subclavian/femoral suitability: incomplete/needs input.",
            ],
            "anatomic_relationships": [
                target_relationship,
                "Tandem lesion relationship: determine whether cervical ICA/common carotid disease must be crossed or treated before/after intracranial thrombectomy.",
                "Collateral relationship: compare ACA/PCA/leptomeningeal and circle-of-Willis collateral supply to infarct core and penumbra.",
                "Access-route relationship: connect arch/cervical anatomy to femoral vs radial strategy, guide support, and risk of dissection or delay.",
            ],
            "red_flags": [
                "Any hemorrhage on NCCT, extensive completed infarct, severe mass effect, or alternative diagnosis: stop and re-evaluate EVT/thrombolytic plan.",
                "Very low ASPECTS/large ischemic core: large-core EVT may still be considered in selected patients but benefit-risk and trial-aligned criteria require attending/stroke-team decision; incomplete/needs input.",
                "No disabling deficit, very low NIHSS, high baseline mRS, or goals-of-care limits: medical management/no-EVT boundary requires explicit decision documentation.",
                "Poor collaterals or rapidly growing core: raises hemorrhage/edema risk and may narrow treatment window.",
                "Tandem cervical lesion, suspected ICAD/dissection, severe arch/cervical tortuosity, or inaccessible route: anticipate alternate access, rescue angioplasty/stenting, antiplatelet implications, or no-EVT boundary.",
            ],
            "images_to_display_in_or": [
                "NCCT axial ASPECTS/hemorrhage-exclusion images.",
                cta_display,
                "CTP/MR core-penumbra maps if late/unknown window or large-core decision is in play.",
                "Planned DSA working projections for access route, clot crossing, distal landing zone, branch anatomy, and final mTICI assessment.",
            ],
        },
        "anatomy_at_risk": {
            "surgical_corridor": [
                f"Arterial access route to {access_target}: femoral vs radial/brachial route depends on arch, cervical vessel anatomy, and device support.",
                "Guide or balloon-guide catheter positioned for stable support appropriate to the confirmed target vessel before intracranial catheter work.",
            ],
            "landmarks_in_order": list(ctx["landmarks"]),
            "neural_structures": [
                f"{territory} tissue at risk from persistent occlusion, distal emboli, or hemorrhagic transformation.",
                neural_risk,
            ],
            "arteries_perforators_veins_sinuses": list(ctx["perforators"]),
            "functional_structures": [mca_note],
            "variants": [
                "Tandem/cervical carotid stenosis or occlusion may require angioplasty/stenting decision before or after intracranial reperfusion.",
                "Arch/access anatomy may favor radial access or alternate guide support if transfemoral access is slow or unstable.",
            ],
            "no_fly_zones": [
                "Do not force microwire/microcatheter across resistant clot without confirming intraluminal course on roadmap runs.",
                "Avoid deep distal access catheter wedging across branch/perforator-rich target-vessel segments.",
            ],
        },
        "operative_plan": {
            "positioning": "Angio suite thrombectomy setup; anesthesia and BP plan coordinated before arterial puncture.",
            "monitoring": [
                "Continuous hemodynamics, oxygenation/ventilation, neurologic status when feasible, ACT/anticoagulation only as indicated by local protocol and stenting decisions.",
            ],
            "equipment_adjuncts": [
                "Femoral and radial access options available; ultrasound access and closure device plan per anatomy/operator preference.",
                f"Long sheath, guide catheter or balloon-guide catheter, intermediate/distal access or aspiration catheter, microcatheter/microwire, aspiration pump/syringes, stent retriever sized for {vessel} anatomy." if bool(ctx["is_mca"]) else "Long sheath, guide catheter or balloon-guide catheter, intermediate/distal access or aspiration catheter, microcatheter/microwire, aspiration pump/syringes, stent retriever sized for the confirmed target-vessel anatomy.",
                f"Roadmap/DSA working projections for {vessel} course, clot face, distal landing zone, and downstream branch anatomy." if bool(ctx["is_mca"]) else "Roadmap/DSA working projections for the target vessel, clot face, distal landing zone, and downstream branch anatomy.",
            ],
            "critical_steps": [
                f"Confirm LKW/time window, disabling deficit, ASPECTS/core-perfusion selection, thrombolytic status, and {target}{unknown_prompt} before puncture.",
                "Access algorithm: default transfemoral when arch/cervical route is fast and supportive; choose radial/brachial for hostile arch, severe iliofemoral disease, or operator speed advantage; consider direct carotid access only as rare rescue after attending-level risk-benefit discussion when standard routes fail and benefit still justifies delay/risk.",
                "Place sheath and guide or balloon-guide catheter (BGC when feasible for anterior circulation) with stable cervical ICA/proximal support; add distal access/aspiration catheter, intermediate/distal access catheter (DAC), or aspiration catheter appropriate to vessel caliber; perform baseline angiographic run before intracranial work.",
                "Advance DAC/aspiration catheter to the clot face under roadmap guidance; keep the catheter coaxial and avoid wedging into M1 perforator origins or M2 branch ostia." if bool(ctx["is_mca"]) else "Advance DAC/aspiration catheter to the clot face under roadmap guidance; keep the catheter coaxial and avoid wedging into perforator origins or distal branch ostia.",
                "First-pass choice: aspiration-first (ADAPT) for favorable clot-face access and straight anatomy; stent retriever when aspiration access is limited, clot is firm/embedded, or branch incorporation needs scaffolding; combined/Solumbra or BADDASS-style strategy when clot burden, ICA terminus/M1 anatomy, or operator preference favors proximal flow control plus retrieval." if bool(ctx["is_mca"]) else "First-pass choice: aspiration-first (ADAPT) for favorable clot-face access and straight anatomy; stent retriever when aspiration access is limited, clot is firm/embedded, or branch incorporation needs scaffolding; combined/Solumbra-style strategy when clot burden, target-vessel anatomy, or operator preference favors proximal flow control plus retrieval.",
                "Cross clot gently with microwire/microcatheter only after confirming safe trajectory; avoid blind distal wire purchase; use small-volume microcatheter injection only when needed to confirm distal intraluminal position and stop if resistance, perforation concern, or subintimal course is suspected.",
                "If using stent retriever, size to parent/branch vessel per device IFU; deploy across the M1 clot with adequate distal purchase in a safe M2 segment without landing in tiny/tortuous eloquent branches; allow integration time per operator/device practice." if bool(ctx["is_mca"]) else "If using stent retriever, size to parent/branch vessel per device IFU; deploy across the clot with adequate distal purchase in a safe downstream segment without landing in tiny/tortuous eloquent branches; allow integration time per operator/device practice.",
                "Retrieve under continuous aspiration through the DAC/guide and BGC flow arrest/proximal aspiration when used; maintain coaxial tension, avoid excessive traction across the carotid siphon/M1 bifurcation, and inspect clot/device after retrieval." if bool(ctx["is_mca"]) else "Retrieve under continuous aspiration through the DAC/guide and BGC or guide aspiration when used; maintain coaxial tension, avoid excessive traction across tortuous branch points, and inspect clot/device after retrieval.",
                "After each pass, obtain control angiography, document mTICI, distal emboli/new-territory emboli, vasospasm/dissection/extravasation, and whether the residual occlusion is reachable; switch technique if the first approach fails because of access, clot consistency, or embolization pattern.",
                "Stop/switch criteria: stop once mTICI 2b/2c/3 is achieved without a safe treatable residual; limit repeated futile passes; escalate to rescue angioplasty/stenting/antiplatelet strategy for suspected ICAD or tandem lesion only after hemorrhage/thrombolytic risk review; stop for perforation, SAH/extravasation, unsafe distal anatomy, or risk exceeding benefit.",
                "Final run checklist: cervical access vessel, intracranial target territory, mTICI score, distal/new-territory emboli, perforator/branch patency, vasospasm/dissection, extravasation, and access-site closure plan.",
            ],
            "decision_points": [
                f"Aspiration-first vs stent retriever vs combined technique for {target} clot burden and branch anatomy.",
                "Balloon-guide flow arrest/use of aspiration during retrieval vs guide support limitations.",
                "Management of tandem cervical lesion: angioplasty/stenting timing and antiplatelet implications.",
                "When to stop after mTICI target achieved or after unsafe/futile passes.",
            ],
            "stop_points": [
                "Perforation, contrast extravasation, or SAH pattern: stop passes, reverse/normalize anticoagulation as applicable, manage BP, and obtain control angiography/CT.",
                "New severe vasospasm, dissection, or access instability that makes further passes unsafe.",
                "Adequate mTICI reperfusion with no treatable residual proximal occlusion.",
            ],
        },
        "risk_and_rescue": {
            "likely_complications": [
                "Vasospasm from catheter/device manipulation; treat with pause, intra-arterial vasodilator per protocol, and gentler catheter position.",
                "Distal emboli or embolus to new territory; reassess full angiographic tree and treat reachable disabling occlusions when safe.",
                "Access complications: access-site hematoma/hemorrhage, pseudoaneurysm, or retroperitoneal bleeding; hold pressure, check hemodynamics/labs, ultrasound/CTA as needed.",
            ],
            "catastrophic_complications": [
                "Vessel perforation with SAH/contrast extravasation during wire, microcatheter, aspiration catheter, or stent-retriever manipulation.",
                f"{vessel} dissection or flow-limiting cervical/proximal vessel injury.",
                f"Failed recanalization or early re-occlusion with persistent {target} syndrome.",
                f"Symptomatic ICH or {edema_watch} after reperfusion.",
            ],
            "mitigation": [
                "Use roadmap guidance, confirm intraluminal clot crossing, avoid forceful advancement, and reassess after each pass.",
                "Maintain BP targets appropriate to occlusion/reperfusion status and hemorrhage risk; avoid hypotension before reperfusion.",
                "Minimize unnecessary passes; consider rescue angioplasty/stenting, antithrombotics, or medical management only after weighing hemorrhage/thrombolytic status.",
            ],
            "rescue_triggers": [
                "Extravasation/SAH: stop device manipulation, lower BP per attending/anesthesia, reverse anticoagulation if relevant, consider balloon tamponade, emergent CT/neuro-ICU pathway.",
                "Dissection/flow limitation: maintain access, angiographic characterization, consider stent/angioplasty or antithrombotic plan with hemorrhage risk review.",
                "Re-occlusion or failed recanalization: repeat angiography, evaluate underlying stenosis/tandem lesion, consider rescue therapy or stop if risk exceeds benefit.",
            ],
        },
        "postop_plan": {
            "destination": "Neuro-ICU/stroke unit capable of post-reperfusion monitoring and rapid CT/CTA response.",
            "neuro_checks": "Frequent neuro checks per stroke/thrombectomy protocol; escalate for NIHSS worsening, headache, emesis, declining arousal, or access-site instability.",
            "bp_goals": "Framework only—verify local stroke/anesthesia protocol and patient comorbidities; set BP target by reperfusion result, hemorrhage/extravasation concern, and IV tPA/TNK status. Before reperfusion avoid hypotension and large BP drops; pre-EVT ceiling differs by thrombolytic status (commonly <=185/110 if IV alteplase/tenecteplase candidate/treated, otherwise often permissive up to <=220/120 if no thrombolytic unless another indication). After successful mTICI 2b-3 reperfusion many protocols use tighter SBP target examples such as <160 or 120-140/140-160 range; after incomplete/failed reperfusion use a more permissive strategy to support collateral flow unless hemorrhage, extravasation, severe edema, cardiac/aortic indication, or other reason mandates lowering. If hemorrhage/extravasation occurs: immediate controlled lowering per attending, stop antithrombotics, emergent CT, and reversal/hemorrhage pathway as applicable.",
            "imaging_timing": "Noncontrast head CT at protocol timing (commonly about 24 hours after IV tPA/TNK and/or EVT before routine antithrombotic start) or immediately for neurologic decline, severe headache, emesis, hypertension crisis, or extravasation concern; CTA/CTP/MRI if re-occlusion or infarct evolution concern.",
            "medications": [
                "Antiplatelet/anticoagulation timing requires input: after IV tPA/TNK, avoid antiplatelet/anticoagulant therapy for the first 24 hours unless an exceptional stent/rescue indication is explicitly accepted; obtain follow-up CT/MRI excluding hemorrhage before routine aspirin/anticoagulation. Without thrombolytic, antiplatelet timing still depends on CT, stent placement, hemorrhage risk, and stroke-team protocol.",
                "High-intensity statin and stroke secondary prevention per stroke team when appropriate.",
            ],
            "drains_devices": [
                "Access-site closure device or radial band protocol; document pulses, groin/wrist checks, and leg/hand perfusion.",
            ],
            "labs_monitoring": [
                "Post-procedure NIHSS trend, glucose/temperature/oxygenation, CBC/coags if bleeding or thrombolytic/coagulopathy concern.",
                f"Watch for hemorrhagic transformation and {edema_watch}; early neurosurgery notification for hemicraniectomy candidacy if swelling evolves.",
            ],
            "dvt_prophylaxis": "Mechanical prophylaxis initially; chemical prophylaxis timing after follow-up CT and thrombolytic/hemorrhage review.",
            "discharge_criteria": [
                "Stable neurologic exam, completed stroke mechanism workup/secondary prevention plan, safe swallow/rehab disposition, and stable access site.",
            ],
        },
    }

def _meningioma_context(schema: dict[str, Any]) -> dict[str, str]:
    """Derive parasagittal/convexity meningioma wording without inventing patient facts."""
    topic = str(schema.get("topic", ""))
    laterality = _structured_case_value(schema, "laterality").strip().casefold()
    side = laterality if laterality in {"right", "left", "bilateral"} else ""
    size = _structured_case_value(schema, "size") or "size needs input"
    raw_location = _structured_case_value(schema, "anatomic_location") or "convexity/parasagittal location"
    pathology = _structured_case_value(schema, "pathology") or "meningioma"
    haystack = " ".join(part for part in (topic, raw_location, pathology) if part).casefold()
    is_parasagittal = any(term in haystack for term in ("parasagittal", "superior sagittal", "sss", "sagittal sinus"))
    location_parts = [part.strip() for part in raw_location.split(";") if part.strip()]
    location = next((part for part in location_parts if "parasagittal" in part.casefold()), raw_location)
    corridor = "parasagittal craniotomy" if is_parasagittal else "convexity craniotomy"
    side_prefix = f"{side} " if side in {"right", "left"} else ""
    lesion = f"{side_prefix}{size} {location} meningioma".replace("  ", " ").strip()
    sinus = "superior sagittal sinus (SSS)" if is_parasagittal else "adjacent cortical veins and dural venous sinuses"
    if is_parasagittal and "abutting" in haystack:
        diagnosis = f"{lesion} abutting {sinus}; invasion unknown"
    elif is_parasagittal:
        diagnosis = f"{lesion} near {sinus}; sinus invasion unknown"
    else:
        diagnosis = lesion
    return {
        "topic": topic,
        "side": side,
        "size": size,
        "location": location,
        "pathology": pathology,
        "lesion": lesion,
        "diagnosis": diagnosis,
        "corridor": corridor,
        "sinus": sinus,
    }


def _meningioma_defaults(schema: dict[str, Any]) -> dict[str, dict[str, Any]]:
    ctx = _meningioma_context(schema)
    lesion = ctx["lesion"]
    sinus = ctx["sinus"]
    corridor = ctx["corridor"]
    return {
        "imaging_review": {
            "required_studies": [
                "MRI brain with contrast to define dural attachment, tumor-cortex interface, edema, and relationship to eloquent cortex.",
                "MRV or CTV when the tumor abuts the superior sagittal sinus to assess sinus patency, invasion versus compression, collateral venous drainage, and dominant cortical veins.",
                "CT head/bone windows if hyperostosis, calcification, or planned bone removal/reconstruction may change the craniotomy.",
            ],
            "key_findings": [
                f"Confirm {lesion} and whether the sinus relationship is abutment, narrowing, invasion, occlusion, or preserved flow.",
                "Assess peritumoral edema, cortical invasion/cleft, mass effect, and proximity to motor/sensory cortex or supplementary motor area when the AP location suggests it.",
                "Map cortical and bridging veins entering the SSS; identify venous lacunae and veins that must not be sacrificed.",
            ],
            "measurements": [
                "Largest diameter, dural base, sinus contact length, degree of sinus narrowing, edema burden, and distance to eloquent cortex.",
            ],
            "anatomic_relationships": [
                f"Tumor relationship to {sinus}, falx, parasagittal cortex, bridging veins, cortical draining veins, and arterial supply.",
                "Review whether the tumor crosses midline/falx or involves bone/dura requiring reconstruction.",
            ],
            "red_flags": [
                "Absent or narrowed SSS flow, dominant bridging-vein dependence, extensive edema, or unclear sinus wall involvement may change extent-of-resection goals.",
            ],
            "images_to_display_in_or": [
                "Contrast T1 axial/coronal/sagittal through tumor and SSS, T2/FLAIR edema map, MRV/CTV venous phase, and navigation-loaded tumor/sinus/vein views.",
            ],
        },
        "anatomy_at_risk": {
            "surgical_corridor": [
                f"{corridor.capitalize()} planned around the lesion while protecting the midline venous drainage route.",
                "Expose the sinus edge deliberately; avoid blind medial burr holes or dural opening that can enter SSS, venous lacunae, or bridging veins.",
            ],
            "landmarks_in_order": [
                "Midline/sagittal suture, craniotomy margins crossing or flanking the sinus as planned, dura, falx when relevant, tumor dural base, and tumor-cortex arachnoid plane.",
                "Define cortical draining veins and bridging veins before dural opening and maintain venous outflow throughout dissection.",
            ],
            "neural_structures": [
                "Parasagittal frontal/parietal cortex, motor strip, sensory cortex, and supplementary motor area depending on lesion AP position.",
                "New leg-predominant weakness, SMA syndrome, seizure, or sensory deficit can result from cortical or venous injury.",
            ],
            "arteries_perforators_veins_sinuses": [
                "Superior sagittal sinus, parasagittal venous lacunae, cortical bridging veins, and cortical draining veins are the dominant danger structures.",
                "Arterial supply may include middle meningeal/dural feeders and pial/cortical supply; pial supply changes the safe devascularization sequence.",
            ],
            "functional_structures": [
                "Motor/sensory cortex and SMA should be localized with imaging/navigation when close to the lesion.",
            ],
            "variants": [
                "Patent versus occluded sinus, suspected sinus wall invasion, dominant parasagittal veins, falcine extension, hyperostotic bone, and marked edema all change the safe resection endpoint.",
            ],
            "no_fly_zones": [
                "Do not sacrifice a patent SSS or dominant bridging vein for marginal Simpson-grade gain without an explicit attending plan.",
                "Do not pursue tumor within a patent/invaded sinus if bleeding or venous outflow risk outweighs benefit; leave adherent sinus tumor when safer.",
            ],
        },
        "operative_plan": {
            "positioning": "Supine or lateral/park-bench variant per lesion location with head fixed, navigation registered, venous air embolism precautions considered for midline/sinus exposure, and access to both sides of midline if needed.",
            "monitoring": [
                "Baseline motor/sensory exam and seizure history; confirm whether lesion location makes cortical mapping relevant.",
                "Navigation with tumor, sinus, and cortical vein anatomy reviewed before incision and dural opening.",
            ],
            "equipment_adjuncts": [
                "Navigation, microscope/loupes, bipolar, ultrasonic aspirator, hemostatic agents, dural substitute/graft, bone flap fixation, and venous bleeding control materials.",
            ],
            "critical_steps": [
                f"Plan {corridor} incision and bone work to expose tumor margins and safe sinus edge without injuring the SSS or bridging veins during burr holes and bone flap elevation.",
                "Open dura based on tumor/sinus relationship, preserving cortical veins and leaving a cuff when needed near venous structures.",
                "Early dural devascularization when safe, then internal debulking to relax the capsule before circumferential extracapsular dissection along the arachnoid plane.",
                "Work around cortical/bridging veins rather than avulsing them; define the sinus interface last if adherent or invasive.",
                "At the sinus/falx attachment, make a practical venous preservation decision: preserve SSS/veins first, peel/coagulate only if the plane is safe, and leave planned residual when the sinus or a dominant vein is threatened.",
                "Close with watertight dural reconstruction as feasible, address involved/hyperostotic bone per plan, and maintain hemostasis after venous pressure changes.",
            ],
            "decision_points": [
                "Practical venous preservation questions: is the SSS patent, is there convincing wall invasion rather than simple abutment/compression, and are there dominant bridging veins near the tumor?",
                "If the sinus wall plane or a bridging vein is unsafe, bias toward work-around or small planned residual rather than chasing Simpson-grade escalation.",
                "Observation or SRS/fractionated RT may be preferred for small/asymptomatic tumors, high-risk sinus involvement, poor surgical candidate, or planned residual.",
            ],
            "stop_points": [
                "Stop sinus-side dissection for uncontrolled venous bleeding, unclear sinus wall plane, dominant bridging vein compromise, or cortical swelling/venous congestion.",
                "Convert to subtotal resection/residual-on-sinus strategy when safe venous preservation conflicts with complete resection.",
            ],
            "closure_reconstruction": [
                "Dural closure/graft, management of invaded dura/falx, bone flap or hyperostotic bone plan, hemostasis, drain decision, and postop venous imaging plan if sinus manipulation occurred.",
            ],
            "attending_preferences_questions": [
                "Extent-of-resection goal at SSS, threshold for leaving sinus-adherent tumor, need for MRV/CTV, embolization consideration, mapping relevance, and postop steroid/AED/imaging protocol.",
            ],
        },
        "risk_and_rescue": {
            "likely_complications": [
                "Seizure, cerebral edema, venous congestion, new motor/sensory deficit, wound/CSF leak issues, and residual/recurrent tumor if sinus-adherent disease is left.",
            ],
            "catastrophic_complications": [
                "SSS or venous lacuna injury with major venous bleeding or air embolism risk.",
                "Dominant bridging vein sacrifice or sinus thrombosis causing venous infarct, hemorrhagic venous conversion, swelling, seizure, or neurologic deficit.",
                "Intracranial hemorrhage, malignant edema, or infarct requiring urgent imaging, ICU management, and possible reoperation/decompression.",
            ],
            "mitigation": [
                "Preop MRV/CTV for SSS patency and venous anatomy; preserve dominant cortical/bridging veins and avoid unnecessary sinus manipulation.",
                "Maintain meticulous hemostasis and avoid excessive retraction; use debulking to reduce traction on cortex and veins.",
                "Steroid/AED and BP plans per surgeon; monitor for edema, seizure, and venous outflow complications.",
            ],
            "rescue_triggers": [
                "If sinus bleeding occurs: tamponade/packing, lower venous pressure as appropriate, maintain visualization, repair only under the attending plan, and avoid blind coagulation of sinus or major veins.",
                "New postop weakness, aphasia/SMA syndrome concern, seizure, declining mental status, or severe headache: urgent CT/CTA/CTV or MRI/MRV depending on suspected hemorrhage/venous thrombosis/edema.",
                "Venous infarct or sinus thrombosis concern: urgent imaging, ICU-level monitoring, edema/ICP management, and attending-directed anticoagulation/reoperation decisions.",
            ],
        },
        "postop_plan": {
            "destination": "PACU then ICU/stepdown consideration for large parasagittal/SSS-adjacent tumors, edema, sinus manipulation, or neurologic risk.",
            "neuro_checks": "Serial exam focused on contralateral leg/arm strength, sensory changes, SMA/language if frontal dominant-side risk, seizures, and mental status.",
            "bp_goals": "Avoid hypertension that worsens hemorrhage/edema while maintaining venous/cerebral perfusion per surgeon/anesthesia plan.",
            "imaging_timing": "Postop MRI for extent of resection/residual and CT/CTV/MRV urgently if deficit, hemorrhage, venous infarct, or sinus thrombosis is suspected.",
            "medications": [
                "Steroid taper, antiseizure plan, analgesia, antiemetics, and DVT prophylaxis timing per surgeon and hemorrhage/venous thrombosis risk.",
            ],
            "drains_devices": [
                "Drain and head-wrap management per closure and sinus exposure; monitor wound for CSF leak or venous bleeding.",
            ],
            "labs_monitoring": [
                "Monitor sodium, edema symptoms, seizure activity, wound drainage, new focal deficits, and signs of venous congestion/infarct.",
            ],
            "dvt_prophylaxis": "Mechanical prophylaxis immediately; chemoprophylaxis timing individualized to postoperative imaging and bleeding risk.",
            "discharge_criteria": [
                "Stable neurologic exam, seizure/edema plan, wound stability, safe mobility, steroid/AED instructions, and follow-up pathology/imaging plan.",
            ],
        },
    }


def _family_defaults(schema: dict[str, Any], section: str) -> dict[str, Any]:
    if _is_thrombectomy(schema):
        return _thrombectomy_defaults(schema).get(section, {})
    if _is_acdf(schema):
        return _acdf_defaults(schema).get(section, {})
    if _is_convexity_meningioma(schema):
        return _meningioma_defaults(schema).get(section, {})
    return {}


def _section_list(schema: dict[str, Any], section: str, key: str) -> list[Any]:
    case_section = schema["case"][section]
    items = case_section.get(key, [])
    if items:
        return items
    defaults = _family_defaults(schema, section)
    value = defaults.get(key, []) if isinstance(defaults, dict) else []
    return list(value) if isinstance(value, list) else []


def _section_scalar(schema: dict[str, Any], section: str, key: str, missing: str = "`needs input`") -> str:
    case_section = schema["case"][section]
    value = case_section.get(key)
    if value:
        return str(value)
    defaults = _family_defaults(schema, section)
    default_value = defaults.get(key) if isinstance(defaults, dict) else None
    return str(default_value) if default_value else missing


def _inline_status(schema: dict[str, Any]) -> str:
    return f"`{schema.get('status', DEFAULT_STATUS)}` `needs clinician verification`"


def _case_field_value(
    field: dict[str, Any] | None,
    *,
    missing: str = "`needs input`",
    low_confidence_label: str | None = None,
) -> str:
    if not isinstance(field, dict) or not field.get("value"):
        return missing
    confidence = float(field.get("confidence") or 0.0)
    value = str(field["value"])
    if low_confidence_label and confidence < 0.8:
        return f"{low_confidence_label}: {value} (low confidence {confidence:.2f})"
    return value


def _case_modifiers(structured_case: dict[str, Any]) -> list[str]:
    modifiers: list[str] = []
    for key in ("laterality", "level_or_segment", "size", "anatomic_location"):
        field = structured_case.get(key)
        if isinstance(field, dict) and field.get("value"):
            modifiers.append(f"{key.replace('_', ' ')}: {field['value']}")
    for key, label in (
        ("patient_modifiers", "patient modifier"),
        ("imaging_modifiers", "imaging modifier"),
    ):
        for field in structured_case.get(key, []) or []:
            if isinstance(field, dict) and field.get("value"):
                modifiers.append(f"{label}: {field['value']}")
    return modifiers


def _render_structured_case_summary(schema: dict[str, Any]) -> str:
    structured_case = schema.get("structured_case") or {}
    if not isinstance(structured_case, dict) or not structured_case:
        return ""

    procedure_raw = structured_case.get("procedure")
    approach_raw = structured_case.get("approach")
    procedure: dict[str, Any] = procedure_raw if isinstance(procedure_raw, dict) else {}
    approach: dict[str, Any] = approach_raw if isinstance(approach_raw, dict) else {}
    procedure_missing_or_low = not procedure.get("value") or float(procedure.get("confidence") or 0.0) < 0.8
    approach_missing_or_low = not approach.get("value") or float(approach.get("confidence") or 0.0) < 0.8
    procedure_family = schema.get("procedure_family") or {}
    family_display = "generic/degraded"
    if isinstance(procedure_family, dict) and procedure_family.get("display_name"):
        family_display = f"{procedure_family['display_name']} (`{procedure_family.get('id', '')}`)"
    elif isinstance(structured_case.get("procedure_family"), dict) and structured_case["procedure_family"].get("value"):
        family_display = str(structured_case["procedure_family"]["value"])

    missing_facts = structured_case.get("missing_critical_facts", []) or []
    modifiers = _case_modifiers(structured_case)
    degradation_lines: list[str] = []
    if structured_case.get("degraded"):
        degradation_lines.append("- Degradation status: degraded/generic case summary")
        if structured_case.get("degradation_reason"):
            degradation_lines.append(f"- Degradation reason: {structured_case['degradation_reason']}")
    else:
        degradation_lines.append("- Degradation status: not degraded")

    procedure_text = _case_field_value(
        procedure,
        missing="generic/degraded — no booked procedure identified",
        low_confidence_label="generic/degraded",
    )
    approach_text = _case_field_value(
        approach,
        missing="generic/degraded — no booked approach identified",
        low_confidence_label="generic/degraded",
    )
    if procedure_missing_or_low:
        procedure_text += "; do not treat as a confirmed booked procedure"
    if approach_missing_or_low:
        approach_text += "; do not treat as a confirmed booked approach"

    return f"""## Parsed Case Summary

- Raw case input: {structured_case.get("raw_input") or schema.get("topic", "")}
- Parsed pathology: {_case_field_value(structured_case.get("pathology") if isinstance(structured_case.get("pathology"), dict) else {})}
- Parsed procedure: {procedure_text}
- Parsed approach: {approach_text}
- Procedure family: {family_display}
- Broad profile: {_case_field_value(structured_case.get("broad_profile") if isinstance(structured_case.get("broad_profile"), dict) else {}, missing=schema.get("case_profile", "general"))}
- Parsed modifiers:
{_list_block(modifiers)}
- Missing critical facts:
{_list_block(list(missing_facts), empty="- none identified")}
{chr(10).join(degradation_lines)}

"""


def _render_readme(schema: dict[str, Any]) -> str:
    topic = schema["topic"]
    profile = schema["case_profile"]
    snapshot = schema["case"]["case_snapshot"]
    evidence = schema["case"]["evidence"]
    if _is_thrombectomy(schema):
        ctx = _thrombectomy_target_context(schema)
        target_descriptor = ctx["target"]
        management = f"Confirm EVT eligibility for {ctx['target']} and proceed with mechanical thrombectomy only if go/no-go facts support benefit."
        approaches = "Femoral vs radial access; guide/BGC plus DAC/aspiration catheter; aspiration-first, stent-retriever, or combined first pass per anatomy/operator preference."
        tradeoff = "Fast reperfusion vs hemorrhage/edema, perforation/dissection, futile passes, tandem/ICAD rescue antithrombotic risk, and goals of care."
    elif _is_acdf(schema):
        ctx = _acdf_context(schema)
        target_descriptor = f"{ctx['root_target']} at {ctx['level']}"
        management = (
            f"Decompress the {ctx['root_target']} at {ctx['level']} and achieve a stable fusion while verifying "
            "approach side, level localization, and implant / fusion construct before incision."
        )
        approaches = (
            "Primary ACDF with discectomy/foraminal decompression, endplate preparation, graft/cage, and plate/screws or stand-alone device; "
            "posterior cervical foraminotomy is the main motion-preserving alternative for selected isolated foraminal radiculopathy."
        )
        tradeoff = (
            "Anterior decompression/fusion durability and disc-space restoration vs dysphagia, recurrent laryngeal nerve/voice risk, "
            "hematoma/airway risk, vertebral artery risk during lateral uncinate work, pseudarthrosis, and adjacent-segment stress."
        )
    elif _is_convexity_meningioma(schema):
        ctx = _meningioma_context(schema)
        target_descriptor = f"{ctx['lesion']} adjacent to {ctx['sinus']}"
        management = (
            f"Plan {ctx['corridor']} and meningioma resection strategy around MRV/CTV-defined sinus patency, "
            "bridging veins, eloquent cortex proximity, and an explicit stop point for sinus-adherent tumor."
        )
        approaches = (
            "Parasagittal/convexity craniotomy with dural devascularization, internal debulking, extracapsular dissection, "
            "and sinus/bridging-vein preservation; observation or SRS/fractionated RT may fit selected asymptomatic, high-risk, or residual sinus disease."
        )
        tradeoff = (
            "Maximal safe resection and Simpson-grade/recurrence benefit vs SSS injury, dominant bridging-vein sacrifice, venous infarct, edema/seizure, "
            "and neurologic deficit; planned residual on a patent sinus may be safer than aggressive removal."
        )
    else:
        target_descriptor = (snapshot.get("laterality") or "laterality `needs input`") + " target `needs input`"
        management = "`needs input`"
        approaches = "`needs input`"
        tradeoff = "`needs input`"
    return f"""# {topic} Case Prep

## One-Line Case

{snapshot.get("one_line_thesis") or "`needs input`: one-line operative thesis"}

## Preparation Status

- Overall: {_inline_status(schema)}
- Profile: `{profile}`
- Evidence sources included: {len(evidence.get("key_sources", []))}
- Unverified fields remain visible as `needs input`.

## Key Decisions

- Diagnosis/target: {snapshot.get("diagnosis") or "`needs input`"}; {target_descriptor}
- Planned procedure: {snapshot.get("planned_procedure") or "`needs input`"}
- Management question: {management}
- Candidate approaches: {approaches}
- Main risk tradeoff: {tradeoff}

## Start Here

- Morning-of-case one-page view: `00-morning-of-case.md`

## Files

{_list_block(CANONICAL_MARKDOWN_FILES[1:])}
"""


def _render_acdf_morning_of_case(schema: dict[str, Any]) -> str:
    ctx = _acdf_context(schema)
    snapshot = schema["case"]["case_snapshot"]
    missing_facts = schema.get("structured_case", {}).get("missing_critical_facts", []) or []
    missing_text = ", ".join(str(item) for item in missing_facts) or "none identified"
    return f"""# Morning Of Case - {schema['topic']}

## Diagnosis / Level / Procedure

- Diagnosis: {snapshot.get('diagnosis') or ctx['diagnosis']}
- Level: {ctx['level']}
- Planned procedure: {snapshot.get('planned_procedure') or ctx['procedure']}
- Objective: {snapshot.get('operative_objective') or f"Decompress the {ctx['root_target']} and achieve stable fusion."}
- Missing critical facts: {missing_text}

## Go / No-Go Missing Facts

| Fact | Status before incision | Why it matters |
|---|---|---|
| Side/site/level localization | confirm with fluoroscopy before discectomy | Wrong-level ACDF is a never-event; localization must be explicit at {ctx['level']}. |
| Approach side | incomplete/needs input unless attending specifies | Prior surgery, symptoms, RLN/voice history, and exposure preference affect side choice. |
| Implant / fusion construct | incomplete/needs input | Cage/graft, plate/screws, zero-profile, or stand-alone device changes sizing, equipment, and postop restrictions. |
| Airway/dysphagia baseline | incomplete/needs input | Baseline voice/swallow and airway risk determine postop monitoring and urgency for hematoma/dysphagia. |
| Fluoroscopy | must be available | Needed for initial level localization, implant sizing, and final AP/lateral confirmation. |

## Imaging / Anatomy Checklist

- Confirm MRI/radiographs match {ctx['diagnosis']} at {ctx['level']} and the {ctx['root_target']}.
- Review foraminal disc-osteophyte/uncinate compression, central canal stenosis, cord signal, alignment, and collapse/kyphosis.
- Identify anterior cervical exposure constraints: sternocleidomastoid/carotid sheath lateral, tracheoesophageal complex/esophagus medial, longus colli over disc space.
- Recheck vertebral artery risk before aggressive lateral uncinate/foraminal decompression.

## Operative Flow Priorities

- Exposure: anterior cervical corridor, protect esophagus/trachea and carotid sheath, elevate longus colli.
- Localization: lateral fluoroscopy at {ctx['level']} before annulotomy/discectomy; repeat if uncertain.
- Decompression: discectomy, posterior osteophyte/PLL work as indicated, and foraminal decompression of the {ctx['root_target']}.
- Fusion: endplate preparation, graft/cage trial/placement, plate/screws or stand-alone fixation per implant / fusion construct plan, final fluoroscopy.

## Rescue / Postop Watch

- Hematoma/airway compromise: neck swelling, stridor, respiratory distress, rapidly progressive dysphagia = immediate airway/surgeon response.
- Recurrent laryngeal nerve/voice change and dysphagia: document baseline, reassess early, escalate persistent or severe findings.
- Esophageal injury or vertebral artery injury: stop, inspect/control, and escalate immediately.
"""


def _render_morning_of_case(schema: dict[str, Any]) -> str:
    if _is_acdf(schema):
        return _render_acdf_morning_of_case(schema)
    if _is_convexity_meningioma(schema):
        ctx = _meningioma_context(schema)
        snapshot = schema["case"]["case_snapshot"]
        missing_facts = schema.get("structured_case", {}).get("missing_critical_facts", []) or []
        missing_text = ", ".join(str(item) for item in missing_facts) or "none identified"
        return f"""# Morning Of Case - {schema['topic']}

## Diagnosis / Procedure / Objective

- Diagnosis: {snapshot.get('diagnosis') or ctx['lesion']}
- Planned procedure: {snapshot.get('planned_procedure') or 'meningioma resection / craniotomy prep domain'}
- Objective: {snapshot.get('operative_objective') or f"Maximal safe resection while preserving {ctx['sinus']} and venous drainage."}
- Missing critical facts: {missing_text}

## Go / No-Go Missing Facts

| Fact | Status before incision | Why it matters |
|---|---|---|
| SSS patency/invasion | incomplete/needs input | Determines whether to peel, reconstruct, leave residual, or avoid sinus entry. |
| Bridging/cortical veins | incomplete/needs input | Dominant veins may be no-fly structures; injury can cause venous infarct/hemorrhage. |
| AP location vs motor/SMA | incomplete/needs input | Drives whether mapping is relevant and focuses postop deficit watch. |
| Edema/seizure history | incomplete/needs input | Affects steroids, AED plan, ICU threshold, and swelling risk. |
| Extent-of-resection goal | incomplete/needs input | Sets Simpson-grade vs venous-safety tradeoff before the dangerous sinus interface. |

## Imaging Must-Review

- Contrast MRI: dural base, tumor-cortex cleft, edema, bone/falx involvement, and relationship to motor/sensory cortex or SMA.
- MRV/CTV: SSS patency, narrowing/invasion versus abutment, venous lacunae, collateral drainage, and dominant bridging veins.
- Navigation: load tumor, sinus, falx/midline, cortical veins, and eloquent cortex landmarks when available.

## Operative Focus

- Plan {ctx['corridor']} and burr holes around the sinus edge; avoid blind medial entry into SSS/lacunae.
- Preserve cortical and bridging veins; internally debulk before mobilizing capsule off cortex/veins.
- Treat the sinus interface as the late decision point: remove/peel/reconstruct only if safe, otherwise leave planned residual.

## Rescue Focus

- SSS bleeding: tamponade/packing, maintain visualization, control venous pressure with anesthesia, repair/reconstruct only under attending plan.
- Venous congestion/new deficit/seizure: urgent imaging for hemorrhage, edema, venous infarct, or sinus thrombosis; escalate ICU management.
- Stop dissection for dominant vein compromise, cortical swelling/venous congestion, or unclear sinus wall plane.
"""
    if not _is_thrombectomy(schema):
        return f"""# Morning Of Case - {schema['topic']}

Use the case summary, imaging review, operative plan, rescue plan, postop plan, and open questions before the case.
"""
    ctx = _thrombectomy_target_context(schema)
    facts = _case_facts(schema)
    snapshot = schema["case"]["case_snapshot"]
    procedure = snapshot.get("planned_procedure") or "mechanical thrombectomy"
    diagnosis = snapshot.get("diagnosis") or "acute ischemic stroke"
    return f"""# Morning Of Case - {schema['topic']}

## Diagnosis / Target / Procedure

- Diagnosis: {diagnosis}
- Target: {ctx['target']} in the {ctx['circulation']}
- Planned procedure: {procedure}
- Objective: {snapshot.get('operative_objective') or 'safe reperfusion with mTICI 2b/2c/3 goal'}

{_render_thrombectomy_known_facts(schema)}## Go / No-Go Missing Facts

| Fact | Status before puncture | Why it matters |
|---|---|---|
| LKW/time window | {missing_or_confirm_line(facts, "last_known_well")} | Determines early vs late/unknown-window selection and urgency. |
| NIHSS/disabling deficit | {missing_or_confirm_line(facts, "nihss")} | EVT benefit depends on disabling deficit; low-NIHSS LVO needs explicit judgment. |
| ASPECTS/core | {missing_or_confirm_line(facts, "aspects")} | Screens completed infarct/large core and hemorrhage/edema risk. |
| Hemorrhage exclusion | incomplete/needs input | Any ICH/SAH/stroke mimic changes or stops EVT/thrombolytic plan. |
| Thrombolytic status | incomplete/needs input | Drives BP ceiling, antithrombotic hold, hemorrhage risk, and rescue stent tradeoffs. |
| Baseline mRS/goals of care | incomplete/needs input | Poor premorbid function or limits of care may make EVT nonbeneficial. |

## Imaging Checklist

- NCCT: hemorrhage exclusion, ASPECTS, early ischemic change, mass effect, large completed infarct.
- CTA head/neck: confirm {ctx['target']}, clot extent, collaterals, arch-to-target access, tandem cervical lesion, dissection/ICAD clues.
- CTP/MR perfusion or DWI/perfusion: obtain/verify if late window, wake-up/unknown onset, large-core question, or clinical-imaging mismatch.
- Angio planning: working projections for clot face, distal landing zone, perforator/branch anatomy, and final mTICI run.
- Access anatomy: femoral/radial feasibility, arch type, carotid/vertebral tortuosity/stenosis, prior stent/CEA, and direct carotid rescue feasibility only if needed.

## Access / Device Plan

- Access: default fastest stable femoral or radial route; switch early if hostile arch, iliofemoral disease, radial/subclavian limitation, or unstable support delays reperfusion.
- Guide support: guide catheter or BGC when feasible for anterior circulation; confirm cervical/proximal support before intracranial work.
- Intracranial tools: DAC/intermediate or aspiration catheter to clot face, microcatheter/microwire, aspiration pump/syringes, stent retriever sized to target vessel.
- First-pass options: aspiration-first for favorable clot-face access; stent retriever when aspiration access/clot mechanics are unfavorable; combined/Solumbra/BGC strategy for {_thrombectomy_combined_strategy_fit(schema).rstrip('.').casefold()}.

## First-Pass Plan And Switch / Stop Criteria

| Step | Plan | Switch/stop trigger |
|---|---|---|
| Baseline run | Confirm target, collaterals, tandem disease, and safe working projection. | Stop/reconsider if no treatable LVO or hemorrhage/extravasation concern. |
| Clot crossing | Gentle roadmap-guided microwire/microcatheter crossing; confirm intraluminal distal position. | Stop if resistance, subintimal course, perforation, or unsafe distal anatomy. |
| First pass | Aspiration, stent retriever, or combined pass per clot face/anatomy. | Switch if no reperfusion, clot fragmentation, poor catheter purchase, or embolization pattern suggests another technique. |
| Repeat passes | Reassess mTICI, residual occlusion reachability, distal emboli, vasospasm/dissection after every pass. | Stop for mTICI 2b/2c/3 with no safe residual, repeated futile passes, perforation/SAH, or risk exceeding benefit. |

## Rescue Plan

- Perforation/extravasation/SAH: stop passes, stabilize, BP down per attending/anesthesia, reverse/normalize anticoagulation if relevant, consider balloon tamponade, emergent CT/neuro-ICU pathway.
- Dissection: maintain access, characterize flow limitation, consider stent/angioplasty or antithrombotic plan only after hemorrhage/thrombolytic risk review.
- Vasospasm: pause, pull back/relax catheter if needed, intra-arterial vasodilator per protocol, repeat angiography.
- Distal embolus/new territory: full-tree run, treat reachable disabling occlusion if safe, document final territory.
- ICAD/re-occlusion/tandem lesion: repeat angiography, consider angioplasty/stenting/antiplatelet strategy with explicit sICH/thrombolytic risk discussion.
- Access bleed: pressure/closure assessment, hemodynamics, CBC/coags, ultrasound/CTA and vascular help if uncontrolled.
- sICH/malignant edema: BP control, stop antithrombotics, STAT CT, reversal pathway, neuro-ICU/neurosurgery/hemicraniectomy watch.

## Postop Plan

- Destination/neuro checks: neuro-ICU or stroke unit; frequent NIHSS/neuro checks and immediate escalation for decline, headache, emesis, hypertension crisis, or access instability.
- BP framework: avoid hypotension pre-reperfusion; after mTICI 2b-3 use local tighter SBP target; after incomplete reperfusion consider more permissive collateral-support target unless hemorrhage/extravasation/medical indication.
- CT timing: noncontrast CT at protocol timing (commonly ~24 h after IV tPA/TNK and/or EVT before routine antithrombotics) and STAT CT for neurologic decline or extravasation concern.
- Antithrombotics: hold/start per thrombolytic exposure, CT result, stent/rescue therapy, hemorrhage risk, and stroke-team protocol.
- Checks/watch: access-site pulses/groin or radial band checks, glucose/temp/O2, hemorrhagic transformation, re-occlusion, and malignant edema/hemicraniectomy candidacy.

## Attending Questions / Preferences

- First-pass preference: aspiration-first, stent retriever, combined/Solumbra, BGC/BADDASS-style flow control?
- Femoral vs radial default and threshold for direct carotid rescue?
- Maximum passes before switching or stopping?
- Rescue ICAD/tandem stenting threshold and antiplatelet plan after IV tPA/TNK?
- Post-reperfusion BP target by mTICI result and hemorrhage risk?
"""


def _render_thrombectomy_evt_eligibility_frame(schema: dict[str, Any]) -> str:
    if not _is_thrombectomy(schema):
        return ""
    ctx = _thrombectomy_target_context(schema)
    facts = _case_facts(schema)
    return f"""## EVT Eligibility / Decision-Boundary Frame

Documented patient-specific facts are rendered with values; items marked **incomplete/need input** still require stroke-team confirmation. Do not invent values.

- {_fact_status_line(facts, "last_known_well", label="Last-known-well/time window")}; record LKW, onset witnessed vs unwitnessed/wake-up, arrival-to-puncture targets, and whether this is early vs late/unknown window.
- {_fact_status_line(facts, "nihss", label="NIHSS/disabling deficit")}; document NIHSS, cortical signs, dominant/nondominant syndrome, and whether a low-NIHSS LVO is nonetheless disabling.
- Baseline mRS/pre-stroke function: incomplete/needs input; high baseline disability, frailty, goals of care, or poor pre-stroke quality of life may shift toward medical management/no-EVT.
- IV tPA/TNK eligibility/status: incomplete/needs input; document eligibility, contraindications, bolus/dose time if given, and post-thrombolytic BP/antithrombotic restrictions.
- {_thrombectomy_imaging_selection_status(facts, str(ctx["target"]))}
- Early vs late window: early-window LVO decisions usually rely on disabling deficit plus favorable NCCT/CTA; late/unknown-window EVT requires explicit core-penumbra or tissue-window selection.
- Large core considerations: incomplete/needs input; selected large-core patients may benefit from EVT, but hemorrhage/edema risk, ASPECTS/core volume, age/frailty, and goals of care must be weighed.
- Low-NIHSS LVO controversy: incomplete/needs input; non-disabling low NIHSS may favor medical management/close monitoring, while disabling aphasia/neglect/hemiparesis or high-risk {ctx["target"]} may justify EVT discussion.
- Medical-management/no-EVT boundaries: no treatable LVO, hemorrhage/stroke mimic, very large completed infarct with unacceptable risk, non-disabling deficit, prohibitive baseline mRS/goals-of-care limits, inaccessible unsafe anatomy, or risk exceeding expected benefit.

"""


def _render_case_summary(schema: dict[str, Any]) -> str:
    case = schema["case"]
    snapshot = case["case_snapshot"]
    decision = case["indication_and_decision"]
    patient = case["patient_context"]
    parsed_summary = _render_structured_case_summary(schema)
    evt_frame = _render_thrombectomy_evt_eligibility_frame(schema)
    return f"""# Case Summary - {schema["topic"]}

{parsed_summary}

{evt_frame}## Snapshot

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


def _render_bound_images(schema: dict[str, Any]) -> str:
    """Render image-bank figures bound to the imaging section, grouped by spec."""
    section = schema.get("imaging_review")
    if not isinstance(section, dict):
        return ""
    bound = section.get("bound_images") or []
    if not bound:
        return ""

    by_spec: dict[str, list[dict[str, Any]]] = {}
    for img in bound:
        by_spec.setdefault(img.get("matched_spec", ""), []).append(img)

    lines: list[str] = ["", "### Prep Images From Image Bank", ""]
    for spec, imgs in by_spec.items():
        lines.append(f"**{spec}**")
        lines.append("")
        for img in imgs:
            caption = img.get("caption", "")
            path = img.get("local_path", "")
            pmcid = img.get("pmcid", "")
            link = (
                f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/"
                if pmcid else ""
            )
            lines.append(f"![{caption}]({path})")
            src = f" — source: [{pmcid}]({link})" if link else ""
            lines.append(f"*{caption}*{src}")
            lines.append("")
    return "\n".join(lines)


def _render_imaging(schema: dict[str, Any]) -> str:
    if _is_thrombectomy(schema):
        return _render_thrombectomy_imaging(schema)
    return f"""# Imaging Review - {schema["topic"]}

## Imaging Review Checklist

### Required Studies

{_list_block(_section_list(schema, "imaging_review", "required_studies"))}

### Key Findings

{_list_block(_section_list(schema, "imaging_review", "key_findings"))}

### Measurements

{_list_block(_section_list(schema, "imaging_review", "measurements"))}

### Anatomic Relationships

{_list_block(_section_list(schema, "imaging_review", "anatomic_relationships"))}

### Red Flags

{_list_block(_section_list(schema, "imaging_review", "red_flags"))}

### Images To Display In OR

{_list_block(_section_list(schema, "imaging_review", "images_to_display_in_or"))}
{_render_bound_images(schema)}"""


def _render_thrombectomy_imaging(schema: dict[str, Any]) -> str:
    ctx = _thrombectomy_target_context(schema)
    facts = _case_facts(schema)
    cta_boundary = _thrombectomy_cta_boundary_text(schema)
    return f"""# Imaging Review - {schema["topic"]}

## Thrombectomy Imaging Review

Patient-specific imaging values are **incomplete/need input** unless supplied below; do not infer ASPECTS, core volume, collaterals, thrombolytic status, or access anatomy from the procedure name alone.

{_render_thrombectomy_imaging_fact_status(schema)}

### Required Studies

{_list_block(_thrombectomy_required_studies(schema))}

### NCCT Hemorrhage Exclusion And ASPECTS

- Hemorrhage exclusion: incomplete/needs input; confirm no intracranial hemorrhage/SAH or stroke mimic before EVT and IV tPA/TNK decisions.
- {_fact_status_line(facts, "aspects", label="ASPECTS")}; document numeric score, involved regions, mass effect, and whether large-core considerations apply.
- Early ischemic change: incomplete/needs input; reconcile NCCT with CTP/MRI if the window is late/unknown or exam-imaging mismatch exists.

### CTA Occlusion Site And Collaterals

- Target to verify: {ctx["target"]} in the {ctx["circulation"]}; incomplete/needs input for exact CTA/DSA confirmation.
- Boundary check: distinguish {cta_boundary} before device plan.
- Collateral status: incomplete/needs input; grade pial/leptomeningeal/circle-of-Willis collateral filling and relate to core growth and hemorrhage risk.

### CTP / Core-Penumbra Selection

- Early window: CTP may not be required when NCCT/CTA and clinical deficit are sufficient, but core estimate and ASPECTS still need documentation.
- {_fact_status_line(facts, "perfusion_selection", label="Perfusion selection")}; record core volume, hypoperfusion/penumbra volume, mismatch ratio, and whether selection is trial-aligned if late/unknown-window or mismatch-based.
- Large core: incomplete/needs input; selected large-core patients may still be EVT candidates, but benefit-risk, hemorrhage/edema risk, and goals-of-care require explicit attending/stroke-team decision.

### Access Anatomy / Etiology Clues

{_list_block(_thrombectomy_imaging_key_findings(schema))}

### Measurements

{_list_block(_thrombectomy_imaging_measurements(schema))}

### Anatomic Relationships

{_list_block(_section_list(schema, "imaging_review", "anatomic_relationships"))}

### Red Flags / No-EVT Boundaries From Imaging

{_list_block(_section_list(schema, "imaging_review", "red_flags"))}

### Images To Display In Angio Suite

{_list_block(_section_list(schema, "imaging_review", "images_to_display_in_or"))}
{_render_bound_images(schema)}"""


def _generated_section(title: str, generated_body: str | None) -> str:
    if not generated_body:
        return ""
    return f"\n## Evidence-Derived Notes\n\n{generated_body.strip()}\n"


def _generated_section_thrombectomy(generated_body: str | None) -> str:
    if not generated_body:
        return ""
    return (
        "\n## Evidence-Derived Notes / Lower-Applicability Provenance Appendix\n\n"
        "The structured clinical plan above is the case-prep bottom line. The excerpts below preserve provenance from retrieval/synthesis and may include lower-applicability or repeated evidence; verify before using them to override the plan.\n\n"
        f"{generated_body.strip()}\n"
    )


def _render_anatomy(schema: dict[str, Any], generated_body: str | None = None) -> str:
    return f"""# Anatomy At Risk - {schema["topic"]}

## Anatomy At Risk

### Surgical Corridor

{_list_block(_section_list(schema, "anatomy_at_risk", "surgical_corridor"))}

### Landmarks In Order

{_list_block(_section_list(schema, "anatomy_at_risk", "landmarks_in_order"))}

### Neural Structures

{_list_block(_section_list(schema, "anatomy_at_risk", "neural_structures"))}

### Arteries / Perforators / Veins / Sinuses

{_list_block(_section_list(schema, "anatomy_at_risk", "arteries_perforators_veins_sinuses"))}

### Functional Structures

{_list_block(_section_list(schema, "anatomy_at_risk", "functional_structures"))}

### Variants

{_list_block(_section_list(schema, "anatomy_at_risk", "variants"))}

### No-Fly Zones

{_list_block(_section_list(schema, "anatomy_at_risk", "no_fly_zones"))}
{_generated_section_thrombectomy(generated_body) if _is_thrombectomy(schema) else _generated_section("Evidence-Derived Notes", generated_body)}"""


def _parasagittal_sss_craniotomy_strategy(ctx: dict[str, str]) -> str:
    return f"""## Parasagittal / SSS Craniotomy Strategy

### Imaging-Gated Plan

| MRV/CTV finding | Craniotomy / dural-opening implication | Resection endpoint |
|---|---|---|
| patent/compressed SSS; sinus wall invasion remains unproven | Plan exposure to show tumor margins and the safe sinus edge; place parasagittal/medial-side burr holes safely lateral to the SSS margin unless the attending explicitly plans a crossing/straddling exposure. | Treat the sinus interface as a preservation boundary; peel/coagulate only where the plane is safe and leave planned residual if sinus wall or dominant veins are endangered. |
| Narrowed or possibly invaded but still flowing SSS | Keep bone work deliberately controlled over the parasagittal edge; avoid blind medial rongeuring and prepare for venous bleeding before opening dura near the sinus. | Debulk first, define the arachnoid/tumor capsule plane, and decide sinus-wall work only after flow, wall adherence, and collateral drainage are understood. |
| Occluded SSS segment with proven collateral outflow | Consider wider midline exposure only if imaging and attending plan confirm the occluded segment and collateral venous drainage. | Sinus resection/reconstruction is not assumed from the topic string; proceed only under a specific attending plan. |
| Dominant bridging veins or venous lacunae near the tumor | Tailor flap/dural opening around the vein entry points; leave a venous corridor rather than forcing a symmetric exposure. | Preserve the vein/lacuna first; accept residual at the vein/sinus interface when mobilization risks venous infarct. |

### Incision / Bone Work / Dura

- Incision and flap: center the flap on the {ctx['lesion']} with navigation-confirmed midline, tumor margins, SSS course, and bridging-vein entry points; exact AP extent depends on imaging rather than a fixed template.
- Burr holes: start safely lateral to the SSS margin and tumor edge; use image guidance and/or preplanned landmarks before any parasagittal/medial-side burr hole, crossing flap, or sinus-adjacent rongeuring.
- Bone flap: expose enough lateral working room for debulking and extracapsular dissection before the sinus side is manipulated; avoid tearing venous lacunae during flap elevation.
- Dural opening: favor a lateral-to-medial opening based away from the SSS, preserve mapped venous entry points, and leave a medial dural cuff near the sinus/venous lacunae for control and closure; reflect the flap in the safest direction for veins/sinus per imaging.
- Sequence: devascularize safe dural base, internally debulk, collapse tumor away from cortex/veins, then address the sinus/falx interface last with planned residual as the default bailout if venous risk rises.
"""


def _meningioma_approach_matrix() -> str:
    return """## Approach Selection Matrix

| Option | Best Fit | Main Advantage | Main Concern / Stop Point |
|---|---|---|---|
| Parasagittal craniotomy with venous-preservation endpoint | Patent or uncertain SSS, abutting/compressed sinus, dominant bridging/cortical veins | Provides working room for decompression while treating SSS/veins as preservation boundaries | Stop or leave residual for unsafe sinus wall plane, dominant vein compromise, venous congestion, or uncontrolled venous bleeding |
| Wider midline/straddling exposure | Bilateral/falcine extension or need to expose both sides of the sinus under attending plan | Improves visualization of midline/falx/sinus relationships | Higher sinus/lacuna/bridging-vein exposure risk; not default for simple abutment |
| Planned subtotal resection plus surveillance/adjuvant radiation strategy | Tumor densely adherent to patent SSS or critical bridging vein | Avoids venous infarct from marginal radicality | Requires explicit residual documentation, postop imaging, pathology-based follow-up, and adjuvant threshold |
"""


def _render_operative_plan(
    schema: dict[str, Any],
    generated_body: str | None = None,
) -> str:
    if _is_thrombectomy(schema):
        return _render_thrombectomy_operative_plan(schema, generated_body)
    strategy_section = ""
    if _is_convexity_meningioma(schema):
        ctx = _meningioma_context(schema)
        selected_approach = (
            f"- Likely approach: {ctx['corridor']} planned around SSS/bridging-vein preservation; "
            "exact positioning/incision depends on AP location and venous imaging.\n"
            "- Rationale: expose tumor and safe sinus edge while preserving cortical/bridging venous drainage; "
            "leave sinus-adherent residual if complete resection risks SSS or a dominant vein.\n"
            "- Must verify before incision: AP location, edema, sinus patency/narrowing, suspected wall invasion, dominant bridging veins, falx/bone involvement, and booked attending plan."
        )
        approach_matrix = _meningioma_approach_matrix()
        if _is_parasagittal_sss_meningioma(schema):
            strategy_section = "\n" + _parasagittal_sss_craniotomy_strategy(ctx)
    else:
        selected_approach = "- Approach: `needs input`\n- Rationale: `needs input`\n- Verification: `needs clinician verification`"
        approach_matrix = """## Approach Selection Matrix

| Option | Advantages | Disadvantages | Best Fit | Concern |
|---|---|---|---|---|
| Primary plan | `needs input` | `needs input` | `needs input` | `needs input` |
| Alternative | `needs input` | `needs input` | `needs input` | `needs input` |"""
    return f"""# Operative Plan - {schema["topic"]}

## Selected Approach

{selected_approach}
{strategy_section}
{approach_matrix}

## Setup

- Positioning: {_section_scalar(schema, "operative_plan", "positioning")}

### Monitoring

{_list_block(_section_list(schema, "operative_plan", "monitoring"))}

### Equipment / Adjuncts

{_list_block(_section_list(schema, "operative_plan", "equipment_adjuncts"))}

## Critical Steps

{_list_block(_section_list(schema, "operative_plan", "critical_steps"))}

## Intraoperative Decision Points

{_list_block(_section_list(schema, "operative_plan", "decision_points"))}

## Bailout / Stop Points

{_list_block(_section_list(schema, "operative_plan", "stop_points"))}
{_generated_section_thrombectomy(generated_body) if _is_thrombectomy(schema) else _generated_section("Evidence-Derived Notes", generated_body)}"""


def _render_thrombectomy_decision_tables(schema: dict[str, Any]) -> str:
    ctx = _thrombectomy_target_context(schema)
    return f"""## Structured Thrombectomy Decision Tables

### Eligibility / Go-No-Go

| Domain | Favor EVT / proceed | Reconsider, pause, or no-go |
|---|---|---|
| Clinical deficit | Disabling deficit attributable to {ctx['target']}; NIHSS and syndrome documented. | Non-disabling deficit, stroke mimic, unclear target-symptom match, or goals-of-care limit. |
| Time window | LKW/onset supports early-window EVT or late/unknown-window tissue selection. | LKW/selection absent, excessive delay without favorable tissue profile, or benefit no longer justifies risk. |
| NCCT / core | No hemorrhage; ASPECTS/core acceptable by protocol and attending/stroke-team judgment. | Hemorrhage/SAH, very large completed infarct with unacceptable edema/sICH risk, or mass effect. |
| CTA target | Treatable LVO confirmed with reachable anatomy and salvageable territory. | No LVO, inaccessible unsafe anatomy, distal nondisabling residual only, or alternate diagnosis. |
| Thrombolytic / meds | IV tPA/TNK status, anticoagulation/coags, and antithrombotic constraints known. | Unknown coagulopathy/DOAC timing or rescue-stent antiplatelet risk unacceptable. |

### Access Selection

| Option | Use when | Watch-outs / switch trigger |
|---|---|---|
| Transfemoral | Fastest stable route with acceptable iliofemoral/arch/cervical anatomy. | Hostile arch, severe tortuosity/stenosis, failed guide support, access bleeding. |
| Transradial / brachial | Hostile femoral/arch anatomy or operator expects faster safer access. | Radial/subclavian loops, small vessel, support limitations, conversion delay. |
| Direct carotid | Rare rescue when standard access fails and benefit still justifies risk. | Neck hematoma, airway risk, carotid injury; attending-level decision only. |

### First-Pass Technique

| Technique | Best fit | Reasons to switch |
|---|---|---|
| Aspiration-first / ADAPT | Straight access to clot face, favorable catheter purchase, soft/accessible clot. | Cannot reach clot face, poor ingestion, embolization, no reperfusion. |
| Stent retriever | Firm/embedded clot, branch incorporation, poor aspiration purchase, need scaffold. | Unsafe distal landing zone, excessive traction, no reperfusion after pass. |
| Combined / Solumbra / BGC-assisted | {_thrombectomy_combined_strategy_fit(schema)} | Support instability, vasospasm/dissection, repeated futile passes, hemorrhage concern. |

### Stop / Switch / Rescue

| Situation | Action |
|---|---|
| mTICI 2b/2c/3 with no safe treatable residual | Stop thrombectomy, final runs, document distal/new-territory emboli and complications. |
| Failed first pass | Diagnose mechanism: access/support, clot consistency, ICAD/tandem lesion, distal embolus; switch technique accordingly. |
| Repeated futile passes | Limit additional passes; reassess core/time/risk and attending threshold. |
| Perforation/SAH/extravasation | Stop passes, BP down, reversal/balloon tamponade/CT pathway. |
| ICAD/re-occlusion/tandem lesion | Consider angioplasty/stenting/antiplatelet rescue only after sICH/thrombolytic risk review. |

### Post-Reperfusion Management

| Issue | Framework |
|---|---|
| BP | Avoid hypotension pre-reperfusion; tailor post-EVT SBP to mTICI result, hemorrhage/extravasation, thrombolytic status, and protocol. |
| CT timing | STAT CT for decline/extravasation concern; protocol NCCT often ~24 h and before routine antithrombotics after IV tPA/TNK. |
| Antithrombotics | Constrain by IV tPA/TNK, hemorrhage exclusion, stent/rescue therapy, and stroke-team protocol. |
| Monitoring | Neuro checks/NIHSS, access-site checks, glucose/temp/O2, re-occlusion, sICH, malignant edema/hemicraniectomy watch. |
"""


def _render_thrombectomy_operative_plan(
    schema: dict[str, Any],
    generated_body: str | None = None,
) -> str:
    return f"""# Operative Plan - {schema["topic"]}

## Endovascular Thrombectomy Strategy

- Target lesion: {_thrombectomy_target_context(schema)["target"]}; verify CTA/angiography clot extent, tandem disease, distal emboli, and access anatomy before device selection.
- Reperfusion goal: successful reperfusion, ideally mTICI 2b/2c/3, with final angiographic runs documenting target territory, distal/new-territory emboli, and no extravasation.
- Verification: `needs clinician verification` for patient-specific times, imaging selection, anesthesia/BP plan, and device sequence.

{_markdown_sections(_render_thrombectomy_decision_tables(schema), _render_thrombectomy_supplied_technique(schema))}## Access And Setup

- Access choice: femoral vs radial access based on pulse exam, arch anatomy, cervical carotid tortuosity/stenosis, anticoagulation/thrombolytic status, and fastest stable support.
- Positioning / suite setup: {_section_scalar(schema, "operative_plan", "positioning")}

### Monitoring

{_list_block(_section_list(schema, "operative_plan", "monitoring"))}

### Equipment / Adjuncts

{_list_block(_section_list(schema, "operative_plan", "equipment_adjuncts"))}

## Workflow / Critical Steps

{_list_block(_section_list(schema, "operative_plan", "critical_steps"))}

## Technique Selection And Pass Strategy

{_list_block(_section_list(schema, "operative_plan", "decision_points"))}

## Bailout / Stop Points

{_list_block(_section_list(schema, "operative_plan", "stop_points"))}
{_generated_section_thrombectomy(generated_body) if _is_thrombectomy(schema) else _generated_section("Evidence-Derived Notes", generated_body)}"""


def _render_risk(schema: dict[str, Any], generated_body: str | None = None) -> str:
    if _is_thrombectomy(schema):
        return _render_thrombectomy_risk(schema, generated_body)
    return f"""# Risk And Rescue - {schema["topic"]}

## Likely Complications

{_list_block(_section_list(schema, "risk_and_rescue", "likely_complications"))}

## Catastrophic Complications

{_list_block(_section_list(schema, "risk_and_rescue", "catastrophic_complications"))}

## Mitigation

{_list_block(_section_list(schema, "risk_and_rescue", "mitigation"))}

## Rescue Triggers

{_list_block(_section_list(schema, "risk_and_rescue", "rescue_triggers"))}

## General Clinical Decline Triggers

| Finding | Immediate Action | Notify | Likely Tests / Imaging |
|---|---|---|---|
| New focal deficit | ABCs, focused neuro exam, urgent surgeon notification | Neurosurgery attending / chief | CT/CTA as clinically appropriate |
| Declining mental status | ABCs, glucose, medication review, urgent evaluation | Neurosurgery and anesthesia/ICU | CT head and labs as clinically appropriate |
{_generated_section_thrombectomy(generated_body) if _is_thrombectomy(schema) else _generated_section("Evidence-Derived Notes", generated_body)}"""


def _render_thrombectomy_risk(schema: dict[str, Any], generated_body: str | None = None) -> str:
    return f"""# Risk And Rescue - {schema["topic"]}

## Thrombectomy-Specific Likely Complications

{_list_block(_section_list(schema, "risk_and_rescue", "likely_complications"))}

## Catastrophic Complications

{_list_block(_section_list(schema, "risk_and_rescue", "catastrophic_complications"))}

## Mitigation

{_list_block(_section_list(schema, "risk_and_rescue", "mitigation"))}

## Rescue Playbook

{_list_block(_section_list(schema, "risk_and_rescue", "rescue_triggers"))}

## Rescue Trigger Table

| Finding | Immediate Action | Notify | Likely Tests / Imaging |
|---|---|---|---|
| Perforation / SAH / extravasation | Stop passes, stabilize wire/catheter position, lower BP per attending, consider reversal/balloon tamponade | Neurointerventional attending, anesthesia, neuro-ICU/neurosurgery | Control angiography, emergent CT head |
| Dissection or flow-limiting stenosis | Maintain access, define lesion, consider angioplasty/stenting or antithrombotic plan | Neurointerventional attending, stroke team | Angiographic runs, CTA if needed |
| Vasospasm | Pause manipulation, intra-arterial vasodilator per protocol, reassess caliber/flow | Attending/anesthesia | Repeat angiography |
| Embolus to new territory or distal emboli | Full-tree angiographic review, treat reachable disabling occlusion when safe | Attending/stroke team | Final DSA runs, postprocedure CT/CTA if decline |
| Failed recanalization / re-occlusion | Reassess clot, tandem lesion, underlying stenosis; consider rescue angioplasty/stenting or stop | Attending/stroke team/family as appropriate | Repeat DSA, CT/CTA/CTP if clinical change |
| Access-site hemorrhage | Manual pressure/closure assessment, hemodynamics, labs/transfusion if needed | Anesthesia, vascular surgery/IR if uncontrolled | Groin/wrist ultrasound or CTA abdomen/pelvis as indicated |
| Symptomatic ICH or malignant edema | BP control, reverse coagulopathy when indicated, hyperosmolar/airway pathway, hemicraniectomy watch | Neurosurgery, neuro-ICU, stroke team | STAT CT head ± CTA |
{_generated_section_thrombectomy(generated_body) if _is_thrombectomy(schema) else _generated_section("Evidence-Derived Notes", generated_body)}"""


def _render_postop(schema: dict[str, Any]) -> str:
    return f"""# Postop Plan - {schema["topic"]}

## Immediate Postop Orders

- Destination: {_section_scalar(schema, "postop_plan", "destination")}
- Neuro checks: {_section_scalar(schema, "postop_plan", "neuro_checks")}
- BP goals: {_section_scalar(schema, "postop_plan", "bp_goals")}
- Imaging timing: {_section_scalar(schema, "postop_plan", "imaging_timing")}
- DVT prophylaxis: {_section_scalar(schema, "postop_plan", "dvt_prophylaxis")}

## Medications

{_list_block(_section_list(schema, "postop_plan", "medications"))}

## Drains / Devices

{_list_block(_section_list(schema, "postop_plan", "drains_devices"))}

## Labs / Monitoring

{_list_block(_section_list(schema, "postop_plan", "labs_monitoring"))}

## Discharge Criteria

{_list_block(_section_list(schema, "postop_plan", "discharge_criteria"))}
"""


def _thrombectomy_source_applicability_notes(schema: dict[str, Any]) -> list[str]:
    evidence = schema["case"]["evidence"]
    notes: list[str] = []
    for source in evidence.get("key_sources", []):
        title = str(source.get("title", ""))
        title_cf = title.casefold()
        flags: list[str] = []
        if "m2" in title_cf and "m1" not in title_cf:
            flags.append("M2-only or distal-MCA focus")
        if any(term in title_cf for term in ("artificial intelligence", "deep learning", "machine learning", "ai ")):
            flags.append("AI detection/imaging-workflow focus")
        if any(term in title_cf for term in ("case report", "twig-like", "anomaly", "rare", "vignette", "history", "historical")):
            flags.append("rare-anomaly/case-report/historical focus")
        if flags:
            notes.append(f"{source.get('id', 'source')}: lower applicability to routine anterior-circulation M1 EVT bottom line ({'; '.join(flags)}): {title}")
    return notes


def _md_cell(value: Any) -> str:
    return str(value or "").replace("|", "\\|").strip()


_RETRIEVAL_SOURCE_LABELS = {
    "pubmed": "PubMed",
    "corpus_fts5": "corpus (FTS5)",
    "corpus_semantic": "corpus (semantic)",
    "radiology": "Open-i",
}


def _retrieval_source_label(tag: Any) -> str:
    if not tag:
        return ""
    return _RETRIEVAL_SOURCE_LABELS.get(str(tag), str(tag))


def _source_ref(source: dict[str, Any]) -> str:
    refs: list[str] = []
    if source.get("pmid"):
        refs.append(f"PMID {source.get('pmid')}")
    if source.get("doi"):
        refs.append(f"DOI {source.get('doi')}")
    base = "; ".join(refs) or str(source.get("id", ""))
    retrieval_tag = _retrieval_source_label(source.get("retrieval_source"))
    also = source.get("also_retrieved_by") or []
    if isinstance(also, list) and also:
        retrieval_tag = (
            f"{retrieval_tag} + " + " + ".join(
                _retrieval_source_label(tag) for tag in also if tag
            )
            if retrieval_tag
            else " + ".join(_retrieval_source_label(tag) for tag in also if tag)
        )
    if retrieval_tag:
        cosine = source.get("semantic_cluster_cosine")
        if cosine is not None and "semantic" in retrieval_tag:
            retrieval_tag = f"{retrieval_tag} cos={cosine}"
        return f"{base} — via {retrieval_tag}" if base else f"via {retrieval_tag}"
    return base


def _evidence_source_row(source: dict[str, Any]) -> str:
    applicability = (
        source.get("quarantine_reason")
        if source.get("clinical_include") is False and source.get("quarantine_reason")
        else source.get("applicability") or source.get("relevance") or source.get("quarantine_reason")
    )
    return "| {title} | {ref} | {tier} | {applicability} | {verification} |".format(
        title=_md_cell(source.get("title") or source.get("pack_item_id") or source.get("id")),
        ref=_md_cell(_source_ref(source)),
        tier=_md_cell(source.get("source_tier") or source.get("tier") or source.get("evidence_level")),
        applicability=_md_cell(applicability),
        verification=_md_cell(source.get("verification") or "cited"),
    )


def _evidence_table(sources: list[dict[str, Any]], empty: str = "No retrieved sources in this category.") -> str:
    if not sources:
        return f"- {empty}"
    rows = ["| Title | PMID/DOI | Tier | Applicability | Verification |", "|---|---|---|---|---|"]
    rows.extend(_evidence_source_row(source) for source in sources)
    return "\n".join(rows)


def _source_category(source: dict[str, Any]) -> str:
    tier = str(source.get("source_tier") or source.get("tier") or source.get("evidence_level") or "").casefold()
    role = str(source.get("evidence_role") or source.get("relevance") or "").casefold()
    title = str(source.get("title") or "").casefold()
    text = " ".join((tier, role, title))
    if source.get("clinical_include") is False:
        return "quarantined"
    if "guideline" in text or "consensus" in text:
        return "guideline"
    if "late-window" in text or "late window" in text or "dawn" in title or "defuse" in title:
        return "late"
    if "large-core" in text or "large core" in text or any(term in title for term in ("select2", "angel", "rescue-japan", "tension", "laste", "large ischemic", "large infarct")):
        return "large_core"
    if any(term in text for term in ("practice-changing", "pooled", "meta-analysis", "early-window", "landmark")):
        return "practice"
    if any(term in text for term in ("technique", "device", "stent", "aspiration", "balloon guide", "access")):
        return "technique"
    return "technique"


def _coverage_items(evidence_pack: dict[str, Any] | None, *keys: str) -> list[dict[str, Any]]:
    if not isinstance(evidence_pack, dict):
        return []
    items: list[dict[str, Any]] = []
    for key in keys:
        value = evidence_pack.get(key, [])
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    normalized = dict(item)
                    normalized.setdefault("verification", key.rstrip("s") or key)
                    items.append(normalized)
    return items


def _render_thrombectomy_evidence(schema: dict[str, Any], literature_summary: str | None = None) -> str:
    evidence = schema["case"]["evidence"]
    ctx = _thrombectomy_target_context(schema)
    target = str(ctx["target"])
    target_label = target if bool(ctx["known"]) else "the target LVO"
    mca_evidence_phrase = (
        f"For a disabling anterior-circulation large-vessel occlusion such as {target_label}, EVT is standard-of-care when imaging/time-window criteria and goals of care support treatment. The strongest routine-M1 foundation is the early-window anterior-circulation LVO randomized-trial bundle plus pooled HERMES patient-level meta-analysis"
        if bool(ctx["is_mca"])
        else f"For a disabling treatable large-vessel occlusion such as {target_label}, EVT candidacy depends on confirmed occlusion territory, imaging/time-window criteria, and goals of care. Landmark anterior-circulation LVO trials remain targets to verify when the target is anterior circulation; posterior/unspecified targets require territory-specific evidence and guidelines"
    )
    routine_focus = "routine M1 EVT conclusions" if bool(ctx["is_mca"]) else "routine EVT conclusions for this target"
    applicability_text = (
        f"{target_label.capitalize()} applicability depends on confirmed disabling deficit, ASPECTS/core-penumbra, time from last-known-well, premorbid status, thrombolytic status, tandem/ICAD anatomy, and hemorrhage risk; no patient-specific values should be inferred from the topic string."
    )
    sources = [source for source in evidence.get("key_sources", []) if isinstance(source, dict)]
    quarantined_sources = [source for source in sources if source.get("clinical_include") is False]
    explicit_quarantined = evidence.get("quarantined_sources", [])
    if isinstance(explicit_quarantined, list):
        for source in explicit_quarantined:
            if isinstance(source, dict) and not any(existing.get("id") == source.get("id") for existing in quarantined_sources):
                quarantined_sources.append(source)
    included_sources = [source for source in sources if source.get("clinical_include") is not False]
    categories = {
        "practice": [],
        "guideline": [],
        "late": [],
        "large_core": [],
        "technique": [],
    }
    for source in included_sources:
        categories.setdefault(_source_category(source), categories["technique"]).append(source)
    evidence_pack = evidence.get("evidence_pack") if isinstance(evidence.get("evidence_pack"), dict) else None
    coverage_rows = _coverage_items(evidence_pack, "retrieved", "missing", "partial")
    missing_rows = _coverage_items(evidence_pack, "missing", "partial")
    lower_applicability_notes = _thrombectomy_source_applicability_notes(schema)
    guardrail_block = _list_block(lower_applicability_notes or [
        f"Screen retrieved sources for M2-only, AI-detection, rare-anomaly case-report, and historical-vignette focus; these should not dominate {routine_focus}."
    ])
    appendix = f"\n## Search Appendix\n\n{literature_summary.strip()}\n" if literature_summary else ""
    return f"""# Evidence - {schema["topic"]}

## Clinical Questions

{_list_block(evidence.get("clinical_questions", []))}

## Thrombectomy Evidence Bottom Line

{mca_evidence_phrase}; late-window selection is supported by DAWN and DEFUSE 3 when mismatch/core criteria apply. Large-core trials support benefit in selected large-core patients but do not automatically apply without ASPECTS/core volume, time, premorbid status, hemorrhage risk, and local stroke-team judgment. Verify current AHA/ASA or ESO/ESMINT guideline recommendations and institutional protocol before applying numeric thresholds.

## Landmark Evidence Coverage

Landmark/guideline targets to verify: MR CLEAN, ESCAPE, EXTEND-IA, SWIFT PRIME, REVASCAT; HERMES collaboration/meta-analysis; DAWN; DEFUSE 3; SELECT2, ANGEL-ASPECT, RESCUE-Japan LIMIT, TENSION/LASTE; AHA/ASA or ESO/ESMINT guideline category.

{_evidence_table(coverage_rows, "No evidence pack coverage was attached to this run.")}

## Practice-Changing EVT Evidence

{_evidence_table(categories["practice"])}

## Guidelines / Consensus

{_evidence_table(categories["guideline"])}

## Late-Window Evidence

{_evidence_table(categories["late"])}

## Large-Core Conditional Evidence

{_evidence_table(categories["large_core"])}

## Technique and Device Evidence

{_evidence_table(categories["technique"])}

## Quarantined / Lower-Applicability Sources

{_evidence_table(quarantined_sources, "No sources were quarantined in this run.")}

## Missing or Partial Evidence

{_evidence_table(missing_rows, "No missing evidence-pack items were recorded.")}

## Applicability Guardrails For Retrieved Sources

{guardrail_block}

## Applicability To This Case

{evidence.get("applicability_to_this_case") or applicability_text}

## Uncertainty / Evidence Gaps

{_list_block(evidence.get("uncertainty_gaps", []) or [
    "Exact PMIDs/DOIs for landmark trials/guidelines must be verified unless already present in retrieved evidence; do not fake citations.",
    "Patient-specific time window, NIHSS/disabling deficit, ASPECTS/core volume, collaterals, and thrombolytic status remain required for applicability.",
])}
{appendix}"""


def _parasagittal_sss_evidence_sources() -> dict[str, list[dict[str, Any]]]:
    """Deterministic source pack for parasagittal/SSS meningioma prep.

    This is intentionally concise and operative: it anchors the renderer to
    relevant parasagittal/SSS literature without pretending the topic string proves
    sinus invasion or patient-specific applicability.
    """
    return {
        "SSS / Parasagittal Surgical Outcomes": [
            {
                "id": "pmid-30171502",
                "title": "Optimal surgical strategy for meningiomas involving the superior sagittal sinus: a systematic review",
                "year": "2020",
                "pmid": "30171502",
                "doi": "10.1007/s10143-018-1026-1",
                "evidence_level": "Systematic review",
                "relevance": "Frames surgical strategy for SSS-involving meningiomas and the tradeoff between radicality and venous morbidity.",
                "verification": "curated PubMed pack",
            },
            {
                "id": "pmid-16607555",
                "title": "Meningiomas infiltrating the superior sagittal sinus: surgical considerations of 328 cases",
                "year": "2006",
                "pmid": "16607555",
                "evidence_level": "Large surgical series",
                "relevance": "Large experience focused on SSS-infiltrating meningiomas; use for operative considerations, not to overcall invasion in this case.",
                "verification": "curated PubMed pack",
            },
            {
                "id": "pmid-20950085",
                "title": "Results with judicious modern neurosurgical management of parasagittal and falcine meningiomas",
                "year": "2011",
                "pmid": "20950085",
                "doi": "10.3171/2010.9.JNS10646",
                "evidence_level": "Clinical surgical series",
                "relevance": "Supports a judicious management frame for parasagittal/falcine tumors rather than maximal sinus-risk resection by default.",
                "verification": "curated PubMed pack",
            },
        ],
        "Venous Complications / Bridging Veins": [
            {
                "id": "pmid-23330997",
                "title": "Venous preservation-guided resection: a changing paradigm in parasagittal meningioma surgery",
                "year": "2013",
                "pmid": "23330997",
                "doi": "10.3171/2012.11.JNS112011",
                "evidence_level": "Operative strategy article",
                "relevance": "Directly supports prioritizing venous preservation, bridging/cortical vein anatomy, and safe resection limits.",
                "verification": "curated PubMed pack",
            },
            {
                "id": "pmid-33618045",
                "title": "Classification of Peritumoral Veins in Convexity and Parasagittal Meningiomas and Its Significance in Preventing Cerebral Venous Infarction",
                "year": "2021",
                "pmid": "33618045",
                "doi": "10.1016/j.wneu.2021.02.041",
                "evidence_level": "Clinical classification / cohort",
                "relevance": "Links peritumoral venous patterns to venous infarction prevention; useful for MRV/CTV and vein-preservation review.",
                "verification": "curated PubMed pack",
            },
            {
                "id": "pmid-40025371",
                "title": "Complications after resection of parasagittal and superior sagittal sinus meningiomas",
                "year": "2025",
                "pmid": "40025371",
                "doi": "10.1007/s10143-025-03430-3",
                "evidence_level": "Complications series",
                "relevance": "Recent source focused on complications after parasagittal/SSS meningioma resection.",
                "verification": "curated PubMed pack",
            },
        ],
        "Residual / Adjuvant Radiation": [
            {
                "id": "pmid-9733295",
                "title": "Judicious resection and/or radiosurgery for parasagittal meningiomas: outcomes from a multicenter review",
                "year": "1998",
                "pmid": "9733295",
                "evidence_level": "Multicenter review",
                "relevance": "Supports considering planned residual and radiosurgery when sinus/venous risk makes aggressive resection unsafe.",
                "verification": "curated PubMed pack",
            },
            {
                "id": "pmid-37496660",
                "title": "Meningioma involving the superior sagittal sinus: long-term outcome after robotic radiosurgery in primary and recurrent situation",
                "year": "2023",
                "pmid": "37496660",
                "doi": "10.3389/fonc.2023.1206059",
                "evidence_level": "Radiosurgery cohort",
                "relevance": "Adjuvant/salvage radiosurgery option for SSS-involving or recurrent residual disease; not a reason to ignore safe surgical decompression goals.",
                "verification": "curated PubMed pack",
            },
        ],
        "Recurrence / Extent Of Resection": [
            {
                "id": "pmid-37987849",
                "title": "Predictors of recurrence after surgical resection of parafalcine and parasagittal meningiomas",
                "year": "2023",
                "pmid": "37987849",
                "doi": "10.1007/s00701-023-05848-4",
                "evidence_level": "Recurrence predictors cohort",
                "relevance": "Relevant to counseling and follow-up around extent of resection, residual tumor, and recurrence risk.",
                "verification": "curated PubMed pack",
            },
            {
                "id": "pmid-33544790",
                "title": "Tumor recurrence in parasagittal and falcine atypical meningiomas invading the superior sagittal sinus",
                "year": "2020",
                "pmid": "33544790",
                "doi": "10.47162/RJME.61.2.08",
                "evidence_level": "Pathology-specific recurrence series",
                "relevance": "Useful for atypical/invasive recurrence framing; do not apply unless grade/invasion is confirmed.",
                "verification": "curated PubMed pack",
            },
        ],
    }


def _parasagittal_sss_evidence_source_count(sources_by_bucket: dict[str, list[dict[str, Any]]]) -> int:
    return sum(len(sources) for sources in sources_by_bucket.values())


def _parasagittal_sss_study_takeaways() -> list[str]:
    return [
        "Giordan et al. systematic review: 26 studies / 1614 patients; most tumors were middle-third SSS and 75% had a patent sinus at surgery; aggressive versus non-aggressive strategies had similar favorable outcome proportions, but aggressive management had higher venous infarct 4% vs 2% and worsening preexisting motor deficits 34% vs 13%.",
        "Tomasello et al. venous-preservation series: 67 SSS-involving parasagittal meningiomas, mean 80-month follow-up; recurrence 10.4%, morbidity 10.4%, mortality 4.5%; authors found no evidence that aggressive SSS management improves recurrence enough to justify venous risk.",
        "Cai et al. peritumoral-vein cohort: 57 convexity/parasagittal meningiomas; MRV/intraop venous patterns were type A 57.9%, type B 26.3%, type C 15.8%; 6 vein injuries caused serious complications including 1 death after central-vein injury, supporting preop venous mapping.",
        "Peto et al. complications series: 62 parasagittal/SSS cases; postoperative intraparenchymal hemorrhage occurred after 8 surgeries (12.90%), procedure-related mortality was 3.2%, long-term headaches 22.58%, and CSF diversion 6.56%; prior surgery and higher WHO grade were independent ICH risk factors.",
        "Khanna et al. recurrence cohort: Recurrence occurred in 37/110 patients (33.6%) at median 42-month follow-up; high-grade histology and complete sinus invasion were independent recurrence predictors; subtotal resection independently shortened time to recurrence (HR 3.10).",
        "Kondziolka et al. multicenter radiosurgery review: 203 benign parasagittal meningioma patients; primary radiosurgery 5-year actuarial tumor control rate was 93 ± 4%, prior-surgery patients had lower 5-year control 60 ± 10%, and transient symptomatic edema after radiosurgery was 16%.",
    ]


def _parasagittal_sss_evidence_provenance(
    sources_by_bucket: dict[str, list[dict[str, Any]]],
    literature_summary: str | None,
) -> list[str]:
    notes = [
        f"Curated parasagittal/SSS evidence-pack sources: {_parasagittal_sss_evidence_source_count(sources_by_bucket)} PubMed-indexed sources across 4 operative buckets.",
        "Live retrieval source counts are separate from curated evidence-pack coverage; a narrow live search may retrieve fewer abstracts and should not be read as the pack source count.",
    ]
    if literature_summary:
        notes.append(
            "The raw live-search appendix is intentionally not reprinted here to avoid implying that a live retrieval count replaces the curated pack; use the bucket tables and study-level takeaways as the rendered evidence surface."
        )
    return notes


def _render_parasagittal_sss_evidence(schema: dict[str, Any], literature_summary: str | None = None) -> str:
    evidence = schema["case"]["evidence"]
    ctx = _meningioma_context(schema)
    sources_by_bucket = _parasagittal_sss_evidence_sources()
    bottom_line = evidence.get("bottom_line") or (
        f"For {ctx['diagnosis']}, the evidence supports a venous-preservation strategy rather than reflexively chasing maximal sinus-interface resection. "
        "Because the case input says abutting SSS and sinus invasion is unknown, confirm MRV/CTV sinus patency, wall invasion versus compression, venous lacunae, and dominant bridging/cortical veins before setting the extent-of-resection endpoint. "
        "Default bias: achieve safe extracapsular/devascularizing resection where the plane is safe, but leave planned residual and consider adjuvant radiosurgery/fractionated radiation when a patent sinus wall or critical vein would be endangered; recurrence/EOR evidence should guide follow-up and counseling after pathology and residual status are known."
    )
    clinical_questions = evidence.get("clinical_questions") or [
        "Is the superior sagittal sinus patent on MRV/CTV, narrowed/compressed, invaded, or occluded?",
        "Are dominant bridging or cortical draining veins entering the SSS near the tumor margin?",
        "Where is the safe stop point between sinus-wall peeling/coagulation and planned residual?",
        "If residual is left on the sinus/veins, what is the follow-up imaging and adjuvant radiosurgery/radiation threshold?",
    ]
    uncertainty_gaps = evidence.get("uncertainty_gaps") or [
        "Topic string says abutting SSS; do not assume true sinus wall invasion without venous imaging and operative findings.",
        "WHO grade, edema burden, sinus patency, venous dominance, and achieved extent of resection determine recurrence/adjuvant-therapy applicability.",
        "Curated pack sources need clinician confirmation against full text before being used for numeric counseling or institutional recommendations.",
    ]
    appendix = ""
    bucket_sections = []
    for heading, sources in sources_by_bucket.items():
        bucket_sections.append(f"## {heading}\n\n{_evidence_table(sources)}")
    return f"""# Evidence - {schema["topic"]}

## Clinical Questions

{_list_block(clinical_questions)}

## Bottom line for this case

{bottom_line}

## Evidence Pack Provenance

{_list_block(_parasagittal_sss_evidence_provenance(sources_by_bucket, literature_summary))}

## Study-Level Takeaways

{_list_block(_parasagittal_sss_study_takeaways())}

{chr(10).join(bucket_sections)}

## Applicability To This Case

{evidence.get("applicability_to_this_case") or "Apply this pack as operative framing for a parasagittal/SSS-adjacent meningioma, not as proof of sinus invasion. The practical decision is venous preservation versus incremental EOR at the sinus/bridging-vein interface."}

## Uncertainty / Evidence Gaps

{_list_block(uncertainty_gaps)}
{appendix}"""


def _render_evidence(schema: dict[str, Any], literature_summary: str | None = None) -> str:
    if _is_thrombectomy(schema):
        return _render_thrombectomy_evidence(schema, literature_summary)
    if _is_parasagittal_sss_meningioma(schema):
        return _render_parasagittal_sss_evidence(schema, literature_summary)
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
    if _is_thrombectomy(schema):
        return _render_thrombectomy_checklists(schema)
    if _is_acdf(schema):
        return _render_acdf_checklists(schema)
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


def _render_acdf_checklists(schema: dict[str, Any]) -> str:
    ctx = _acdf_context(schema)
    return f"""# Checklists - {schema["topic"]}

## Pre-Incision ACDF Safety Checklist

- Confirm patient, consent, approach side, and side/site/level localization plan for {ctx['level']}.
- Confirm baseline motor/sensory exam, myelopathy status, and baseline voice/swallow symptoms.
- Confirm imaging displayed: sagittal/axial MRI through {ctx['level']}, radiographs/fluoro localization, and CT if osteophyte/OPLL/bony anatomy matters.
- Confirm implant / fusion construct: graft/cage, plate/screws, zero-profile, or stand-alone device; ensure trials, screws, backup sizes, and fluoroscopy are available.
- Confirm recurrent laryngeal nerve, esophagus/trachea, carotid sheath, and vertebral artery risk points are in the team brief.
- Confirm hematoma/airway rescue plan: anesthesia awareness, postop neck checks, and immediate response pathway for stridor, swelling, or respiratory distress.
- Confirm drain, collar, antibiotics, steroid, anticoagulation/antiplatelet restart, and postop imaging plan.

## Must-Review Before Incision

- Imaging: symptomatic {ctx['root_target']} compression at {ctx['level']}; cord signal/myelopathy, alignment, uncinate/foraminal osteophyte, and vertebral artery boundary.
- Exposure: anterior cervical corridor between carotid sheath laterally and tracheoesophageal complex medially; protect esophagus and release retractors if prolonged.
- Technique: fluoroscopic localization before annulotomy, discectomy/decompression, PLL/uncinate/foramen strategy, endplate preparation, graft/cage placement, plate/screws/fixation.
- Consent-specific risks: dysphagia, dysphonia/recurrent laryngeal nerve palsy, esophageal injury, hematoma/airway compromise, vertebral artery injury, neurologic deficit/C5 palsy, pseudarthrosis/subsidence.
- Open questions: see `09-open-questions.md`.
"""


def _render_thrombectomy_checklists(schema: dict[str, Any]) -> str:
    return f"""# Checklists - {schema["topic"]}

## Pre-Puncture Stroke / EVT Safety Checklist

- Confirm patient, laterality, target vessel, consent/emergency consent pathway, and stroke-team activation.
- Confirm LKW/time window, NIHSS/disabling deficit, baseline mRS, glucose, anticoagulation/coagulopathy status, and IV tPA/TNK status.
- Confirm noncontrast CT/ASPECTS, CTA target ({_thrombectomy_target_context(schema)["target"]}; access/occlusion anatomy needs input if unspecified), and CTP/core-volume selection if late/extended window.
- Confirm anesthesia plan, BP floor/ceiling before reperfusion, and handoff plan for post-reperfusion BP target.
- Confirm femoral vs radial access plan, closure plan, guide/balloon-guide, distal access/aspiration catheter, stent retriever, aspiration setup, and rescue angioplasty/stenting supplies.
- Confirm roadmap working projections, pass strategy, mTICI target, and criteria to stop or switch strategy.
- Confirm neuro-ICU bed, postprocedure CT timing, antithrombotic hold/start rules, access-site checks, and malignant edema/hemorrhagic transformation watch.

## Must-Review Before Arterial Puncture

- Imaging: NCCT/CTA ± CTP confirms treatable {_thrombectomy_target_context(schema)["target"]} in the {_thrombectomy_target_context(schema)["circulation"]} and acceptable core/collateral profile; access/occlusion anatomy needs input if unspecified.
- Access/equipment: femoral/radial route, sheath, guide or balloon guide, distal access/aspiration catheter, microcatheter/wire, aspiration vs stent-retriever vs combined plan.
- Consent-specific risks: vessel perforation/SAH, symptomatic ICH, distal emboli/new territory embolus, dissection, vasospasm, failed recanalization, access-site hemorrhage, malignant edema.
- Team alerts: thrombolytic exposure, anticoagulation/coagulopathy, tandem lesion/stenting possibility, BP goals, and hemicraniectomy candidacy.
- Open questions: see `09-open-questions.md`.
"""


def _render_open_questions(schema: dict[str, Any]) -> str:
    if _is_thrombectomy(schema):
        return _render_thrombectomy_open_questions(schema)
    if _is_acdf(schema):
        return _render_acdf_open_questions(schema)
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



def _render_acdf_open_questions(schema: dict[str, Any]) -> str:
    ctx = _acdf_context(schema)
    return f"""# Open Questions - {schema["topic"]}

## Patient-Specific Missing Spine Facts

- Is {ctx['level']} definitively the symptomatic level on exam, MRI, and radiographs/fluoroscopy?
- What is the baseline motor/sensory deficit, reflex change, pain distribution, myelopathy status, and baseline voice/swallow function?
- Any prior anterior neck surgery, vocal cord dysfunction, radiation, infection/tumor, OPLL/calcified disc, smoking/diabetes/osteoporosis, or bone-healing risk?
- What anticoagulation/antiplatelet medication must be held or restarted, and what is the hematoma/airway risk plan?
- What postop destination, diet/swallow pathway, collar plan, drain plan, and upright cervical x-ray timing are expected?

## Attending / Team Questions

- Approach side and rationale, especially with recurrent laryngeal nerve/voice history or prior surgery?
- Implant / fusion construct: graft/cage type, plate/screws vs zero-profile vs stand-alone device, graft material, and backup sizes?
- PLL opening threshold, uncinate/foraminal decompression extent, and vertebral artery lateral stop point?
- Is posterior cervical foraminotomy a reasonable alternative or backup for this radiculopathy pattern, or is anterior fusion required by disc-space collapse, alignment, central disease, or instability?
- Drain, collar, steroids, antibiotics, postop imaging, activity restrictions, and fusion precautions?

## Safety-Critical Unknowns

- Side/site/level localization workflow and who confirms final level before discectomy?
- Airway/hematoma rescue plan and who can open the wound emergently if respiratory compromise occurs?
- Escalation plan for esophageal injury, vertebral artery bleeding, CSF leak, neuromonitoring change, or new neurologic deficit?
- Discharge readiness: swallowing, voice, airway, pain control, neurologic exam, ambulation, wound/drain, and follow-up imaging plan?
"""


def _thrombectomy_target_question(schema: dict[str, Any]) -> str:
    ctx = _thrombectomy_target_context(schema)
    target = str(ctx["target"])
    target_lower = target.casefold()
    if "m1" in target_lower:
        m1_target = target.replace(" M1 MCA", " M1")
        return f"{m1_target} vs ICA terminus, tandem/cervical carotid lesion, or more distal M2 branch"
    if not bool(ctx["known"]):
        return "target LVO; access/occlusion anatomy needs input"
    return f"{target}; confirm target vessel, laterality if applicable, tandem/cervical lesion, clot extent, distal branch involvement, and access route"


def _thrombectomy_open_questions(schema: dict[str, Any]) -> list[str]:
    facts = _case_facts(schema)
    questions: list[str] = []

    if has_known_fact(facts, "last_known_well"):
        questions.append(
            f"Confirm last-known-well {_known_fact_value(facts, 'last_known_well')}: witnessed vs unwitnessed/wake-up onset and treatment time window."
        )
    else:
        questions.append("LKW / last-known-well time, witnessed vs unwitnessed onset, and treatment time window?")

    if has_known_fact(facts, "nihss"):
        questions.append(
            f"Confirm current NIHSS/exam: NIHSS {_known_fact_value(facts, 'nihss')}, disabling deficit, cortical signs, and any interval change before puncture."
        )
    else:
        questions.append("What is the NIHSS and whether current deficit is disabling?")

    if has_known_fact(facts, "aspects"):
        questions.append(
            f"Confirm ASPECTS {_known_fact_value(facts, 'aspects')}: involved regions, mass effect, and whether large-core considerations apply."
        )
    else:
        questions.append(
            "What is the ASPECTS/core status on noncontrast CT, and if used, CTP/MRI core volume and mismatch profile?"
        )

    questions.extend(
        [
            "Collateral/perfusion quantitative unknowns: collateral grade, core volume, hypoperfusion/penumbra volume, mismatch ratio, and infarct-growth risk.",
            f"CTA/angiography target: {_thrombectomy_target_question(schema)}?",
            "IV tPA/TNK status, thrombolytic dose/time, contraindications, and required post-thrombolytic restrictions?",
            "Anticoagulation, antiplatelet use, platelet count/INR/DOAC timing, or other coagulopathy/lab constraints?",
            "Baseline mRS / pre-stroke functional status and goals-of-care constraints?",
        ]
    )

    if has_known_fact(facts, "access_route"):
        questions.append(
            f"Confirm access route {_known_fact_value(facts, 'access_route')}: pulses, arch/cervical anatomy, closure plan, bleeding risk, and crossover threshold."
        )
    else:
        questions.append(
            "Access concerns: route choice, femoral/radial pulses, aortic arch, cervical carotid tortuosity/stenosis, prior vascular surgery, obesity, or bleeding risk?"
        )

    questions.append(
        "Anesthesia plan and BP plan before reperfusion, after mTICI 2b/3 reperfusion, and if hemorrhage/extravasation occurs?"
    )
    return questions


def _thrombectomy_supplied_device_summary(schema: dict[str, Any]) -> str:
    facts = _case_facts(schema)
    parts = []
    if has_known_fact(facts, "balloon_guide"):
        parts.append("balloon guide/BGC")
    if has_known_fact(facts, "aspiration"):
        parts.append("aspiration")
    if has_known_fact(facts, "stent_retriever"):
        parts.append("stent retriever")
    return ", ".join(parts)


def _render_thrombectomy_open_questions(schema: dict[str, Any]) -> str:
    supplied_devices = _thrombectomy_supplied_device_summary(schema)
    technique_question = (
        f"Confirm supplied first-pass/device plan ({supplied_devices}) and fallback/switch strategy with attending."
        if supplied_devices
        else "Preferred first-pass technique: aspiration, stent retriever, or combined approach?"
    )
    return f"""# Open Questions - {schema["topic"]}

## Patient-Specific Missing Stroke Facts

{_list_block(_thrombectomy_open_questions(schema))}

## Attending / Team Questions

- {technique_question}
- Balloon-guide vs standard guide strategy and planned distal access/aspiration catheter if not already specified?
- Maximum number of passes before switching strategy or stopping?
- Rescue plan for tandem lesion, intracranial stenosis, failed recanalization, or early re-occlusion?
- Postprocedure antithrombotic timing if no stent, if carotid/intracranial stent, or if tPA/TNK was given?

## Safety-Critical Unknowns

- Neuro-ICU bed and immediate CT/CTA availability?
- Hemorrhagic transformation and malignant edema/hemicraniectomy watch plan for the affected territory?
- Access-site closure and monitoring plan, including who checks pulses/groin or radial band?
- Family contact/surrogate decision maker for emergent rescue stenting or decompressive surgery discussions?
"""


def render_caseprep_files(
    schema: dict[str, Any],
    *,
    provenance: list[Any] | None = None,
    literature_summary: str | None = None,
    anatomy_body: str | None = None,
    operative_body: str | None = None,
    risk_body: str | None = None,
) -> dict[str, str]:
    """Render dossier files through the pure markdown renderer."""
    from caseprep.renderers.markdown import render_caseprep_files as render_markdown

    render_kwargs = {
        "provenance": provenance,
        "literature_summary": literature_summary,
        "anatomy_body": anatomy_body,
        "operative_body": operative_body,
        "risk_body": risk_body,
    }
    return render_markdown(schema, **render_kwargs)


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
