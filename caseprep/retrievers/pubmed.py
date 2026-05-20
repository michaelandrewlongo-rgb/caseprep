"""PubMed retriever normalization."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any, Awaitable

from caseprep.core import CasePrepExternalServiceError, EvidenceRecord


PubMedSearch = Callable[
    [str, int, str | None],
    tuple[list[str], int] | Awaitable[tuple[list[str], int]],
]
PubMedSummaries = Callable[
    [list[str]],
    list[dict[str, Any]] | Awaitable[list[dict[str, Any]]],
]
PubMedAbstracts = Callable[
    [list[str]],
    dict[str, str] | Awaitable[dict[str, str]],
]


async def _maybe_await(value):
    if inspect.isawaitable(value):
        return await value
    return value


async def _default_search(
    query: str,
    max_results: int,
    filter_type: str | None,
) -> tuple[list[str], int]:
    from caseprep.mcp_server import _pubmed_search

    return await _pubmed_search(query, max_results, filter_type)


async def _default_summaries(pmids: list[str]) -> list[dict[str, Any]]:
    from caseprep.mcp_server import _pubmed_summaries

    return await _pubmed_summaries(pmids)


async def _default_abstracts(pmids: list[str]) -> dict[str, str]:
    from caseprep.mcp_server import _pubmed_abstracts

    return await _pubmed_abstracts(pmids)


class PubMedRetriever:
    """Normalize PubMed search results into EvidenceRecord objects."""

    def __init__(
        self,
        *,
        search: PubMedSearch | None = None,
        summaries: PubMedSummaries | None = None,
        abstracts: PubMedAbstracts | None = None,
    ) -> None:
        self._search = search or _default_search
        self._summaries = summaries or _default_summaries
        self._abstracts = abstracts or _default_abstracts

    async def retrieve(
        self,
        query: str,
        *,
        max_results: int = 10,
        filter_type: str | None = None,
        include_abstracts: bool = True,
    ) -> list[EvidenceRecord]:
        try:
            pmids, total = await _maybe_await(
                self._search(query, max_results, filter_type)
            )
            articles = await _maybe_await(self._summaries(pmids[:max_results]))
            abstract_by_pmid: dict[str, str] = {}
            if include_abstracts and articles:
                article_pmids = [article.get("pmid", "") for article in articles]
                abstract_by_pmid = await _maybe_await(self._abstracts(article_pmids))
        except Exception as exc:
            raise CasePrepExternalServiceError(
                "PubMed retrieval failed",
                details={"provider": "pubmed", "query": query, "cause": str(exc)},
            ) from exc

        records: list[EvidenceRecord] = []
        for article in articles:
            pmid = str(article.get("pmid") or "")
            if not pmid:
                continue
            metadata = {
                "authors": article.get("authors", ""),
                "journal": article.get("source", ""),
                "pubdate": article.get("pubdate", ""),
                "doi": article.get("doi", ""),
                "total_results": total,
            }
            if article.get("pub_types") is not None:
                metadata["pub_types"] = article["pub_types"]
            records.append(
                EvidenceRecord(
                    id=f"pmid-{pmid}",
                    source="pubmed",
                    title=article.get("title", "") or "",
                    url=article.get("url"),
                    text=abstract_by_pmid.get(pmid, ""),
                    metadata=metadata,
                )
            )
        return records
