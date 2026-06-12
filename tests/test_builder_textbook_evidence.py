"""The core builder gathers textbook-rag evidence on the Textbook axis."""

from __future__ import annotations

import pytest

from caseprep.core import BuildCasePlanRequest, EvidenceRecord
from caseprep.core.builder import CoreRetrieverSet, build_core_case_plan


class FakePubMedRetriever:
    async def retrieve(self, query, *, max_results=10, filter_type=None,
                       include_abstracts=True):
        return []


class FakeRadiologyRetriever:
    async def retrieve(self, query, *, max_results=5, modality=None):
        return []


class FakeCorpusRetriever:
    def retrieve(self, fts_query, *, subdomain=None, top_n=8):
        return []


class FakeTextbookRetriever:
    def __init__(self):
        self.calls = []

    def retrieve(self, query, *, subdomain=None, top_n=6):
        self.calls.append((query, subdomain, top_n))
        return [
            EvidenceRecord(
                id="textbook-Benzel Spine-p726",
                source="textbook",
                title="Benzel Spine (p.592)",
                text="Anterior-only two-level corpectomy failure rates rise.",
                metadata={
                    "book": "Benzel Spine",
                    "page": 726,
                    "printed_page": "592",
                    "citation": "Benzel Spine, p.592",
                },
            )
        ]


@pytest.mark.asyncio
async def test_builder_gathers_textbook_evidence_on_textbook_axis():
    textbook = FakeTextbookRetriever()
    result = await build_core_case_plan(
        BuildCasePlanRequest(topic="C5-6 corpectomy for spondylotic myelopathy"),
        retrievers=CoreRetrieverSet(
            pubmed=FakePubMedRetriever(),
            radiology=FakeRadiologyRetriever(),
            corpus=FakeCorpusRetriever(),
            textbook=textbook,
        ),
    )
    assert textbook.calls, "builder never called the textbook retriever"
    textbook_evidence = [r for r in result.evidence if r.source == "textbook"]
    assert textbook_evidence, "no textbook evidence gathered"
    assert textbook_evidence[0].metadata["axis"] == "Textbook"
    assert textbook_evidence[0].metadata["citation"] == "Benzel Spine, p.592"


@pytest.mark.asyncio
async def test_builder_skips_textbook_when_not_configured():
    result = await build_core_case_plan(
        BuildCasePlanRequest(topic="C5-6 corpectomy for spondylotic myelopathy"),
        retrievers=CoreRetrieverSet(
            pubmed=FakePubMedRetriever(),
            radiology=FakeRadiologyRetriever(),
            corpus=FakeCorpusRetriever(),
        ),
    )
    assert not [r for r in result.evidence if r.source == "textbook"]


@pytest.mark.asyncio
async def test_builder_textbook_failure_becomes_warning_not_crash():
    from caseprep.core import CasePrepExternalServiceError

    class BoomTextbookRetriever:
        def retrieve(self, query, *, subdomain=None, top_n=6):
            raise CasePrepExternalServiceError(
                "textbook-rag CLI not found on PATH",
                details={"provider": "textbook"},
            )

    result = await build_core_case_plan(
        BuildCasePlanRequest(topic="C5-6 corpectomy for spondylotic myelopathy"),
        retrievers=CoreRetrieverSet(
            pubmed=FakePubMedRetriever(),
            radiology=FakeRadiologyRetriever(),
            corpus=FakeCorpusRetriever(),
            textbook=BoomTextbookRetriever(),
        ),
    )
    assert any("Textbook" in w for w in result.warnings)
