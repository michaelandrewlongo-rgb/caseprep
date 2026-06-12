"""Textbook-RAG retriever: page-grounded passages from the user's textbook
library, via the `textbook-rag search --json` CLI seam."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Callable
from typing import Any

from caseprep.core import CasePrepExternalServiceError, EvidenceRecord

SearchFn = Callable[[str, int], list[dict[str, Any]]]


def _default_search_fn(question: str, k: int) -> list[dict[str, Any]]:
    exe = os.environ.get("TEXTBOOK_RAG_BIN", "textbook-rag")
    if shutil.which(exe) is None:
        raise CasePrepExternalServiceError(
            "textbook-rag CLI not found on PATH",
            details={"provider": "textbook", "bin": exe},
        )
    proc = subprocess.run(
        [exe, "search", question, "--k", str(k)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        raise CasePrepExternalServiceError(
            "textbook-rag search failed",
            details={"provider": "textbook", "stderr": proc.stderr[-500:]},
        )
    return json.loads(proc.stdout or "[]")


def _citation(hit: dict[str, Any]) -> str:
    book = hit.get("book", "")
    folio = hit.get("printed_page")
    if folio:
        return f"{book}, p.{folio}"
    return f"{book}, PDF p.{hit.get('page')}"


class TextbookRetriever:

    """Normalize textbook-rag search hits into EvidenceRecord objects."""

    def __init__(self, *, search_fn: SearchFn | None = None) -> None:
        self._search_fn = search_fn or _default_search_fn

    def retrieve(
        self,
        query: str,
        *,
        subdomain: str | None = None,
        top_n: int = 6,
    ) -> list[EvidenceRecord]:
        try:
            hits = self._search_fn(query, top_n)
        except CasePrepExternalServiceError:
            raise
        except Exception as exc:  # subprocess/JSON/timeout
            raise CasePrepExternalServiceError(
                "Textbook search failed",
                details={"provider": "textbook", "cause": str(exc)},
            ) from exc

        records: list[EvidenceRecord] = []
        for hit in list(hits)[:top_n]:
            book = hit.get("book") or ""
            page = hit.get("page")
            if not book or page is None:
                continue
            metadata: dict[str, Any] = {
                "book": book,
                "chapter": hit.get("chapter") or "",
                "page": page,
                "printed_page": hit.get("printed_page"),
                "score": hit.get("score"),
                "citation": _citation(hit),
                "retrieval_source": "textbook_rag",
            }
            if hit.get("figure_path"):
                metadata["figure_path"] = hit["figure_path"]
                metadata["caption"] = hit.get("caption") or ""
            records.append(
                EvidenceRecord(
                    id=f"textbook-{book}-p{page}",
                    source="textbook",
                    title=f"{book} (p.{hit.get('printed_page') or page})",
                    url=None,
                    text=hit.get("text") or "",
                    metadata=metadata,
                )
            )
        return records
