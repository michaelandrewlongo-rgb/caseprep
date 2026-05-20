"""Provenance validation and strict-mode enforcement for CasePrep core."""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from typing import Literal

from caseprep.core import (
    CasePrepConfigurationError,
    CasePrepProvenanceError,
    EvidenceRecord,
    ProvenanceRecord,
)
from caseprep.synthesis.section_synthesis import SectionDraft


StrictProvenanceMode = Literal["off", "warn", "error"]
VALID_STRICT_PROVENANCE_MODES: set[str] = {"off", "warn", "error"}


def resolve_strict_provenance(
    env: Mapping[str, str] | None = None,
) -> StrictProvenanceMode:
    values = env if env is not None else os.environ
    raw_mode = values.get("CASEPREP_STRICT_PROVENANCE", "off").strip().lower()
    mode = raw_mode or "off"
    if mode not in VALID_STRICT_PROVENANCE_MODES:
        raise CasePrepConfigurationError(
            "CASEPREP_STRICT_PROVENANCE must be one of off, warn, or error",
            details={"field": "CASEPREP_STRICT_PROVENANCE", "value": raw_mode},
        )
    return mode  # type: ignore[return-value]


def _lookup_path(data: dict[str, object], field_path: str) -> object:
    current: object = data
    for part in field_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _has_value(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _matches_required_field(record: ProvenanceRecord, field_path: str) -> bool:
    return (
        record.field_path == field_path
        or record.field_path.startswith(f"{field_path}.")
    )


def validate_provenance(
    *,
    structured: dict[str, object],
    provenance: Sequence[ProvenanceRecord],
    evidence: Sequence[EvidenceRecord],
    required_fields: Sequence[str] = (),
) -> list[str]:
    """Return deterministic provenance validation issues."""
    issues: list[str] = []
    evidence_ids = {record.id for record in evidence if record.id}

    for record in provenance:
        for source_id in record.source_ids:
            if source_id not in evidence_ids:
                issues.append(
                    f"Dangling evidence ID {source_id} in provenance "
                    f"{record.field_path}"
                )

    for field_path in required_fields:
        matching = [
            record
            for record in provenance
            if _matches_required_field(record, field_path)
        ]
        if not matching:
            issues.append(f"Missing provenance for required field {field_path}")
            continue

        value = _lookup_path(structured, field_path)
        has_generated_value = any(
            record.value_status in {"generated", "cited"}
            for record in matching
        )
        has_cited_sources = any(record.source_ids for record in matching)
        if not _has_value(value) or not (has_generated_value or has_cited_sources):
            issues.append(
                f"Required field {field_path} has no provenance-backed value"
            )

    return issues


def enforce_provenance(
    *,
    structured: dict[str, object],
    provenance: Sequence[ProvenanceRecord],
    evidence: Sequence[EvidenceRecord],
    required_fields: Sequence[str] = (),
    strict_mode: StrictProvenanceMode | None = None,
    env: Mapping[str, str] | None = None,
) -> list[str]:
    """Apply CASEPREP_STRICT_PROVENANCE semantics to validation issues."""
    mode = strict_mode or resolve_strict_provenance(env)
    if mode == "off":
        return []

    issues = validate_provenance(
        structured=structured,
        provenance=provenance,
        evidence=evidence,
        required_fields=required_fields,
    )
    if not issues:
        return []
    if mode == "warn":
        return [f"Provenance warning: {issue}" for issue in issues]
    raise CasePrepProvenanceError(
        "Strict provenance validation failed",
        details={"issues": issues},
    )


def build_core_provenance(
    *,
    structured: dict[str, object],
    evidence: Sequence[EvidenceRecord],
    sections: Sequence[SectionDraft],
) -> list[ProvenanceRecord]:
    """Create field-level provenance for the current core structured result."""
    evidence_ids = [record.id for record in evidence if record.id]
    records = [
        ProvenanceRecord(
            field_path="profile",
            source_ids=[],
            value_status="generated",
            generated_by="caseprep.core.profile_classifier",
            notes="Profile classified deterministically from topic and hint.",
        ),
        ProvenanceRecord(
            field_path="retrieval",
            source_ids=evidence_ids,
            value_status="cited" if evidence_ids else "needs_input",
            generated_by="caseprep.core.retrievers",
            notes="Normalized evidence returned by core retrievers.",
        ),
        ProvenanceRecord(
            field_path="sections",
            source_ids=evidence_ids,
            value_status="cited" if sections else "needs_input",
            generated_by="caseprep.synthesis.section_synthesis",
            notes="Section drafts grouped from normalized evidence.",
        ),
    ]
    records.extend(
        ProvenanceRecord(
            field_path=section.field_path,
            source_ids=section.evidence_ids,
            value_status="cited",
            generated_by="caseprep.synthesis.section_synthesis",
            notes=f"Section draft cites evidence IDs for {section.title}.",
        )
        for section in sections
    )
    return records
