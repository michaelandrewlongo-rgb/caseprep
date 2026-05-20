"""Tests for the CasePrep web layer (FastAPI + DB)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from caseprep.db import CasePrepDB
from caseprep.web import app, get_db


# ── Fixtures ────────────────────────────────────────────────────────────────

class ASGISyncClient:
    """Small sync wrapper around httpx.ASGITransport for FastAPI tests."""

    def __init__(self, app):
        self.app = app

    def get(self, url: str, **kwargs) -> httpx.Response:
        return self._request("GET", url, **kwargs)

    def post(self, url: str, **kwargs) -> httpx.Response:
        return self._request("POST", url, **kwargs)

    def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        import asyncio

        async def send_request() -> httpx.Response:
            transport = httpx.ASGITransport(app=self.app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
            ) as async_client:
                return await async_client.request(method, url, **kwargs)

        return asyncio.run(send_request())


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temp DB, populate it, and wire it into the app."""
    db = CasePrepDB(tmp_path / "test.db")

    # Seed a case plan + paper + image
    cp_id = db.save_caseplan("vestibular schwannoma", "vestibular-schwannoma", "/tmp/vs-caseprep")
    db.save_paper(
        "12345", cp_id,
        title="Schwannoma Outcomes Study",
        authors="Doe J et al",
        source="J Neurosurg",
        pubdate="2024",
        abstract="Retrospective review of 200 patients.",
        tier="structured",
        search_axis="outcomes",
    )
    db.save_paper(
        "67890", cp_id,
        title="MRI Findings in CPA Tumors",
        authors="Smith A et al",
        tier="plain",
        search_axis="technique",
        structured={"BACKGROUND": "CPA tumors", "RESULTS": "T2 hyperintensity"},
    )
    db.save_image(
        "img001", cp_id,
        title="CPA MRI Axial",
        caption="T1-weighted axial MRI showing CPA mass",
        journal="Radiopaedia",
        local_path=str(tmp_path / "images" / "01.png"),
    )
    db.log_search("vestibular schwannoma", "search_pubmed", 10)
    db.log_search("vestibular schwannoma", "build_caseplan", 1)

    yield db

    db.close()


@pytest.fixture
def client(tmp_db):
    """Sync ASGI client wired to the FastAPI app with our test DB."""
    import caseprep.web as web_mod
    web_mod._db = tmp_db  # set the module-level singleton

    tc = ASGISyncClient(app)
    yield tc

    web_mod._db = None


# ── Health ──────────────────────────────────────────────────────────────────

def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["version"] == "0.1.0"


# ── Case plans ──────────────────────────────────────────────────────────────

def test_list_caseplans(client):
    resp = client.get("/api/caseplans")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert data[0]["slug"] == "vestibular-schwannoma"
    assert data[0]["topic"] == "vestibular schwannoma"


def test_get_caseplan_detail(client):
    resp = client.get("/api/caseplans/vestibular-schwannoma")
    assert resp.status_code == 200
    data = resp.json()
    assert data["topic"] == "vestibular schwannoma"
    assert len(data["papers"]) == 2
    assert len(data["images"]) == 1

    # Check structured abstract deserialized
    mri_paper = [p for p in data["papers"] if p["pmid"] == "67890"][0]
    assert mri_paper["structured"]["BACKGROUND"] == "CPA tumors"
    assert mri_paper["structured"]["RESULTS"] == "T2 hyperintensity"


def test_get_caseplan_404(client):
    resp = client.get("/api/caseplans/nonexistent")
    assert resp.status_code == 404


# ── Search history ──────────────────────────────────────────────────────────

def test_search_history(client):
    resp = client.get("/api/history")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["query"] == "vestibular schwannoma"


# ── Frontend ────────────────────────────────────────────────────────────────

def test_index_page(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "CasePrep" in resp.text
    assert "dashboard" in resp.text.lower()


# ── API endpoints that call external services (mocked) ──────────────────────

def test_search_pubmed_mocked(client):
    with patch("caseprep.web._handle_pubmed", new_callable=AsyncMock) as mock:
        mock.return_value = "Found 10 results for vestibular schwannoma"
        resp = client.post("/api/search?query=vestibular+schwannoma&include_abstracts=true")
        assert resp.status_code == 200
        data = resp.json()
        assert data["result"] == "Found 10 results for vestibular schwannoma"
        mock.assert_called_once()


def test_search_radiology_mocked(client):
    with patch("caseprep.web._handle_radiology", new_callable=AsyncMock) as mock:
        mock.return_value = "Found 5 radiology images"
        resp = client.post("/api/radiology?query=schwannoma+MRI&modality=mri")
        assert resp.status_code == 200
        data = resp.json()
        assert data["result"] == "Found 5 radiology images"
        mock.assert_called_once()


def test_get_fulltext_mocked(client):
    with patch("caseprep.web._handle_get_fulltext", new_callable=AsyncMock) as mock:
        mock.return_value = "Full text content for PMID 12345"
        resp = client.post("/api/fulltext?pmid=12345")
        assert resp.status_code == 200
        data = resp.json()
        assert data["result"] == "Full text content for PMID 12345"


def test_build_caseplan_mocked(client):
    from caseprep.core import BuildCasePlanResult

    seen_requests = []

    class FakeBuilder:
        async def build_case_plan(self, request):
            seen_requests.append(request)
            return BuildCasePlanResult(
                topic=request.topic,
                markdown=(
                    "## Case Plan\n\n"
                    "Outcomes: 3 papers found\n\n"
                    "---\n"
                    "Case plan written to /tmp/vestibular-schwannoma-caseprep/\n"
                    "Canonical files: caseprep.yaml, 01-case-summary.md"
                ),
                output_dir=request.resolved_output_dir(),
                mode="legacy",
            )

    with patch("caseprep.web.CasePlanBuilder", FakeBuilder):
        resp = client.post("/api/build?topic=vestibular+schwannoma")
        assert resp.status_code == 200
        data = resp.json()
        assert data["slug"] == "vestibular-schwannoma"
        assert "Case Plan" in data["summary"]
        assert data["output_dir"].endswith("vestibular-schwannoma-caseprep")
        assert "caseprep.yaml" in data["summary"]
        assert seen_requests[0].topic == "vestibular schwannoma"
        assert seen_requests[0].max_per_category == 3


# ── DB persistence after API calls ──────────────────────────────────────────

def test_search_persists_to_history(client, tmp_db):
    with patch("caseprep.web._handle_pubmed", new_callable=AsyncMock) as mock:
        mock.return_value = "Results"
        client.post("/api/search?query=meningioma")
    history = tmp_db.get_search_history()
    # Should now have 3 entries (2 seed + 1 new)
    assert len(history) == 3
    assert any(h["query"] == "meningioma" for h in history)


# ── Image serving ──────────────────────────────────────────────────────────

def test_image_serve_404(client):
    resp = client.get("/api/images/nonexistent/path.png")
    assert resp.status_code == 404


# ── OpenAPI docs ────────────────────────────────────────────────────────────

def test_openapi_docs(client):
    resp = client.get("/docs")
    assert resp.status_code == 200
