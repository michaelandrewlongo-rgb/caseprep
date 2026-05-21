"""Pure deterministic section drafting from normalized evidence."""

from __future__ import annotations

import re
from dataclasses import dataclass

from caseprep.core import EvidenceRecord


@dataclass(frozen=True)
class SectionDraft:
    """Structured section draft with explicit evidence support."""

    id: str
    title: str
    body: str
    evidence_ids: list[str]
    field_path: str

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "title": self.title,
            "body": self.body,
            "evidence_ids": self.evidence_ids,
            "field_path": self.field_path,
        }


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "section"


def _axis_for(record: EvidenceRecord) -> str:
    axis = str(record.metadata.get("axis") or "").strip()
    return axis or "Evidence"


def _summary_for(record: EvidenceRecord) -> str:
    title = record.title.strip()
    text = " ".join(record.text.split())
    if title and text:
        return f"{title}: {text}"
    if title:
        return title
    if text:
        return text
    return f"{record.source} evidence"


def synthesize_sections(
    topic: str,
    evidence: list[EvidenceRecord],
) -> list[SectionDraft]:
    """Draft evidence-backed sections without transport or provider access."""
    grouped: dict[str, list[EvidenceRecord]] = {}
    for record in evidence:
        if not record.id.strip():
            continue
        if record.metadata.get("clinical_include") is False:
            continue
        grouped.setdefault(_axis_for(record), []).append(record)

    sections: list[SectionDraft] = []
    for axis, records in grouped.items():
        section_id = _slugify(axis)
        evidence_ids = [record.id for record in records]
        body_lines = [
            f"- {_summary_for(record)} [{record.id}]"
            for record in records
        ]
        sections.append(
            SectionDraft(
                id=section_id,
                title=axis,
                body="\n".join(body_lines),
                evidence_ids=evidence_ids,
                field_path=f"sections.{section_id}",
            )
        )
    return sections
