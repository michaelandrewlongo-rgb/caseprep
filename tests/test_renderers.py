"""Tests for pure CasePrep renderers and dual-write flags."""

from __future__ import annotations

import json

import pytest

from caseprep.core import CasePrepConfigurationError, ProvenanceRecord
from caseprep.case_parser import parse_case_input, select_procedure_family
from caseprep.links import build_search_links
from caseprep.schema import build_caseprep_schema


def test_markdown_renderer_matches_legacy_schema_output():
    from caseprep.schema import _legacy_render_caseprep_files
    from caseprep.renderers.markdown import render_caseprep_files

    schema = build_caseprep_schema(
        "retrosigmoid vestibular schwannoma",
        profile="skull_base",
    )

    assert render_caseprep_files(schema) == _legacy_render_caseprep_files(schema)


def test_markdown_renderer_accepts_provenance_without_mutating_schema():
    from caseprep.renderers.markdown import render_caseprep_files

    schema = build_caseprep_schema("aneurysm", profile="vascular")
    original_provenance = list(schema["provenance"])
    provenance = [
        ProvenanceRecord(
            field_path="sections.anatomy",
            source_ids=["pmid-1"],
            value_status="cited",
        )
    ]

    rendered = render_caseprep_files(schema, provenance=provenance)

    assert json.loads(rendered["provenance.json"]) == [
        {
            "field_path": "sections.anatomy",
            "source_ids": ["pmid-1"],
            "value_status": "cited",
            "generated_by": "caseprep",
            "notes": "",
        }
    ]
    assert schema["provenance"] == original_provenance


def test_markdown_renderer_includes_structured_case_summary():
    from caseprep.renderers.markdown import render_caseprep_files

    case_spec = parse_case_input(
        "C5-6 anterior cervical discectomy and fusion for right C6 radiculopathy"
    )
    family = select_procedure_family(case_spec)
    assert family is not None
    schema = build_caseprep_schema(
        case_spec.raw_input,
        profile="spine",
        structured_case=case_spec.to_dict(),
        procedure_family={
            "id": family.id,
            "display_name": family.display_name,
            "broad_profile": family.broad_profile,
            "required_fields": list(family.required_fields),
            "missing_fact_prompts": list(family.missing_fact_prompts),
        },
    )

    rendered = render_caseprep_files(schema)["01-case-summary.md"]

    assert "## Parsed Case Summary" in rendered
    assert "Raw case input: C5-6 anterior cervical discectomy" in rendered
    assert "Parsed procedure: anterior cervical discectomy and fusion" in rendered
    assert "Procedure family: Anterior cervical discectomy and fusion (ACDF) (`spine_acdf`)" in rendered
    assert "Broad profile: spine" in rendered
    assert "Missing critical facts:" in rendered


def test_markdown_renderer_thrombectomy_adds_morning_file_and_propagates_snapshot():
    from caseprep.renderers.markdown import render_caseprep_files

    case_spec = parse_case_input(
        "mechanical thrombectomy for acute ischemic stroke due to right M1 MCA occlusion"
    )
    family = select_procedure_family(case_spec)
    assert family is not None
    schema = build_caseprep_schema(
        case_spec.raw_input,
        profile="vascular",
        structured_case=case_spec.to_dict(),
        procedure_family={
            "id": family.id,
            "display_name": family.display_name,
            "broad_profile": family.broad_profile,
            "required_fields": list(family.required_fields),
            "missing_fact_prompts": list(family.missing_fact_prompts),
        },
    )

    rendered = render_caseprep_files(schema)

    assert "00-morning-of-case.md" in rendered
    assert "00-morning-of-case.md" in rendered["README.md"]
    assert "Planned procedure: mechanical thrombectomy" in rendered["01-case-summary.md"]
    assert "Laterality: right" in rendered["01-case-summary.md"]
    assert "right M1 MCA occlusion" in rendered["00-morning-of-case.md"]
    assert "Structured Thrombectomy Decision Tables" in rendered["04-operative-plan.md"]
    combined = "\n".join(rendered.values()).casefold()
    assert "right right m1" not in combined


