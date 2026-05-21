"""Tests for PubMed retriever normalization."""

from __future__ import annotations

import pytest

from caseprep.retrievers.pubmed import PubMedRetriever


@pytest.mark.asyncio
async def test_pubmed_retriever_preserves_pmid_in_metadata_for_exact_matching():
    async def search(query, max_results, filter_type):
        return ["25517348"], 1

    async def summaries(pmids):
        return [
            {
                "pmid": "25517348",
                "title": "A Randomized Trial of Intraarterial Treatment for Acute Ischemic Stroke",
                "source": "N Engl J Med",
                "doi": "10.1056/NEJMoa1411587",
                "url": "https://pubmed.ncbi.nlm.nih.gov/25517348/",
            }
        ]

    async def abstracts(pmids):
        return {"25517348": "MR CLEAN abstract."}

    retriever = PubMedRetriever(search=search, summaries=summaries, abstracts=abstracts)

    records = await retriever.retrieve("25517348[PMID]", max_results=1)

    assert len(records) == 1
    assert records[0].id == "pmid-25517348"
    assert records[0].metadata["pmid"] == "25517348"
    assert records[0].metadata["doi"] == "10.1056/NEJMoa1411587"
