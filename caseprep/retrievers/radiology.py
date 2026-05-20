"""Open-i radiology retriever normalization."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any, Awaitable

from caseprep.core import CasePrepExternalServiceError, EvidenceRecord


RadiologySearch = Callable[
    [str, int, str | None, list[str] | None],
    tuple[list[dict[str, Any]], int] | Awaitable[tuple[list[dict[str, Any]], int]],
]
QueryTerms = Callable[[str], list[str]]


async def _maybe_await(value):
    if inspect.isawaitable(value):
        return await value
    return value


async def _default_search_images(
    query: str,
    max_results: int,
    modality: str | None,
    query_terms: list[str] | None = None,
) -> tuple[list[dict[str, Any]], int]:
    from caseprep.mcp_server import _openi_search

    return await _openi_search(
        query,
        max_results=max_results,
        modality=modality,
        query_terms=query_terms,
    )


def _default_query_terms(query: str) -> list[str]:
    from caseprep.mcp_server import _query_terms

    return _query_terms(query)


class RadiologyRetriever:
    """Normalize Open-i image search results into EvidenceRecord objects."""

    def __init__(
        self,
        *,
        search_images: RadiologySearch | None = None,
        query_terms: QueryTerms | None = None,
    ) -> None:
        self._search_images = search_images or _default_search_images
        self._query_terms = query_terms or _default_query_terms

    async def retrieve(
        self,
        query: str,
        *,
        max_results: int = 5,
        modality: str | None = None,
    ) -> list[EvidenceRecord]:
        terms = self._query_terms(query)
        try:
            images, total = await _maybe_await(
                self._search_images(query, max_results, modality, terms)
            )
        except Exception as exc:
            raise CasePrepExternalServiceError(
                "Radiology retrieval failed",
                details={"provider": "openi", "query": query, "cause": str(exc)},
            ) from exc

        records: list[EvidenceRecord] = []
        for image in images:
            uid = str(image.get("uid") or "")
            if not uid:
                continue
            image_url = (
                image.get("img_large")
                or image.get("img_grid")
                or image.get("img_thumb")
                or image.get("pubmed_url")
            )
            metadata = {
                key: value
                for key, value in image.items()
                if key not in {"title", "caption"}
            }
            metadata["total_results"] = total
            records.append(
                EvidenceRecord(
                    id=f"openi-{uid}",
                    source="openi",
                    title=image.get("title", "") or "",
                    url=image_url,
                    text=image.get("caption", "") or "",
                    metadata=metadata,
                )
            )
        return records