def test_thrombectomy_evidence_renderer_shows_pack_coverage_and_hierarchy():
    from caseprep.renderers.markdown import render_caseprep_files

    case_spec = parse_case_input(
        "mechanical thrombectomy for acute ischemic stroke due to right M1 MCA occlusion"
    )
    family = select_procedure_family(case_spec)
    assert family is not None
    schema = build_caseprep_schema(
        case_spec.raw_input,
        profile="vascular",
        structured_case=case_spec.to_dict(),
        procedure_family={
            "id": family.id,
            "display_name": family.display_name,
            "broad_profile": family.broad_profile,
            "required_fields": list(family.required_fields),
            "missing_fact_prompts": list(family.missing_fact_prompts),
        },
    )
    schema["case"]["evidence"]["key_sources"] = [
        {
            "id": "pmid-25517348",
            "title": "A Randomized Trial of Intraarterial Treatment for Acute Ischemic Stroke",
            "pmid": "25517348",
            "doi": "10.1056/NEJMoa1411587",
            "tier": "practice-changing RCT",
            "source_tier": "practice-changing RCT",
            "evidence_role": "early-window EVT trial",
            "applicability": "Directly applicable to anterior-circulation M1 LVO EVT.",
            "verification": "retrieved",
        },
        {
            "id": "pmid-41582814",
            "title": "Current AHA/ASA guideline for acute ischemic stroke EVT",
            "pmid": "41582814",
            "doi": "10.1161/STR.0000000000000513",
            "tier": "guideline/consensus",
            "source_tier": "guideline/consensus",
            "evidence_role": "guideline",
            "applicability": "Use to verify current EVT eligibility and peri-procedural standards.",
            "verification": "retrieved",
        },
        {
            "id": "pmid-select2",
            "title": "Trial of Endovascular Thrombectomy for Large Ischemic Strokes",
            "pmid": "36762865",
            "doi": "10.1056/NEJMoa2214403",
            "tier": "large-core conditional RCT",
            "source_tier": "large-core conditional RCT",
            "evidence_role": "large-core conditional evidence",
            "applicability": "Conditional: only if large-core selection criteria apply.",
            "verification": "retrieved",
        },
        {
            "id": "pmid-ai",
            "title": "Artificial intelligence workflow triage for stroke thrombectomy",
            "tier": "workflow study",
            "evidence_role": "workflow-only",
            "applicability": "Workflow only; not part of clinical EVT benefit hierarchy.",
            "verification": "cited",
            "clinical_include": False,
            "quarantine_reason": "AI/workflow-only source",
        },
    ]
    schema["case"]["evidence"]["evidence_pack"] = {
        "id": "anterior_circulation_lvo_m1",
        "retrieved": [{"pack_item_id": "mr_clean", "pmid": "25517348"}],
        "missing": [{"pack_item_id": "escape", "pmid": "25671798", "doi": "10.1056/NEJMoa1414905"}],
        "partial": [],
    }

    evidence_md = render_caseprep_files(schema)["07-evidence.md"]

    for heading in [
        "## Landmark Evidence Coverage",
        "## Practice-Changing EVT Evidence",
        "## Guidelines / Consensus",
        "## Late-Window Evidence",
        "## Large-Core Conditional Evidence",
        "## Technique and Device Evidence",
        "## Quarantined / Lower-Applicability Sources",
        "## Missing or Partial Evidence",
    ]:
        assert heading in evidence_md
    assert "25517348" in evidence_md
    assert "10.1056/NEJMoa1411587" in evidence_md
    assert "A Randomized Trial" in evidence_md
    assert "Current AHA/ASA" in evidence_md
    assert "SELECT2" in evidence_md or "Large Ischemic Strokes" in evidence_md
    assert "Artificial intelligence workflow" in evidence_md
    assert "AI/workflow-only source" in evidence_md
    assert "escape" in evidence_md
    assert "25671798" in evidence_md


def test_markdown_renderer_labels_degraded_missing_approach_as_generic():
    from caseprep.renderers.markdown import render_caseprep_files

    case_spec = parse_case_input("Chiari")
    schema = build_caseprep_schema(
        case_spec.raw_input,
        profile="posterior_fossa",
        structured_case=case_spec.to_dict(),
        procedure_family=None,
    )

    rendered = render_caseprep_files(schema)["01-case-summary.md"]

    assert "Degradation status: degraded/generic case summary" in rendered
    assert "Parsed approach: generic/degraded — no booked approach identified" in rendered
    assert "do not treat as a confirmed booked approach" in rendered
    assert "Approach: suboccipital" not in rendered


def test_html_renderer_matches_resource_links_template():
    from caseprep.generator import RESOURCE_HTML_TEMPLATE, _link_items_html
    from caseprep.renderers.html import render_resource_links_html

    topic = "glioma"
    links = build_search_links(topic)

    assert render_resource_links_html(topic, links) == RESOURCE_HTML_TEMPLATE.format(
        topic=topic,
        link_items=_link_items_html(links),
    )


def test_renderer_boolean_flags(monkeypatch):
    from caseprep.renderers import (
        resolve_compare_outputs_enabled,
        resolve_dual_write_enabled,
    )

    monkeypatch.delenv("CASEPREP_DUAL_WRITE", raising=False)
    monkeypatch.delenv("CASEPREP_COMPARE_OUTPUTS", raising=False)
    assert resolve_dual_write_enabled() is False
    assert resolve_compare_outputs_enabled() is False

    monkeypatch.setenv("CASEPREP_DUAL_WRITE", "1")
    monkeypatch.setenv("CASEPREP_COMPARE_OUTPUTS", "1")
    assert resolve_dual_write_enabled() is True
    assert resolve_compare_outputs_enabled() is True

    monkeypatch.setenv("CASEPREP_DUAL_WRITE", "yes")
    with pytest.raises(CasePrepConfigurationError) as exc:
        resolve_dual_write_enabled()
    assert exc.value.details["field"] == "CASEPREP_DUAL_WRITE"


def test_schema_dual_write_compare_raises_on_mismatch(monkeypatch):
    import caseprep.schema as schema_module
    from caseprep.core import CasePrepValidationError

    schema = build_caseprep_schema("aneurysm", profile="vascular")

    def fake_renderer(case_object, **kwargs):
        kwargs.pop("provenance", None)
        rendered = schema_module._legacy_render_caseprep_files(case_object, **kwargs)
        rendered["README.md"] += "\nchanged\n"
        return rendered

    monkeypatch.setenv("CASEPREP_DUAL_WRITE", "1")
    monkeypatch.setenv("CASEPREP_COMPARE_OUTPUTS", "1")
    monkeypatch.setattr(
        "caseprep.renderers.markdown.render_caseprep_files",
        fake_renderer,
    )

    with pytest.raises(CasePrepValidationError) as exc:
        schema_module.render_caseprep_files(schema)

    assert exc.value.details["diffs"] == ["Changed rendered file README.md"]
