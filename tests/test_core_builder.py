"""Tests for the initial transport-agnostic CasePrep core builder."""

from __future__ import annotations

import pytest

from caseprep.core import BuildCasePlanRequest, EvidenceRecord
from caseprep.core.builder import CoreRetrieverSet, build_core_case_plan


@pytest.mark.asyncio
async def test_core_builder_classifies_profile_and_normalizes_retriever_evidence():
    calls = []

    class FakePubMedRetriever:
        async def retrieve(
            self,
            query,
            *,
            max_results=10,
            filter_type=None,
            include_abstracts=True,
        ):
            calls.append(
                ("pubmed", query, max_results, filter_type, include_abstracts)
            )
            axis = filter_type or "unfiltered"
            return [
                EvidenceRecord(
                    id=f"pmid-{len(calls)}",
                    source="pubmed",
                    title=query,
                    metadata={"axis": axis},
                )
            ]

    class FakeRadiologyRetriever:
        async def retrieve(self, query, *, max_results=5, modality=None):
            calls.append(("radiology", query, max_results, modality))
            return [
                EvidenceRecord(
                    id="openi-1",
                    source="openi",
                    title="Aneurysm angiogram",
                )
            ]

    class FakeCorpusRetriever:
        def retrieve(self, fts_query, *, subdomain=None, top_n=8):
            calls.append(("corpus", fts_query, subdomain, top_n))
            return [
                EvidenceRecord(
                    id="corpus-W1",
                    source="corpus",
                    title="Aneurysm corpus paper",
                )
            ]

    result = await build_core_case_plan(
        BuildCasePlanRequest(
            topic="anterior communicating artery aneurysm clipping",
            max_per_category=2,
        ),
        retrievers=CoreRetrieverSet(
            pubmed=FakePubMedRetriever(),
            radiology=FakeRadiologyRetriever(),
            corpus=FakeCorpusRetriever(),
        ),
    )

    assert result.mode == "core"
    assert result.topic == "anterior communicating artery aneurysm clipping"
    assert result.structured["profile"]["name"] == "vascular"
    assert result.structured["profile"]["source"] == "substring"
    assert result.structured["retrieval"]["evidence_count"] == 7
    assert result.structured["retrieval"]["pubmed_axes"] == [
        "Anatomy / Relevant Structures",
        "Outcomes / Evidence",
        "Surgical Technique",
        "Complications",
        "Reviews / Landmarks",
    ]
    assert result.structured["sections"][0]["id"] == "anatomy-relevant-structures"
    assert result.structured["sections"][0]["evidence_ids"] == ["pmid-1"]
    assert any(
        record.field_path == "sections.anatomy-relevant-structures"
        and record.source_ids == ["pmid-1"]
        for record in result.provenance
    )
    assert any(
        record.field_path == "profile"
        and record.value_status == "generated"
        for record in result.provenance
    )
    assert {record.source for record in result.evidence} == {
        "corpus",
        "openi",
        "pubmed",
    }
    assert calls[0][0] == "pubmed"
    assert "anterior communicating artery aneurysm clipping" in calls[0][1]
    assert calls[0][2] == 2
    assert calls[-2] == (
        "radiology",
        "anterior communicating artery aneurysm clipping radiology imaging",
        2,
        None,
    )
    assert calls[-1] == (
        "corpus",
        "anterior communicating artery aneurysm clipping",
        "vascular",
        2,
    )


@pytest.mark.asyncio
async def test_core_builder_strict_provenance_warn_mode_surfaces_warnings(monkeypatch):
    class EmptyPubMedRetriever:
        async def retrieve(
            self,
            query,
            *,
            max_results=10,
            filter_type=None,
            include_abstracts=True,
        ):
            return []

    class EmptyRadiologyRetriever:
        async def retrieve(self, query, *, max_results=5, modality=None):
            return []

    class EmptyCorpusRetriever:
        def retrieve(self, fts_query, *, subdomain=None, top_n=8):
            return []

    monkeypatch.setenv("CASEPREP_STRICT_PROVENANCE", "warn")

    result = await build_core_case_plan(
        BuildCasePlanRequest(topic="aneurysm", max_per_category=1),
        retrievers=CoreRetrieverSet(
            pubmed=EmptyPubMedRetriever(),
            radiology=EmptyRadiologyRetriever(),
            corpus=EmptyCorpusRetriever(),
        ),
    )

    assert any(
        warning
        == "Provenance warning: Required field sections has no provenance-backed value"
        for warning in result.warnings
    )
