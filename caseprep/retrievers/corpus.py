"""Local corpus retriever normalization."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from caseprep.core import CasePrepExternalServiceError, EvidenceRecord


CorpusSearch = Callable[[str, str | None, int], dict[str, Any]]


def _default_search_corpus(
    fts_query: str,
    subdomain: str | None = None,
    top_n: int = 8,
) -> dict[str, Any]:
    from caseprep.mcp_server import _corpus_search

    return _corpus_search(fts_query, subdomain, top_n)


class CorpusRetriever:
    """Normalize local corpus search results into EvidenceRecord objects."""

    def __init__(self, *, search_corpus: CorpusSearch | None = None) -> None:
        self._search_corpus = search_corpus or _default_search_corpus

    def retrieve(
        self,
        fts_query: str,
        *,
        subdomain: str | None = None,
        top_n: int = 8,
    ) -> list[EvidenceRecord]:
        try:
            result = self._search_corpus(fts_query, subdomain, top_n)
        except Exception as exc:
            raise CasePrepExternalServiceError(
                "Corpus search failed",
                details={"provider": "corpus", "cause": str(exc)},
            ) from exc

        if result.get("error"):
            raise CasePrepExternalServiceError(
                str(result["error"]),
                details={"provider": "corpus", "query": fts_query},
            )

        total_matches = result.get("total_matches", 0)
        records: list[EvidenceRecord] = []
        for paper in result.get("papers", []):
            work_id = str(paper.get("work_id") or paper.get("id") or "")
            if not work_id:
                continue
            text_parts = [
                part
                for part in (paper.get("abstract"), paper.get("conclusion"))
                if part
            ]
            metadata = {
                key: value
                for key, value in paper.items()
                if key not in {"abstract", "conclusion", "title"}
            }
            metadata["total_matches"] = total_matches
            records.append(
                EvidenceRecord(
                    id=f"corpus-{work_id}",
                    source="corpus",
                    title=paper.get("title", "") or "",
                    url=paper.get("pubmed_url") or paper.get("doi_url"),
                    text="\n\n".join(text_parts),
                    metadata=metadata,
                )
            )
        return records
