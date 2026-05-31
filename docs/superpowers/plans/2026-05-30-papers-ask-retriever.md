# PAPERS Ask Retriever Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `PapersAskRetriever` that calls the PAPERS `/v1/ask` service, keeps only its citations, and returns them as `EvidenceRecord`s into CasePrep's existing evidence pipeline — preserving the provenance contract.

**Architecture:** A new retriever mirrors `SemanticCorpusRetriever`: a pure citation→`EvidenceRecord` mapping function, an env-driven config, a pluggable auth strategy (none/cookie), and an httpx client that degrades to `[]` on any failure. It is wired into `CoreRetrieverSet` and invoked beside the other retrievers in `build_core_case_plan`. PMID-bearing citations carry their pointer in metadata so CasePrep's existing fulltext/PubMed path can hydrate evidence text; citations without a stable id are flagged weak-key.

**Tech Stack:** Python 3.12, `httpx` (HTTP + `MockTransport` for tests), `pytest`, dataclasses. Spec: `docs/superpowers/specs/2026-05-30-papers-ask-retriever-design.md`.

---

## File Structure

- **Create** `caseprep/retrievers/papers_ask.py` — config dataclass, auth strategies, mapping function, `PapersAskRetriever`. One file: it's a single cohesive retriever, sized like `corpus_semantic.py`.
- **Modify** `caseprep/core/builder.py` — add `papers_ask` field to `CoreRetrieverSet`, construct it in `default_core_retrievers()`, invoke it in the retrieval section.
- **Create** `tests/test_papers_ask_retriever.py` — unit tests (mapping, degradation, auth, config).
- **Create** `tests/test_papers_ask_wiring.py` — builder-wiring test (record tagged `retrieval_source="papers_ask"`).

Conventions to follow (verified in repo):
- `EvidenceRecord` is `caseprep.core.EvidenceRecord` with fields `id, source, title, url, text, metadata`.
- Retrievers use `httpx`; tests mock via `httpx.Client(transport=httpx.MockTransport(handler))` and `httpx.Response(status, json=...)`.
- The builder invokes `retrieve(query, subdomain=..., top_n=...)`, wraps it in `try/except CasePrepExternalServiceError`, and tags each record's `metadata["retrieval_source"]`.

---

## Task 1: Citation → EvidenceRecord mapping

**Files:**
- Create: `caseprep/retrievers/papers_ask.py`
- Test: `tests/test_papers_ask_retriever.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_papers_ask_retriever.py
from caseprep.core import EvidenceRecord
from caseprep.retrievers.papers_ask import citation_to_record


def test_citation_with_pmid_maps_to_record():
    cit = {
        "citation_number": 1,
        "pmid": "12345678",
        "doi": "10.1/abc",
        "title": "BP targets after thrombectomy",
        "journal": "Stroke",
        "pub_year": 2023,
        "primary_domain": "cerebrovascular",
        "study_type_hint": "rct",
        "evidence_source": "full_text",
        "passage_count": 3,
        "scores": {"rerank": 0.91},
    }
    rec = citation_to_record(cit)
    assert isinstance(rec, EvidenceRecord)
    assert rec.id == "papers-ask-12345678"
    assert rec.source == "papers"
    assert rec.title == "BP targets after thrombectomy"
    assert rec.metadata["pmid"] == "12345678"
    assert rec.metadata["doi"] == "10.1/abc"
    assert rec.metadata["year"] == 2023
    assert rec.metadata["retrieval_source"] == "papers_ask"
    assert rec.metadata["evidence_source"] == "full_text"
    assert rec.metadata["rerank"] == 0.91
    assert rec.metadata["provenance_key"] == "pmid"


def test_citation_without_ids_is_weak_key():
    cit = {
        "citation_number": 2,
        "pmid": "",
        "doi": "",
        "title": "Some OpenAlex-only work",
        "journal": "J Neurosurg",
        "pub_year": 2021,
        "primary_domain": "cerebrovascular",
        "study_type_hint": "cohort",
    }
    rec = citation_to_record(cit)
    assert rec.id == "papers-ask-some-openalex-only-work-2021"
    assert rec.metadata["provenance_key"] == "title_year_weak"
    assert rec.metadata["pmid"] == ""


def test_citation_missing_title_returns_none():
    assert citation_to_record({"pmid": "", "doi": "", "title": ""}) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_papers_ask_retriever.py -v`
