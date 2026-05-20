"""FastAPI web dashboard for CasePrep.

Thin HTTP wrapper around the existing MCP handler functions.
All business logic lives in mcp_server.py — this file is just a transport adapter.
"""

from __future__ import annotations

import asyncio
import traceback
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from caseprep.core import BuildCasePlanRequest, CasePlanBuilder
from caseprep.db import CasePrepDB, DEFAULT_DB_PATH
from caseprep.mcp_server import (
    _handle_get_fulltext,
    _handle_pubmed,
    _handle_radiology,
    _handle_generate,
    _handle_pdfs,
    _handle_send_email,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _safe_call(handler, params: dict) -> str:
    """Call a handler and return its text result, or raise HTTPException."""
    try:
        return await handler(params) if asyncio.iscoroutinefunction(handler) else handler(params)
    except Exception as exc:
        tb = traceback.format_exc()
        raise HTTPException(500, f"{type(exc).__name__}: {exc}")


# ── App setup ────────────────────────────────────────────────────────────────
app = FastAPI(
    title="CasePrep",
    description="Neurosurgical case preparation dashboard",
    version="0.1.0",
)

# Static files (frontend)
_STATIC_DIR = Path(__file__).resolve().parent / "static"
if _STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

# Image files served from caseprep output dirs
# We'll handle this with a route instead of a mount (dirs are dynamic)

# DB singleton (lazily initialized per-request via dependency)
_db: CasePrepDB | None = None


def get_db() -> CasePrepDB:
    global _db
    if _db is None:
        _db = CasePrepDB(DEFAULT_DB_PATH)
    return _db


# ── HTML pages ──────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve the main dashboard page."""
    index_path = _STATIC_DIR / "index.html"
    if index_path.exists():
        return index_path.read_text(encoding="utf-8")
    return HTMLResponse("<h1>CasePrep</h1><p>Static frontend not found. Use the API at /docs</p>")


# ── API routes ──────────────────────────────────────────────────────────────

@app.get("/api/caseplans")
async def api_list_caseplans(limit: int = Query(50, ge=1, le=200)):
    """List all saved case plans."""
    db = get_db()
    return db.list_caseplans(limit)


@app.get("/api/caseplans/{slug}")
async def api_get_caseplan(slug: str):
    """Get a case plan with its papers and images."""
    db = get_db()
    plan = db.get_caseplan(slug)
    if not plan:
        raise HTTPException(404, f"Case plan '{slug}' not found")
    plan["papers"] = db.get_papers(plan["id"])
    plan["images"] = db.get_images(plan["id"])
    return plan


@app.post("/api/build")
async def api_build_caseplan(
    topic: str = Query(..., description="Case or procedure topic"),
    max_per_category: int = Query(3, ge=1, le=5),
):
    """Build a full case plan: 4-axis PubMed search + radiology images."""
    db = get_db()
    slug = topic.strip().lower().replace(" ", "-")
    output_dir = str(Path.cwd() / f"{slug}-caseprep")

    request = BuildCasePlanRequest(
        topic=topic,
        output_dir=output_dir,
        max_per_category=max_per_category,
    )
    result_obj = await CasePlanBuilder().build_case_plan(request)
    result = result_obj.markdown

    # Persist the case plan
    cp_id = db.save_caseplan(topic, slug, output_dir, summary=result[:2000])

    # Log the search
    db.log_search(topic, "build_caseplan")

    return {
        "slug": slug,
        "topic": topic,
        "output_dir": output_dir,
        "summary": result,
        "caseplan_id": cp_id,
    }


@app.post("/api/search")
async def api_search_pubmed(
    query: str = Query(..., description="PubMed search query"),
    max_results: int = Query(10, ge=1, le=20),
    filter_type: str | None = Query(None, description="Clinical filter: therapy, prognosis, etiology, diagnosis, systematic_review"),
    include_abstracts: bool = Query(False),
):
    """Search PubMed with optional clinical query filters."""
    db = get_db()
    result = await _safe_call(_handle_pubmed, {
        "query": query,
        "max_results": max_results,
        "filter_type": filter_type,
        "include_abstracts": include_abstracts,
    })
    db.log_search(query, "search_pubmed")
    return {"query": query, "filter": filter_type, "result": result}


@app.post("/api/fulltext")
async def api_get_fulltext(
    pmid: str = Query(..., description="PubMed ID"),
):
    """Fetch best available content for a PMID (3-tier fallback)."""
    result = await _safe_call(_handle_get_fulltext, {"pmid": pmid})
    return {"pmid": pmid, "result": result}


@app.post("/api/radiology")
async def api_search_radiology(
    query: str = Query(..., description="Radiology image search query"),
    max_results: int = Query(5, ge=1, le=10),
    modality: str = Query("any", description="Image modality: any, mri, ct, xray, ultrasound"),
    download_images: bool = Query(True),
):
    """Search Open-i for radiology images with relevance filtering."""
    db = get_db()
    result = await _safe_call(_handle_radiology, {
        "query": query,
        "max_results": max_results,
        "modality": modality,
        "download_images": download_images,
    })
    db.log_search(query, "search_radiology")
    return {"query": query, "modality": modality, "result": result}


@app.post("/api/generate")
async def api_generate_caseprep(
    topic: str = Query(..., description="Case or procedure topic"),
):
    """Generate a blank (fill-in-the-blanks) case prep folder."""
    result = _handle_generate({"topic": topic})
    return {"topic": topic, "result": result}


@app.get("/api/history")
async def api_search_history(limit: int = Query(50, ge=1, le=200)):
    """Get recent search history."""
    db = get_db()
    return db.get_search_history(limit)


@app.get("/api/images/{path:path}")
async def api_serve_image(path: str):
    """Serve a downloaded radiology image by its local path.

    Images are stored under the caseprep output directories.
    The path must be absolute and exist on disk.
    """
    # Security: only serve files that actually exist and look like images
    filepath = Path("/" + path) if not path.startswith("/") else Path(path)
    if not filepath.exists():
        raise HTTPException(404, f"Image not found: {path}")
    if filepath.suffix.lower() not in (".png", ".jpg", ".jpeg", ".gif"):
        raise HTTPException(400, f"Not an image file: {filepath.suffix}")
    return FileResponse(str(filepath))


# ── Health check ────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}
