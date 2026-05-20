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
        "aneurysm_sah",
        2,
    )


@pytest.mark.asyncio
async def test_core_builder_maps_mma_csdh_to_hemorrhage_corpus_subdomain():
    calls = []

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

    class FakeCorpusRetriever:
        def retrieve(self, fts_query, *, subdomain=None, top_n=8):
            calls.append((fts_query, subdomain, top_n))
            return [
                EvidenceRecord(
                    id="corpus-csdh",
                    source="corpus",
                    title="MMA embolization for chronic subdural hematoma",
                    text="MMA embolization evidence.",
                )
            ]

    result = await build_core_case_plan(
        BuildCasePlanRequest(
            topic="middle meningeal artery embolization chronic subdural hematoma",
            max_per_category=1,
        ),
        retrievers=CoreRetrieverSet(
            pubmed=EmptyPubMedRetriever(),
            radiology=EmptyRadiologyRetriever(),
            corpus=FakeCorpusRetriever(),
        ),
    )

    assert calls == [
        (
            "middle meningeal artery embolization chronic subdural hematoma",
            "intracranial_hemorrhage",
            1,
        )
    ]
    assert result.structured["retrieval"]["sources"]["corpus"] == 1


@pytest.mark.asyncio
async def test_core_builder_writes_synthesized_sections_to_dossier_files(tmp_path):
    class FakePubMedRetriever:
        async def retrieve(
            self,
            query,
            *,
            max_results=10,
            filter_type=None,
            include_abstracts=True,
        ):
            if filter_type == "therapy":
                return []
            if "surgical technique" in query:
                return [
                    EvidenceRecord(
                        id="pmid-technique",
                        source="pubmed",
                        title="Technique Evidence",
                        text="Use bilateral distal middle meningeal artery access.",
                        metadata={"pubdate": "2024", "axis": "Surgical Technique"},
                    )
                ]
            if "complications" in query:
                return [
                    EvidenceRecord(
                        id="pmid-complication",
                        source="pubmed",
                        title="Complication Evidence",
                        text="Postprocedure seizure risk requires monitoring.",
                        metadata={"pubdate": "2025", "axis": "Complications"},
                    )
                ]
            return [
                EvidenceRecord(
                    id="pmid-anatomy",
                    source="pubmed",
                    title="Anatomy Evidence",
                    text="The middle meningeal artery supplies the dura.",
                    metadata={
                        "pubdate": "2023",
                        "axis": "Anatomy / Relevant Structures",
                    },
                )
            ]

    class EmptyRadiologyRetriever:
        async def retrieve(self, query, *, max_results=5, modality=None):
            return []

    class EmptyCorpusRetriever:
        def retrieve(self, fts_query, *, subdomain=None, top_n=8):
            return []

    output_dir = tmp_path / "mma-csdh-caseprep"

    result = await build_core_case_plan(
        BuildCasePlanRequest(
            topic="middle meningeal artery embolization chronic subdural hematoma",
            output_dir=output_dir,
            max_per_category=1,
        ),
        retrievers=CoreRetrieverSet(
            pubmed=FakePubMedRetriever(),
            radiology=EmptyRadiologyRetriever(),
            corpus=EmptyCorpusRetriever(),
        ),
    )

    anatomy = (output_dir / "03-anatomy-at-risk.md").read_text(encoding="utf-8")
    operative = (output_dir / "04-operative-plan.md").read_text(encoding="utf-8")
    risk = (output_dir / "05-risk-and-rescue.md").read_text(encoding="utf-8")
    evidence = (output_dir / "07-evidence.md").read_text(encoding="utf-8")

    assert "The middle meningeal artery supplies the dura. [pmid-anatomy]" in anatomy
    assert (
        "Use bilateral distal middle meningeal artery access. [pmid-technique]"
        in operative
    )
    assert (
        "Postprocedure seizure risk requires monitoring. [pmid-complication]"
        in risk
    )
    assert "pmid-anatomy" in evidence
    assert "03-anatomy-at-risk.md" in {artifact.path.name for artifact in result.artifacts}


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