Expected: FAIL with `ImportError: cannot import name 'citation_to_record'`

- [ ] **Step 3: Write minimal implementation**

```python
# caseprep/retrievers/papers_ask.py
"""Retriever over the PAPERS /v1/ask service. Citations only.

Calls the local PAPERS FastAPI RAG service, keeps the citation list (a stable
pointer + bibliographic metadata) and discards the synthesized prose, returning
EvidenceRecords for CasePrep's evidence pipeline. Mirrors SemanticCorpusRetriever:
degrades to [] on any failure so a briefing is never blocked.
"""
from __future__ import annotations

import re
from typing import Any

from caseprep.core import EvidenceRecord


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
        "passage_count": cit.get("passage_count", 0),
        "rerank": scores.get("rerank"),
    }
    return EvidenceRecord(id=rec_id, source="papers", title=title, text=text, metadata=metadata)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_papers_ask_retriever.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add caseprep/retrievers/papers_ask.py tests/test_papers_ask_retriever.py
git commit -m "feat(papers-ask): citation -> EvidenceRecord mapping with weak-key flag"
```

---

## Task 2: Config from environment

**Files:**
- Modify: `caseprep/retrievers/papers_ask.py`
- Test: `tests/test_papers_ask_retriever.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_papers_ask_retriever.py
from caseprep.retrievers.papers_ask import PapersAskConfig


def test_config_defaults_disabled(monkeypatch):
    for k in ("CASEPREP_PAPERS_ENABLED", "CASEPREP_PAPERS_BASE_URL",
              "CASEPREP_PAPERS_AUTH", "CASEPREP_PAPERS_MAX_PAPERS",
              "CASEPREP_PAPERS_TIMEOUT_S", "CASEPREP_PAPERS_PASSWORD"):
        monkeypatch.delenv(k, raising=False)
    cfg = PapersAskConfig.from_env()
    assert cfg.enabled is False
    assert cfg.base_url == "http://127.0.0.1:8000"
    assert cfg.auth == "none"
    assert cfg.max_papers == 8
    assert cfg.timeout_s == 60


def test_config_reads_env(monkeypatch):
    monkeypatch.setenv("CASEPREP_PAPERS_ENABLED", "1")
    monkeypatch.setenv("CASEPREP_PAPERS_BASE_URL", "http://host:9000/")
    monkeypatch.setenv("CASEPREP_PAPERS_AUTH", "cookie")
    monkeypatch.setenv("CASEPREP_PAPERS_PASSWORD", "neuro")
    monkeypatch.setenv("CASEPREP_PAPERS_MAX_PAPERS", "5")
    cfg = PapersAskConfig.from_env()
    assert cfg.enabled is True
    assert cfg.base_url == "http://host:9000"  # trailing slash stripped
    assert cfg.auth == "cookie"
    assert cfg.password == "neuro"
    assert cfg.max_papers == 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_papers_ask_retriever.py -k config -v`
Expected: FAIL with `ImportError: cannot import name 'PapersAskConfig'`

- [ ] **Step 3: Write minimal implementation**

```python
# add to caseprep/retrievers/papers_ask.py (after imports)
import os
from dataclasses import dataclass

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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_papers_ask_retriever.py -k config -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add caseprep/retrievers/papers_ask.py tests/test_papers_ask_retriever.py
git commit -m "feat(papers-ask): env-driven config (off by default)"
```

---

## Task 3: Retriever happy path (httpx, citations only)

