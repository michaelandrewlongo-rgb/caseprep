"""Tests for normalized evidence retrievers."""

from __future__ import annotations

import pytest

from caseprep.core import CasePrepConfigurationError, CasePrepExternalServiceError
from caseprep.retrievers import resolve_retrievers_v2_enabled
from caseprep.retrievers.corpus import CorpusRetriever
from caseprep.retrievers.pubmed import PubMedRetriever
from caseprep.retrievers.radiology import RadiologyRetriever


def test_resolve_retrievers_v2_defaults_to_disabled(monkeypatch):
    monkeypatch.delenv("CASEPREP_RETRIEVERS_V2", raising=False)

    assert resolve_retrievers_v2_enabled() is False


def test_resolve_retrievers_v2_accepts_enabled(monkeypatch):
    monkeypatch.setenv("CASEPREP_RETRIEVERS_V2", "1")

    assert resolve_retrievers_v2_enabled() is True


def test_resolve_retrievers_v2_rejects_unknown_value(monkeypatch):
    monkeypatch.setenv("CASEPREP_RETRIEVERS_V2", "yes")

    with pytest.raises(CasePrepConfigurationError) as exc:
        resolve_retrievers_v2_enabled()

    assert exc.value.details["field"] == "CASEPREP_RETRIEVERS_V2"


@pytest.mark.asyncio
async def test_pubmed_retriever_normalizes_articles_to_evidence_records():
    async def search(query, max_results, filter_type):
        assert query == "vestibular schwannoma"
        assert max_results == 2
        assert filter_type == "therapy"
        return ["12345"], 8

    async def summaries(pmids):
        assert pmids == ["12345"]
        return [
            {
                "pmid": "12345",
                "title": "Surgery Outcomes",
                "authors": "Doe J",
                "source": "J Neurosurg",
                "pubdate": "2024",
                "url": "https://pubmed.ncbi.nlm.nih.gov/12345/",
                "doi": "10.1000/test",
            }
        ]

    async def abstracts(pmids):
        assert pmids == ["12345"]
        return {"12345": "Outcome abstract."}

    retriever = PubMedRetriever(
        search=search,
        summaries=summaries,
        abstracts=abstracts,
    )

    records = await retriever.retrieve(
        "vestibular schwannoma",
        max_results=2,
        filter_type="therapy",
        include_abstracts=True,
    )

    assert len(records) == 1
    assert records[0].id == "pmid-12345"
    assert records[0].source == "pubmed"
    assert records[0].title == "Surgery Outcomes"
    assert records[0].url == "https://pubmed.ncbi.nlm.nih.gov/12345/"
    assert records[0].text == "Outcome abstract."
    assert records[0].metadata["total_results"] == 8
    assert records[0].metadata["doi"] == "10.1000/test"


@pytest.mark.asyncio
async def test_pubmed_retriever_raises_domain_error_for_provider_failure():
    async def search(query, max_results, filter_type):
        raise RuntimeError("NCBI timeout")

    retriever = PubMedRetriever(search=search)

    with pytest.raises(CasePrepExternalServiceError) as exc:
        await retriever.retrieve("aneurysm")

    assert exc.value.details["provider"] == "pubmed"


@pytest.mark.asyncio
async def test_radiology_retriever_normalizes_images_to_evidence_records():
    async def search_images(query, max_results, modality, query_terms=None):
        assert query_terms == ["schwannoma", "mri"]
        return [
            {
                "uid": "img1",
                "title": "CPA MRI",
                "caption": "Axial MRI showing CPA tumor.",
                "img_large": "https://openi.nlm.nih.gov/img1.png",
                "pubmed_url": "https://pubmed.ncbi.nlm.nih.gov/12345/",
                "pmid": "12345",
                "journal": "AJNR",
            }
        ], 4

    retriever = RadiologyRetriever(
        search_images=search_images,
        query_terms=lambda query: ["schwannoma", "mri"],
    )

    records = await retriever.retrieve("schwannoma mri", max_results=1, modality="mri")

    assert records[0].id == "openi-img1"
    assert records[0].source == "openi"
    assert records[0].title == "CPA MRI"
    assert records[0].url == "https://openi.nlm.nih.gov/img1.png"
    assert records[0].text == "Axial MRI showing CPA tumor."
    assert records[0].metadata["pmid"] == "12345"
    assert records[0].metadata["total_results"] == 4


def test_corpus_retriever_normalizes_local_papers_to_evidence_records():
    def search_corpus(fts_query, subdomain=None, top_n=8):
        assert fts_query == "aneurysm"
        assert subdomain == "aneurysm_sah"
        assert top_n == 1
        return {
            "total_matches": 12,
            "papers": [
                {
                    "work_id": "W123",
                    "title": "Aneurysm Outcomes",
                    "abstract": "Treatment outcomes.",
                    "conclusion": "Clipping remains durable.",
                    "pubmed_url": "https://pubmed.ncbi.nlm.nih.gov/1/",
                    "evidence_tier": "observational",
                }
            ],
        }

    retriever = CorpusRetriever(search_corpus=search_corpus)

    records = retriever.retrieve("aneurysm", subdomain="aneurysm_sah", top_n=1)

    assert records[0].id == "corpus-W123"
    assert records[0].source == "corpus"
    assert records[0].title == "Aneurysm Outcomes"
    assert records[0].text == "Treatment outcomes.\n\nClipping remains durable."
    assert records[0].metadata["total_matches"] == 12
    assert records[0].metadata["evidence_tier"] == "observational"


def test_corpus_retriever_raises_domain_error_for_provider_error():
    retriever = CorpusRetriever(
        search_corpus=lambda fts_query, subdomain=None, top_n=8: {
            "error": "Local corpus not available",
            "papers": [],
            "total_matches": 0,
        }
    )

    with pytest.raises(CasePrepExternalServiceError) as exc:
        retriever.retrieve("aneurysm")

    assert exc.value.details["provider"] == "corpus"
