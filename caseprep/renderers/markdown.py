"""Pure markdown renderer for structured CasePrep dossiers."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, Sequence

from caseprep.core import ProvenanceRecord
from caseprep.schema import (
    LEGACY_MARKDOWN_ALIASES,
    _render_anatomy,
    _render_case_summary,
    _render_checklists,
    _render_evidence,
    _render_imaging,
    _render_morning_of_case,
    _render_open_questions,
    _render_operative_plan,
    _render_postop,
    _render_readme,
    _render_risk,
    dump_yaml,
)


def _provenance_to_dict(record: ProvenanceRecord | dict[str, Any]) -> dict[str, Any]:
    if isinstance(record, ProvenanceRecord):
        return record.to_dict()
    return dict(record)


def _with_provenance(
    case_object: dict[str, Any],
    provenance: Sequence[ProvenanceRecord | dict[str, Any]] | None,
) -> dict[str, Any]:
    if provenance is None:
        return case_object
    rendered_object = deepcopy(case_object)
    rendered_object["provenance"] = [
        _provenance_to_dict(record) for record in provenance
    ]
    return rendered_object


def render_caseprep_files(
    case_object: dict[str, Any],
    *,
    provenance: Sequence[ProvenanceRecord | dict[str, Any]] | None = None,
    literature_summary: str | None = None,
    anatomy_body: str | None = None,
    operative_body: str | None = None,
    risk_body: str | None = None,
) -> dict[str, str]:
    """Render structured case data, parsed case summary, and provenance into dossier files."""
    schema = _with_provenance(case_object, provenance)
    files = {
        "caseprep.yaml": dump_yaml(schema) + "\n",
        "provenance.json": json.dumps(
            schema.get("provenance", []),
            indent=2,
        ) + "\n",
        "README.md": _render_readme(schema),
        "00-morning-of-case.md": _render_morning_of_case(schema),
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
