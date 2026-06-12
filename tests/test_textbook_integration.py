"""End-to-end: CASEPREP_TEXTBOOK=1 + a fake textbook-rag CLI on the real
default search path (subprocess -> JSON -> EvidenceRecord -> builder)."""

from __future__ import annotations

import pytest

from caseprep.core import BuildCasePlanRequest
from caseprep.core.builder import CoreRetrieverSet, build_core_case_plan
from caseprep.retrievers import resolve_textbook_enabled
from caseprep.retrievers.textbook import TextbookRetriever

FAKE_JSON = (
    '[{"book":"Benzel Spine","chapter":"Cervical","page":726,'
    '"printed_page":"592","text":"corpectomy failure rates",'
    '"score":0.9,"figure_path":"/figs/p0726.png","caption":"Fig 69-3"}]'
)


class EmptyPubMedRetriever:
    async def retrieve(self, query, *, max_results=10, filter_type=None,
                       include_abstracts=True):
        return []


class EmptyRadiologyRetriever:
    async def retrieve(self, query, *, max_results=5, modality=None):
        return []


class EmptyCorpusRetriever:
    def retrieve(self, fts_query, *, subdomain=None, top_n=8):
        return []


@pytest.mark.asyncio
async def test_textbook_evidence_end_to_end(tmp_path, monkeypatch):
    fake = tmp_path / "textbook-rag"
    fake.write_text(f"#!/usr/bin/env bash\necho '{FAKE_JSON}'\n")
    fake.chmod(0o755)
    monkeypatch.setenv("CASEPREP_TEXTBOOK", "1")
    monkeypatch.setenv("TEXTBOOK_RAG_BIN", str(fake))

    assert resolve_textbook_enabled() is True
    result = await build_core_case_plan(
        BuildCasePlanRequest(topic="C5-6 corpectomy for spondylotic myelopathy"),
        retrievers=CoreRetrieverSet(
            pubmed=EmptyPubMedRetriever(),
            radiology=EmptyRadiologyRetriever(),
            corpus=EmptyCorpusRetriever(),
            textbook=TextbookRetriever(),  # real subprocess path via fake bin
        ),
    )
    textbook_evidence = [r for r in result.evidence if r.source == "textbook"]
    assert textbook_evidence
    assert "p." in textbook_evidence[0].metadata["citation"]
    assert textbook_evidence[0].metadata["citation"].endswith("p.592")
    assert textbook_evidence[0].metadata["figure_path"] == "/figs/p0726.png"
