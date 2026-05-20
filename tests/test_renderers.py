"""Tests for pure CasePrep renderers and dual-write flags."""

from __future__ import annotations

import json

import pytest

from caseprep.core import CasePrepConfigurationError, ProvenanceRecord
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
