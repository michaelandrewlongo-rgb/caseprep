"""Retriever over the PAPERS /v1/ask service. Citations only.

Calls the local PAPERS FastAPI RAG service, keeps the citation list (a stable
pointer + bibliographic metadata) and discards the synthesized prose, returning
EvidenceRecords for CasePrep's evidence pipeline. Mirrors SemanticCorpusRetriever:
degrades to [] on any failure so a briefing is never blocked.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any

from caseprep.core import EvidenceRecord


_TRUE = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class PapersAskConfig:
    enabled: bool = False
    base_url: str = "http://127.0.0.1:8000"
    auth: str = "none"          # "none" | "cookie"
    password: str = ""
    max_papers: int = 8
    timeout_s: int = 60

    @classmethod
    def from_env(cls) -> "PapersAskConfig":
        def _int(name: str, default: int) -> int:
            try:
                return int(os.environ.get(name, "") or default)
            except ValueError:
                return default
        return cls(
            enabled=(os.environ.get("CASEPREP_PAPERS_ENABLED", "").strip().lower() in _TRUE),
            base_url=(os.environ.get("CASEPREP_PAPERS_BASE_URL") or "http://127.0.0.1:8000").rstrip("/"),
            auth=(os.environ.get("CASEPREP_PAPERS_AUTH") or "none").strip().lower(),
            password=os.environ.get("CASEPREP_PAPERS_PASSWORD") or "",
            max_papers=_int("CASEPREP_PAPERS_MAX_PAPERS", 8),
            timeout_s=_int("CASEPREP_PAPERS_TIMEOUT_S", 60),
        )


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s[:60] or "untitled"


def citation_to_record(cit: dict[str, Any]) -> EvidenceRecord | None:
    """Map one PAPERS PaperCitation dict to an EvidenceRecord, or None if unusable."""
    title = str(cit.get("title") or "").strip()
    pmid = str(cit.get("pmid") or "").strip()
    doi = str(cit.get("doi") or "").strip()
    if not title and not pmid and not doi:
        return None

    if pmid:
        rec_id, prov_key = f"papers-ask-{pmid}", "pmid"
    elif doi:
        rec_id, prov_key = f"papers-ask-{_slug(doi)}", "doi"
    else:
        year = cit.get("pub_year")
        rec_id = f"papers-ask-{_slug(title)}-{year}" if year else f"papers-ask-{_slug(title)}"
        prov_key = "title_year_weak"

    journal = str(cit.get("journal") or "").strip()
    year = cit.get("pub_year")
    text = title
    if journal or year:
        text = f"{title} ({journal}{', ' if journal and year else ''}{year or ''})".strip()

    scores = cit.get("scores") or {}
    metadata: dict[str, Any] = {
        "retrieval_source": "papers_ask",
        "provenance_key": prov_key,
        "pmid": pmid,
        "doi": doi,
        "year": year,
        "journal": journal,
        "primary_domain": str(cit.get("primary_domain") or ""),
        "study_type_hint": str(cit.get("study_type_hint") or ""),
        "evidence_source": str(cit.get("evidence_source") or ""),
        "passage_count": int(cit.get("passage_count") or 0),
        "rerank": scores.get("rerank"),
    }
    return EvidenceRecord(id=rec_id, source="papers", title=title, text=text, metadata=metadata)