**Files:**
- Modify: `caseprep/retrievers/papers_ask.py`
- Test: `tests/test_papers_ask_retriever.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_papers_ask_retriever.py
import httpx
from caseprep.retrievers.papers_ask import PapersAskRetriever


def _retriever(monkeypatch, handler, **cfg_over):
    cfg = PapersAskConfig(enabled=True, **cfg_over)
    r = PapersAskRetriever(config=cfg)
    monkeypatch.setattr(r, "_client_factory",
                        lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    return r


def test_retrieve_keeps_citations_discards_answer(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/ask"
        assert request.method == "POST"
        return httpx.Response(200, json={
            "answer": "Synthesized prose we must discard.",
            "citations": [
                {"citation_number": 1, "pmid": "111", "doi": "", "title": "Paper A",
                 "journal": "Stroke", "pub_year": 2022, "primary_domain": "cerebrovascular",
                 "study_type_hint": "rct", "evidence_source": "full_text",
                 "passage_count": 2, "scores": {"rerank": 0.8}},
                {"citation_number": 2, "pmid": "222", "doi": "", "title": "Paper B",
                 "journal": "JNS", "pub_year": 2020, "primary_domain": "cerebrovascular",
                 "study_type_hint": "cohort", "evidence_source": "abstract_only",
                 "passage_count": 0, "scores": {}},
            ],
        })
    r = _retriever(monkeypatch, handler)
    recs = r.retrieve("bp targets after thrombectomy", top_n=5)
    assert [x.metadata["pmid"] for x in recs] == ["111", "222"]
    assert all(x.source == "papers" for x in recs)
    assert all("Synthesized" not in x.text for x in recs)


def test_retrieve_respects_top_n(monkeypatch):
    def handler(request):
        return httpx.Response(200, json={"citations": [
            {"pmid": str(i), "title": f"P{i}", "pub_year": 2020} for i in range(10)
        ]})
    r = _retriever(monkeypatch, handler)
    assert len(r.retrieve("q", top_n=3)) == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_papers_ask_retriever.py -k "keeps_citations or respects_top_n" -v`
Expected: FAIL with `ImportError: cannot import name 'PapersAskRetriever'`

- [ ] **Step 3: Write minimal implementation**

```python
# add to caseprep/retrievers/papers_ask.py
import logging

import httpx

logger = logging.getLogger(__name__)


class PapersAskRetriever:
    """Citations-only retriever over PAPERS /v1/ask. Degrades to [] on any failure."""

    def __init__(self, *, config: PapersAskConfig | None = None) -> None:
        self._cfg = config or PapersAskConfig.from_env()

    def _client_factory(self) -> httpx.Client:
        return httpx.Client(timeout=self._cfg.timeout_s)

    def retrieve(self, query: str, *, subdomain: str | None = None,
                 top_n: int = 8) -> list[EvidenceRecord]:
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
            if rec is not None:
                records.append(rec)
            if len(records) >= top_n:
                break
        return records
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_papers_ask_retriever.py -k "keeps_citations or respects_top_n" -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add caseprep/retrievers/papers_ask.py tests/test_papers_ask_retriever.py
git commit -m "feat(papers-ask): httpx retriever, citations-only, top_n cap"
```

---

## Task 4: Graceful degradation

