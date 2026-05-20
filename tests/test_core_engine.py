"""Tests for the shared CasePrep core engine facade contracts."""

from __future__ import annotations

from pathlib import Path

import pytest

from caseprep.core import (
    ArtifactRef,
    BuildCasePlanRequest,
    CasePlanBuilder,
    CasePrepConfigurationError,
    CasePrepExternalServiceError,
    CasePrepValidationError,
    resolve_core_mode,
)


def test_build_case_plan_request_normalizes_topic_and_legacy_args(tmp_path):
    output_dir = tmp_path / "vs-caseprep"
    request = BuildCasePlanRequest(
        topic="  vestibular schwannoma  ",
        output_dir=output_dir,
        max_per_category=4,
        profile_hint="skull_base",
        structured_output=True,
    )

    assert request.topic == "vestibular schwannoma"
    assert request.output_dir == output_dir
    assert request.to_legacy_args() == {
        "topic": "vestibular schwannoma",
        "output_dir": str(output_dir),
        "max_per_category": 4,
        "profile_hint": "skull_base",
    }


def test_build_case_plan_request_rejects_blank_topic():
    with pytest.raises(CasePrepValidationError) as exc:
        BuildCasePlanRequest(topic=" ")

    assert exc.value.code == "validation_error"
    assert exc.value.details["field"] == "topic"


def test_domain_errors_expose_stable_payloads():
    error = CasePrepExternalServiceError(
        "PubMed request failed",
        details={"provider": "pubmed"},
    )

    assert error.to_dict() == {
        "error": "external_service_error",
        "message": "PubMed request failed",
        "details": {"provider": "pubmed"},
    }


def test_artifact_ref_serializes_paths(tmp_path):
    artifact = ArtifactRef(
        path=tmp_path / "caseprep.yaml",
        kind="caseprep_yaml",
        media_type="application/x-yaml",
    )

    assert artifact.to_dict() == {
        "path": str(tmp_path / "caseprep.yaml"),
        "kind": "caseprep_yaml",
        "media_type": "application/x-yaml",
        "label": None,
        "metadata": {},
    }


def test_resolve_core_mode_defaults_to_legacy(monkeypatch):
    monkeypatch.delenv("CASEPREP_CORE_MODE", raising=False)

    assert resolve_core_mode() == "legacy"


def test_resolve_core_mode_rejects_unknown_value(monkeypatch):
    monkeypatch.setenv("CASEPREP_CORE_MODE", "experimental")

    with pytest.raises(CasePrepConfigurationError) as exc:
        resolve_core_mode()

    assert exc.value.details["field"] == "CASEPREP_CORE_MODE"


@pytest.mark.asyncio
async def test_case_plan_builder_legacy_mode_delegates_to_legacy_builder(tmp_path):
    calls = []

    async def legacy_builder(request: BuildCasePlanRequest) -> str:
        calls.append(request.to_legacy_args())
        return "# Case Plan\n\nlegacy output"

    request = BuildCasePlanRequest(
        topic="glioma",
        output_dir=tmp_path / "glioma-caseprep",
        max_per_category=2,
    )
    builder = CasePlanBuilder(mode="legacy", legacy_builder=legacy_builder)

    result = await builder.build_case_plan(request)

    assert calls == [
        {
            "topic": "glioma",
            "output_dir": str(tmp_path / "glioma-caseprep"),
            "max_per_category": 2,
        }
    ]
    assert result.topic == "glioma"
    assert result.markdown == "# Case Plan\n\nlegacy output"
    assert result.output_dir == tmp_path / "glioma-caseprep"
    assert result.mode == "legacy"
    assert result.evidence == []
    assert result.provenance == []


@pytest.mark.asyncio
async def test_case_plan_builder_shadow_mode_returns_legacy_output_with_warning():
    async def legacy_builder(request: BuildCasePlanRequest) -> str:
        return "legacy output"

    builder = CasePlanBuilder(mode="shadow", legacy_builder=legacy_builder)

    result = await builder.build_case_plan(BuildCasePlanRequest(topic="aneurysm"))

    assert result.markdown == "legacy output"
    assert result.mode == "shadow"
    assert result.warnings == [
        "CASEPREP_CORE_MODE=shadow ran legacy only because no core builder is configured."
    ]


@pytest.mark.asyncio
async def test_case_plan_builder_core_mode_requires_core_builder():
    builder = CasePlanBuilder(mode="core", legacy_builder=lambda request: "legacy")

    with pytest.raises(CasePrepConfigurationError) as exc:
        await builder.build_case_plan(BuildCasePlanRequest(topic="aneurysm"))

    assert "core builder is not configured" in str(exc.value)
