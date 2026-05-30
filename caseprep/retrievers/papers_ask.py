"""Retriever over the PAPERS /v1/ask service. Citations only.

Calls the local PAPERS FastAPI RAG service, keeps the citation list (a stable
pointer + bibliographic metadata) and discards the synthesized prose, returning
EvidenceRecords for CasePrep's evidence pipeline. Mirrors SemanticCorpusRetriever:
degrades to [] on any failure so a briefing is never blocked.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Any

import httpx

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


logger = logging.getLogger(__name__)


class PapersAskRetriever:
    """Citations-only retriever over PAPERS /v1/ask. Degrades to [] on any failure."""

    def __init__(self, *, config: PapersAskConfig | None = None) -> None:
        self._cfg = config or PapersAskConfig.from_env()

    def _client_factory(self) -> httpx.Client:
        return httpx.Client(timeout=self._cfg.timeout_s)

    def _login(self, client: httpx.Client) -> bool:
        """Cookie auth: POST /login form; success iff a session cookie is set."""
        try:
            client.post(
                f"{self._cfg.base_url}/login",
                data={"password": self._cfg.password},
                follow_redirects=False,
            )
        except Exception as exc:
            logger.warning("papers_ask: login failed: %s", exc)
            return False
        return "session" in client.cookies

    def retrieve(self, query: str, *, subdomain: str | None = None,
                 top_n: int = 8, hydrate_text=None) -> list[EvidenceRecord]:
        del subdomain  # accepted for protocol symmetry; PAPERS parses its own filters
        cfg = self._cfg
        if not cfg.enabled or not (query or "").strip():
            return []
        payload = {
            "question": query.strip(),
            "max_papers": min(cfg.max_papers, 50),
            "include_figures": False,
            "use_passages": True,
        }
        try:
            with self._client_factory() as client:
                if cfg.auth == "cookie":
                    if not self._login(client):
                        logger.warning("papers_ask: cookie login did not yield a session")
                        return []
                resp = client.post(f"{cfg.base_url}/v1/ask", json=payload)
            if resp.status_code != 200:
                logger.warning("papers_ask: /v1/ask returned %s", resp.status_code)
                return []
            data = resp.json()
        except Exception as exc:  # never block a briefing
            logger.warning("papers_ask: request failed: %s", exc)
            return []

        records: list[EvidenceRecord] = []
        for cit in (data.get("citations") or []):
            rec = citation_to_record(cit)
            if rec is None:
                continue
            rec.metadata.setdefault("text_hydrated", False)
            pmid = rec.metadata.get("pmid")
            if hydrate_text is not None and pmid:
                try:
                    text = hydrate_text(pmid)
                except Exception as exc:
                    logger.warning("papers_ask: hydrate failed for pmid %s: %s", pmid, exc)
                    text = ""
                if text:
                    rec = EvidenceRecord(id=rec.id, source=rec.source, title=rec.title,
                                         url=rec.url, text=text, metadata=rec.metadata)
                    rec.metadata["text_hydrated"] = True
            records.append(rec)
            if len(records) >= top_n:
                break
        return records