**Files:**
- Test: `tests/test_papers_ask_retriever.py` (no impl change expected — verifies Task 3's guards)

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_papers_ask_retriever.py
def test_disabled_returns_empty(monkeypatch):
    def handler(request):  # should never be called
        raise AssertionError("network touched while disabled")
    cfg = PapersAskConfig(enabled=False)
    r = PapersAskRetriever(config=cfg)
    monkeypatch.setattr(r, "_client_factory",
                        lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    assert r.retrieve("q") == []


def test_401_returns_empty(monkeypatch):
    r = _retriever(monkeypatch, lambda req: httpx.Response(401, json={"error": "auth"}))
    assert r.retrieve("q") == []


def test_429_returns_empty(monkeypatch):
    r = _retriever(monkeypatch, lambda req: httpx.Response(429, json={"error": "rate"}))
    assert r.retrieve("q") == []


def test_connect_error_returns_empty(monkeypatch):
    def handler(request):
        raise httpx.ConnectError("refused")
    r = _retriever(monkeypatch, handler)
    assert r.retrieve("q") == []


def test_empty_query_returns_empty(monkeypatch):
    r = _retriever(monkeypatch, lambda req: httpx.Response(200, json={"citations": []}))
    assert r.retrieve("   ") == []
```

- [ ] **Step 2: Run test to verify it fails (or passes)**

Run: `pytest tests/test_papers_ask_retriever.py -k "empty or error or disabled or 401 or 429" -v`
Expected: PASS — Task 3 already implements every guard. If any FAIL, fix `retrieve()` to satisfy it (do not weaken the test).

- [ ] **Step 3: (only if a test failed) adjust implementation**

No change expected. If `test_empty_query_returns_empty` failed, confirm the `not (query or "").strip()` guard exists in `retrieve()`.

- [ ] **Step 4: Run the full unit suite**

Run: `pytest tests/test_papers_ask_retriever.py -v`
Expected: PASS (all tasks 1–4 tests)

- [ ] **Step 5: Commit**

```bash
git add tests/test_papers_ask_retriever.py
git commit -m "test(papers-ask): graceful degradation (disabled/401/429/connect/empty)"
```

---

## Task 5: Cookie auth strategy

**Files:**
- Modify: `caseprep/retrievers/papers_ask.py`
- Test: `tests/test_papers_ask_retriever.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_papers_ask_retriever.py
def test_cookie_auth_logs_in_before_ask(monkeypatch):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/login":
            return httpx.Response(302, headers={"set-cookie": "session=abc; Path=/"})
        if request.url.path == "/v1/ask":
            assert "session=abc" in request.headers.get("cookie", "")
            return httpx.Response(200, json={"citations": [
                {"pmid": "1", "title": "P", "pub_year": 2020}]})
        return httpx.Response(404)

    r = _retriever(monkeypatch, handler, auth="cookie", password="neuro")
    recs = r.retrieve("q")
    assert "/login" in calls and "/login" == calls[0]
    assert [x.metadata["pmid"] for x in recs] == ["1"]


def test_cookie_login_failure_returns_empty(monkeypatch):
    def handler(request):
        if request.url.path == "/login":
            return httpx.Response(200)  # HTML re-render = wrong password, no cookie
        raise AssertionError("must not call /v1/ask without a session cookie")
    r = _retriever(monkeypatch, handler, auth="cookie", password="wrong")
    assert r.retrieve("q") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_papers_ask_retriever.py -k cookie -v`
Expected: FAIL (no login is performed; `/v1/ask` called without cookie, or assertion trips)

- [ ] **Step 3: Write minimal implementation**

Replace `retrieve()`'s request block to log in first when `auth == "cookie"`, reusing one client (so the cookie jar persists), and treat a missing `session` cookie as failure:

```python
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
                 top_n: int = 8) -> list[EvidenceRecord]:
        del subdomain
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
        except Exception as exc:
            logger.warning("papers_ask: request failed: %s", exc)
            return []

        records: list[EvidenceRecord] = []
        for cit in (data.get("citations") or []):
            rec = citation_to_record(cit)
            if rec is not None:
                records.append(rec)
            if len(records) >= top_n:
                break
        return records
```

Note: `with self._client_factory() as client` must wrap both the login and the ask call so the cookie jar persists across them (single client).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_papers_ask_retriever.py -k cookie -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Run full unit suite + commit**

Run: `pytest tests/test_papers_ask_retriever.py -v`
Expected: PASS (all)

```bash
git add caseprep/retrievers/papers_ask.py tests/test_papers_ask_retriever.py
git commit -m "feat(papers-ask): cookie-session auth strategy"
```

---

## Task 6: Wire into the core builder

**Files:**
- Modify: `caseprep/core/builder.py` (import ~L39; `CoreRetrieverSet` ~L95-106; `default_core_retrievers()` ~L240-247; retrieval section ~L1147-1166)
- Test: `tests/test_papers_ask_wiring.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_papers_ask_wiring.py
import asyncio

from caseprep.core import EvidenceRecord
from caseprep.core.builder import CoreRetrieverSet, default_core_retrievers


class _StubPapers:
    def retrieve(self, query, *, subdomain=None, top_n=8):
        return [EvidenceRecord(id="papers-ask-1", source="papers", title="P",
                               text="P", metadata={})]


def test_retriever_set_accepts_papers_ask():
    s = CoreRetrieverSet(
        pubmed=object(), radiology=object(), corpus=object(),
        corpus_semantic=None, papers_ask=_StubPapers(),
    )
    assert s.papers_ask is not None


def test_default_set_includes_papers_ask():
    s = default_core_retrievers()
    assert hasattr(s, "papers_ask")
    # off by default → constructed but disabled; presence is what we assert here
    assert s.papers_ask is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_papers_ask_wiring.py -v`
Expected: FAIL with `TypeError: __init__() got an unexpected keyword argument 'papers_ask'`

- [ ] **Step 3: Write minimal implementation**

In `caseprep/core/builder.py`:

(a) Add the import near the other retriever imports (~L39):
```python
from caseprep.retrievers.papers_ask import PapersAskRetriever
```

(b) Add the field to `CoreRetrieverSet` (after `corpus_semantic`, ~L105):
```python
    papers_ask: CorpusRetrieverProtocol | None = None
```

(c) Construct it in `default_core_retrievers()` (~L240-247):
```python
    return CoreRetrieverSet(
        pubmed=PubMedRetriever(),
        radiology=RadiologyRetriever(),
        corpus=CorpusRetriever(),
        corpus_semantic=SemanticCorpusRetriever(),
        papers_ask=PapersAskRetriever(),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_papers_ask_wiring.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add caseprep/core/builder.py tests/test_papers_ask_wiring.py
git commit -m "feat(papers-ask): add to CoreRetrieverSet + defaults"
```

---

## Task 7: Invoke papers_ask during retrieval

**Files:**
- Modify: `caseprep/core/builder.py` (retrieval section, immediately after the `corpus_semantic` block ~L1166)
- Test: `tests/test_papers_ask_wiring.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_papers_ask_wiring.py
import inspect

from caseprep.core import builder as builder_mod


def test_builder_invokes_papers_ask_and_tags_source():
    """The retrieval body must call provider_set.papers_ask.retrieve and tag
    records with retrieval_source='papers_ask' (mirrors the corpus_semantic block)."""
    src = inspect.getsource(builder_mod)
    assert "provider_set.papers_ask" in src
    assert '"papers_ask"' in src or "'papers_ask'" in src
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_papers_ask_wiring.py -k invokes -v`
Expected: FAIL — `provider_set.papers_ask` not yet referenced in builder.

- [ ] **Step 3: Write minimal implementation**

In `caseprep/core/builder.py`, immediately **after** the `corpus_semantic` block
(the one ending at the `)` that closes `evidence.extend(_tag_evidence(...))`,
~L1178) and **before** the `evidence = dedupe_evidence(evidence)` line at L1180,
add a parallel block. It mirrors the semantic block exactly — same `_maybe_await`,
same `_tag_evidence(...)` call, same `except CasePrepError` (NOT
`CasePrepExternalServiceError` — that name is not used in this module), reusing
the existing `semantic_top_n`, `semantic_query`, `corpus_subdomain`,
`query_case_spec`, `retrieval_family`, `evidence`, and `warnings` locals:

```python
    papers_used = False
    if provider_set.papers_ask is not None:
        papers_used = True
        try:
            papers_records = await _maybe_await(
                provider_set.papers_ask.retrieve(
                    semantic_query,
                    subdomain=corpus_subdomain,
                    top_n=semantic_top_n,
                )
            )
        except CasePrepError as exc:
            warnings.append(f"PAPERS ask: {exc}")
        else:
            papers_records = list(papers_records)[:semantic_top_n]
            evidence.extend(
                _tag_evidence(
                    papers_records,
                    axis="PAPERS ask",
                    query=semantic_query,
                    case_spec=query_case_spec,
                    family=retrieval_family,
                    procedure_family=retrieval_family.id if retrieval_family else None,
                    broad_profile=(
                        retrieval_family.broad_profile
                        if retrieval_family
                        else query_case_spec.broad_profile.value
                    ),
                    retrieval_source="papers_ask",
                )
            )
```

This places `papers_ask` results into the same `evidence` list that
`dedupe_evidence(evidence)` (the very next line, L1180) processes — so dedup
against PubMed/corpus by PMID happens for free. `_tag_evidence` sets
`metadata["retrieval_source"]="papers_ask"`, satisfying the Step-1 test.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_papers_ask_wiring.py -k invokes -v`
Expected: PASS

- [ ] **Step 5: Run the broad builder suite to confirm no regression**

Run: `pytest tests/test_core_builder.py tests/test_core_engine.py tests/test_papers_ask_wiring.py -v`
Expected: PASS (papers_ask is off by default → `retrieve()` returns `[]`, so existing builder behavior is unchanged). If `test_core_builder.py` constructs `CoreRetrieverSet(...)` positionally or with a fixture that doesn't pass `papers_ask`, the new field's `= None` default keeps it green; do not change those tests.

- [ ] **Step 6: Commit**

```bash
git add caseprep/core/builder.py tests/test_papers_ask_wiring.py
git commit -m "feat(papers-ask): invoke retriever in core build, tag retrieval_source"
```

---

## Task 8: PMID text hydration

**Files:**
- Modify: `caseprep/retrievers/papers_ask.py`
- Test: `tests/test_papers_ask_retriever.py`

**Why:** `PaperCitation` carries no abstract/passage text, but CasePrep's auditor verifies claims against `EvidenceRecord.text`. PAPERS gives the *pointer* (PMID); CasePrep already knows how to fetch the *text*. This task adds an optional, injectable hydrator hook so a PMID-bearing record's `text` can be filled by the existing PubMed/fulltext path. Weak-key records (no pmid/doi) are left thin and flagged.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_papers_ask_retriever.py
def test_hydrate_fills_text_for_pmid_records(monkeypatch):
    def handler(request):
        return httpx.Response(200, json={"citations": [
            {"pmid": "555", "title": "Hydratable", "pub_year": 2021},
            {"pmid": "", "doi": "", "title": "WeakKey", "pub_year": 2019},
        ]})

    def fake_hydrator(pmid: str) -> str:
        return f"ABSTRACT for {pmid}" if pmid == "555" else ""

    r = _retriever(monkeypatch, handler)
    recs = r.retrieve("q", hydrate_text=fake_hydrator)
    by_id = {x.metadata.get("pmid"): x for x in recs}
    assert by_id["555"].text == "ABSTRACT for 555"
    assert by_id["555"].metadata["text_hydrated"] is True
    # weak-key record left thin, not hydrated
    weak = [x for x in recs if x.metadata["provenance_key"] == "title_year_weak"][0]
    assert weak.metadata.get("text_hydrated") is False


def test_hydrate_absent_leaves_text_unchanged(monkeypatch):
    r = _retriever(monkeypatch, lambda req: httpx.Response(200, json={"citations": [
        {"pmid": "9", "title": "T", "pub_year": 2020}]}))
    recs = r.retrieve("q")  # no hydrator passed
    assert recs[0].text == "T"
    assert recs[0].metadata["text_hydrated"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_papers_ask_retriever.py -k hydrate -v`
Expected: FAIL — `retrieve()` has no `hydrate_text` parameter.

- [ ] **Step 3: Write minimal implementation**

Add a `hydrate_text` callable parameter to `retrieve()` and apply it after building each record:

```python
    def retrieve(self, query: str, *, subdomain: str | None = None,
                 top_n: int = 8,
                 hydrate_text=None) -> list[EvidenceRecord]:
```

In the record-building loop, after `rec = citation_to_record(cit)` and the `None` check:

```python
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
```

(Keep the `len(records) >= top_n` break after the append.)

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_papers_ask_retriever.py -k hydrate -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Run the full retriever suite + commit**

Run: `pytest tests/test_papers_ask_retriever.py -v`
Expected: PASS (all)

```bash
git add caseprep/retrievers/papers_ask.py tests/test_papers_ask_retriever.py
git commit -m "feat(papers-ask): optional PMID text hydration hook"
```

---

## Task 9: Full-suite regression + docs note

**Files:**
- Modify: `README.md` (retriever/integration note, if a retriever list exists there)

- [ ] **Step 1: Run the whole test suite**

Run: `pytest -q`
Expected: PASS — same pass count as before plus the new `test_papers_ask_*` tests; no regressions (papers_ask is off by default).

- [ ] **Step 2: Confirm off-by-default behavior end to end**

Run: `python -c "from caseprep.retrievers.papers_ask import PapersAskRetriever; print(PapersAskRetriever().retrieve('thrombectomy bp targets'))"`
Expected: `[]` (disabled unless `CASEPREP_PAPERS_ENABLED=1`).

- [ ] **Step 3: Add a short README note** (only if README documents retrievers/integrations)

Add under the corpus/retrieval section:
```markdown
- **PAPERS `/v1/ask` retriever** (opt-in, `CASEPREP_PAPERS_ENABLED=1`): pulls cited
  evidence from the local PAPERS corpus service; citations-only, PMID-hydrated,
  degrades to no-op when the service is unreachable. See
  `docs/superpowers/specs/2026-05-30-papers-ask-retriever-design.md`.
```

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs(papers-ask): README note for opt-in PAPERS retriever"
```

---

## Deferred / dependencies (not in this plan)

- **Live validation** against a real `/v1/ask` (needs PAPERS container recreated with `ASK_PUBLIC_API_ENABLED=1` via `docker compose up -d --force-recreate api`). Once live: capture one real response as a JSON fixture and add a gated integration test; measure PMID coverage.
- **PAPERS `work_id` exposure** on `PaperCitation` (closes the weak-key gap, spec §9) — a PAPERS-side change, tracked separately.
- **Wiring the hydrator** to CasePrep's concrete PubMed/fulltext fetch at the builder call site — Task 8 ships the injectable hook; binding it to the real fetch function is a focused follow-up once live citations confirm the PMID shape.
