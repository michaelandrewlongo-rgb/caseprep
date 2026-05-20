"""Tests for core provenance validation and strict-mode enforcement."""

from __future__ import annotations

import pytest

from caseprep.core import (
    CasePrepConfigurationError,
    CasePrepProvenanceError,
    EvidenceRecord,
    ProvenanceRecord,
)
from caseprep.provenance import (
    enforce_provenance,
    resolve_strict_provenance,
    validate_provenance,
)


def test_resolve_strict_provenance_defaults_to_off(monkeypatch):
    monkeypatch.delenv("CASEPREP_STRICT_PROVENANCE", raising=False)

    assert resolve_strict_provenance() == "off"


def test_resolve_strict_provenance_rejects_unknown_value(monkeypatch):
    monkeypatch.setenv("CASEPREP_STRICT_PROVENANCE", "strict")

    with pytest.raises(CasePrepConfigurationError) as exc:
        resolve_strict_provenance()

    assert exc.value.details["field"] == "CASEPREP_STRICT_PROVENANCE"


def test_validate_provenance_reports_dangling_evidence_ids_and_missing_fields():
    issues = validate_provenance(
        structured={"profile": {"name": "vascular"}, "sections": []},
        provenance=[
            ProvenanceRecord(
                field_path="sections.anatomy",
                source_ids=["pmid-1", "missing-id"],
                value_status="cited",
            )
        ],
        evidence=[
            EvidenceRecord(id="pmid-1", source="pubmed", title="Anatomy"),
        ],
        required_fields=["profile", "retrieval", "sections"],
    )

    assert "Dangling evidence ID missing-id in provenance sections.anatomy" in issues
    assert "Missing provenance for required field profile" in issues
    assert "Missing provenance for required field retrieval" in issues


def test_enforce_provenance_warn_mode_returns_warnings():
    warnings = enforce_provenance(
        structured={"profile": {"name": "vascular"}},
        provenance=[],
        evidence=[],
        required_fields=["profile"],
        strict_mode="warn",
    )

    assert warnings == [
        "Provenance warning: Missing provenance for required field profile"
    ]


def test_enforce_provenance_error_mode_raises_domain_error():
    with pytest.raises(CasePrepProvenanceError) as exc:
        enforce_provenance(
            structured={"profile": {"name": "vascular"}},
            provenance=[],
            evidence=[],
            required_fields=["profile"],
            strict_mode="error",
        )

    assert exc.value.details["issues"] == [
        "Missing provenance for required field profile"
    ]


def test_enforce_provenance_off_mode_is_non_blocking():
    warnings = enforce_provenance(
        structured={"profile": {"name": "vascular"}},
        provenance=[],
        evidence=[],
        required_fields=["profile"],
        strict_mode="off",
    )

    assert warnings == []
