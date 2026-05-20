"""Tests for pure core section synthesis."""

from __future__ import annotations

from caseprep.core import EvidenceRecord
from caseprep.synthesis.section_synthesis import synthesize_sections


def test_synthesize_sections_groups_evidence_by_axis_and_cites_ids():
    evidence = [
        EvidenceRecord(
            id="pmid-1",
            source="pubmed",
            title="Aneurysm Anatomy",
            text="Perforators arise near the aneurysm neck.",
            metadata={"axis": "Anatomy / Relevant Structures"},
        ),
        EvidenceRecord(
            id="pmid-2",
            source="pubmed",
            title="Aneurysm Outcomes",
            text="Durable occlusion was reported.",
            metadata={"axis": "Outcomes / Evidence"},
        ),
        EvidenceRecord(
            id="corpus-W1",
            source="corpus",
            title="Local Corpus Note",
            text="Institutional checklist emphasizes bailout plans.",
            metadata={"axis": "Outcomes / Evidence"},
        ),
    ]

    sections = synthesize_sections("acom aneurysm clipping", evidence)

    assert [section.id for section in sections] == [
        "anatomy-relevant-structures",
        "outcomes-evidence",
    ]
    anatomy = sections[0]
    assert anatomy.field_path == "sections.anatomy-relevant-structures"
    assert anatomy.evidence_ids == ["pmid-1"]
    assert "[pmid-1]" in anatomy.body

    outcomes = sections[1]
    assert outcomes.evidence_ids == ["pmid-2", "corpus-W1"]
    assert "[pmid-2]" in outcomes.body
    assert "[corpus-W1]" in outcomes.body


def test_synthesize_sections_omits_records_without_ids():
    sections = synthesize_sections(
        "topic",
        [
            EvidenceRecord(
                id="",
                source="pubmed",
                title="No ID",
                metadata={"axis": "Complications"},
            )
        ],
    )

    assert sections == []
