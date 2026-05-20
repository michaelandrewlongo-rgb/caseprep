"""MCP server for caseprep — PubMed-powered case preparation.

Tools:
  search_pubmed      — search with clinical query filters, optional abstracts
  build_caseplan     — run 5 targeted searches, pull abstracts, write filled-in templates
  generate_caseprep  — static template folder (quick scaffold)
  search_local_pdfs  — PyMuPDF local PDF search
  get_fulltext       — 3-tier best-available content for a PMID
  search_radiology   — search Open-i for radiology images (MRI, CT, X-ray)
  send_email         — send email via Resend REST API
"""

from __future__ import annotations

import asyncio
import os
import re
import sqlite3
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from caseprep.generator import generate_caseprep as _generate_caseprep
from caseprep.knowledge_graph import build_enriched_query
from caseprep.links import build_search_links
from caseprep.pdfs import format_pdf_results, search_local_pdfs as _search_local_pdfs
from caseprep.schema import (
    build_caseprep_schema,
    build_caseprep_schema_from_axis_data,
    render_caseprep_files,
)
from caseprep.scoring import (
    EvidenceGrade,
    classify_study_type,
    extract_n_value,
    grade_evidence,
    neurosurg_relevance_score,
)

# ── Load .env file ───────────────────────────────────────────────────────────

import os
from pathlib import Path as _Path

_ENV_FILE = _Path(__file__).resolve().parent.parent / ".env"
if _ENV_FILE.exists():
    with open(_ENV_FILE) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _key, _val = _line.split("=", 1)
                os.environ.setdefault(_key.strip(), _val.strip())

# Also load Hermes .env as fallback (for OPENROUTER_API_KEY etc.)
_HERMES_ENV = _Path.home() / ".hermes" / ".env"
if _HERMES_ENV.exists():
    with open(_HERMES_ENV) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _key, _val = _line.split("=", 1)
                os.environ.setdefault(_key.strip(), _val.strip())

# ── NCBI API key ────────────────────────────────────────────────────────────

_NCBI_API_KEY = os.environ.get("NCBI_API_KEY", "").strip()
_DELAY = 0.15 if _NCBI_API_KEY else 0.6  # 10/sec with key, ~1.5/sec without

# ── Resend email API ─────────────────────────────────────────────────────────

_RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "").strip()
RESEND_API = "https://api.resend.com"
RESEND_DEFAULT_FROM = "CasePrep <onboarding@resend.dev>"

# ── HTTP client ─────────────────────────────────────────────────────────────

_http: httpx.AsyncClient | None = None

def _client() -> httpx.AsyncClient:
    global _http
    if _http is None:
        _http = httpx.AsyncClient(
            timeout=httpx.Timeout(45.0),
            headers={"User-Agent": "caseprep-mcp/0.2 (hermes-agent)"},
        )
    return _http

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
OPENI = "https://openi.nlm.nih.gov/api"

# ── Local corpus (NSGY_DB_lean) ─────────────────────────────────────────────

_CORPUS_DB = os.environ.get(
    "CASEPREP_CORPUS_DB",
    "/mnt/c/dev/NSGY_DB_lean/corpus/neurointerventional.sqlite",
)
_FULLTEXT_DB = os.environ.get(
    "CASEPREP_FULLTEXT_DB",
    "/mnt/c/dev/NSGY_DB_lean/fulltext/neurointerventional_fulltext.sqlite",
)

_CORPUS_AVAILABLE = Path(_CORPUS_DB).exists() and Path(_FULLTEXT_DB).exists()

# Subdomain descriptions (mirrors neurointerventional_mcp)
SUBDOMAIN_DESCRIPTIONS: dict[str, str] = {
    "stroke_thrombectomy": "Acute ischemic stroke, mechanical thrombectomy, LVO, thrombolysis",
    "aneurysm_sah": "Intracranial aneurysm, subarachnoid hemorrhage, coiling, clipping, vasospasm",
    "avm_vascular_malformation": "AVM, dAVF, cavernous malformations, vein of Galen",
    "carotid_cervical_vascular": "Carotid stenosis/stenting, CEA, vertebral artery, extracranial vascular",
    "intracranial_hemorrhage": "ICH, subdural hematoma, MMA embolization, intracerebral hemorrhage",
    "flow_diversion": "Flow diverters (Pipeline, FRED, Surpass), WEB device, intrasaccular",
    "venous_interventional": "Venous sinus stenting, IIH, cerebral venous thrombosis",
    "moyamoya": "Moyamoya disease, EC-IC bypass, cerebral revascularization",
    "intracranial_atherosclerosis": "ICAD, intracranial stenting, Wingspan, basilar stenosis",
    "radiosurgery": "Gamma Knife, stereotactic radiosurgery, LINAC",
    "tumor_skull_base": "Tumor embolization, meningioma, GBM, skull base",
    "spine_interventional": "Vertebroplasty, kyphoplasty, spinal AVM/dAVF",
    "neurocritical_care": "ICP, decompressive craniectomy, TBI, brain death",
    "functional_epilepsy": "Epilepsy surgery, Wada test, SEEG, DBS, VNS",
    "pediatric_neurointerventional": "Pediatric neurointerventional procedures",
    "cerebrovascular_other": "CNS vasculitis, hydrocephalus, vessel wall imaging",
    "general_neurointerventional": "Cross-cutting technique/access papers, general endovascular",
}

EVIDENCE_TIER_LABELS: dict[str, str] = {
    "guideline": "Level 1 — Guideline",
    "meta_analysis": "Level 1 — Meta-Analysis",
    "RCT": "Level 2 — Randomized Controlled Trial",
    "observational": "Level 3 — Observational Study",
    "case_report": "Level 5 — Case Report / Series",
    "narrative_review": "Level 5 — Narrative Review",
    "technical_note": "Level 5 — Technical Note",
}

# ── Open-i radiology image type codes ────────────────────────────────────────
# Codes are loosely tagged; prefer "x" (general radiology) as default.
OPENI_MODALITY: dict[str, str] = {
    "any": "x",         # all radiology (MRI/CT/X-ray/ultrasound)
    "mri": "m",         # MRI
    "ct": "c",          # CT
    "xray": "x",        # general x-ray / radiology
    "ultrasound": "u",  # ultrasound
    "graph": "g",       # charts / graphs (non-radiology fallback)
}

STOP_WORDS: set[str] = {
    "and", "or", "not", "the", "a", "an", "in", "of", "for",
    "with", "to", "from", "by", "on", "at", "is", "are",
    "was", "were", "be", "been", "being",
}


def _query_terms(query: str) -> list[str]:
    """Extract meaningful search terms from a query string.

    Splits on whitespace, punctuation, and hyphens; removes stop words
    and tokens shorter than 2 chars. Each term is lowercased and deduplicated.
    """
    tokens = re.split(r'[\s,"\':;()\[\]{}-]+', query.lower())
    seen: set[str] = set()
    terms: list[str] = []
    for t in tokens:
        t = t.strip(".")
        if len(t) >= 2 and t not in STOP_WORDS and t not in seen:
            seen.add(t)
            terms.append(t)
    return terms


# ── Clinical query filters (PubMed syntax) ──────────────────────────────────

CLINICAL_FILTERS: dict[str, str] = {
    "therapy": (
        " AND (clinical trial[pt] OR randomized controlled trial[pt] "
        "OR comparative study[pt] OR multicenter study[pt])"
    ),
    "prognosis": (
        " AND (prognosis[MeSH] OR survival analysis[MeSH] "
        "OR mortality[MeSH] OR follow-up studies[MeSH] OR outcome*[tiab])"
    ),
    "etiology": (
        " AND (risk[MeSH] OR cohort studies[MeSH] OR case-control studies[MeSH] "
        "OR retrospective studies[MeSH] OR complications[sh])"
    ),
    "diagnosis": (
        " AND (sensitivity and specificity[MeSH] OR diagnosis[sh] "
        "OR diagnostic imaging[MeSH] OR diagnostic use[sh])"
    ),
    "systematic_review": (
        " AND (systematic review[pt] OR meta-analysis[pt] "
        "OR systematic review[tiab] OR meta-analysis[tiab])"
    ),
}


def _apply_filter(query: str, filter_type: str | None) -> str:
    """Append a clinical query filter to the PubMed query string."""
    ft = (filter_type or "").strip().lower()
    if ft in CLINICAL_FILTERS:
        return query + CLINICAL_FILTERS[ft]
    return query


# ── Rate limiter (NCBI: 3 req/sec without API key) ───────────────────────────

_last_request: float = 0.0


async def _rate_limit():
    """Enforce delay between NCBI requests."""
    global _last_request
    now = time.monotonic()
    wait = _last_request + _DELAY - now
    if wait > 0:
        await asyncio.sleep(wait)
    _last_request = time.monotonic()


async def _ncbi_get(url: str, params: dict) -> httpx.Response:
    """GET with API key injection, rate limiting, and retry on 429."""
    if _NCBI_API_KEY:
        params["api_key"] = _NCBI_API_KEY
    for attempt in range(3):
        await _rate_limit()
        resp = await _client().get(url, params=params)
        if resp.status_code == 429 and attempt < 2:
            await asyncio.sleep(2.0 * (attempt + 1))
            continue
        resp.raise_for_status()
        return resp
    raise RuntimeError("NCBI rate limit exceeded after retries")


# ── PubMed API helpers ──────────────────────────────────────────────────────

async def _pubmed_search(
    query: str,
    max_results: int = 10,
    filter_type: str | None = None,
) -> list[str]:
    """Return PMIDs matching *query*, optionally filtered by clinical type."""
    term = _apply_filter(query, filter_type)
    params = {
        "db": "pubmed",
        "term": term,
        "retmax": str(max_results),
        "retmode": "xml",
        "sort": "relevance",
    }
    resp = await _ncbi_get(f"{EUTILS}/esearch.fcgi", params)
    root = ET.fromstring(resp.text)
    total = root.findtext(".//Count") or "0"
    pmids = [e.text or "" for e in root.findall(".//Id") if e.text]
    # Attach total count as a pseudo-attribute on first element
    return pmids, int(total)


async def _pubmed_summaries(pmids: list[str]) -> list[dict]:
    """Fetch structured summaries (title, authors, journal, etc.) for PMIDs."""
    if not pmids:
        return []
    params = {"db": "pubmed", "id": ",".join(pmids), "retmode": "json"}
    resp = await _ncbi_get(f"{EUTILS}/esummary.fcgi", params)
    data = resp.json()
    results = []
    for pmid in pmids:
        a = data.get("result", {}).get(pmid, {})
        if not a or "uid" not in a:
            continue
        pub_types = a.get("pubtype", [])
        if isinstance(pub_types, str):
            pub_types = [pub_types]
        results.append({
            "pmid": a.get("uid", ""),
            "title": a.get("title", ""),
            "authors": _fmt_authors(a.get("authors", [])),
            "source": a.get("source", ""),
            "pubdate": a.get("pubdate", ""),
            "pub_types": pub_types,
            "doi": a.get("elocationid", "").replace("doi: ", "")
                   if a.get("elocationid", "") else "",
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{a.get('uid', '')}/",
        })
    return results


async def _pubmed_abstracts(pmids: list[str]) -> dict[str, str]:
    """Fetch plain-text abstracts for PMIDs. Returns dict[pmid → abstract_text]."""
    if not pmids:
        return {}
    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "xml",
        "rettype": "abstract",
    }
    resp = await _ncbi_get(f"{EUTILS}/efetch.fcgi", params)
    root = ET.fromstring(resp.text)
    abstracts = {}
    for article in root.findall(".//PubmedArticle"):
        pmid_el = article.find(".//PMID")
        abstract_el = article.find(".//Abstract/AbstractText")
        pmid = pmid_el.text if pmid_el is not None else ""
        text = abstract_el.text if abstract_el is not None else ""
        if pmid and text:
            abstracts[pmid] = text
    return abstracts


async def _pubmed_structured_abstracts(pmids: list[str]) -> dict[str, dict[str, str]]:
    """Fetch structured abstracts with labeled sections for PMIDs.

    Returns dict[pmid → {label: text}] where labels are BACKGROUND, METHODS,
    RESULTS, CONCLUSIONS, or empty string for unlabeled paragraphs.
    Works for JAMA, NEJM, Lancet, Neurology — even without PMC access.
    """
    if not pmids:
        return {}
    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "xml",
        "rettype": "abstract",
    }
    resp = await _ncbi_get(f"{EUTILS}/efetch.fcgi", params)
    root = ET.fromstring(resp.text)
    results: dict[str, dict[str, str]] = {}
    for article in root.findall(".//PubmedArticle"):
        pmid_el = article.find(".//PMID")
        pmid = pmid_el.text if pmid_el is not None else ""
        if not pmid:
            continue
        sections: dict[str, str] = {}
        for at in article.findall(".//Abstract/AbstractText"):
            label = (at.get("Label") or "").upper().rstrip(":")
            text = at.text or ""
            # Also collect text from child elements (some abstracts have inline markup)
            for child in at:
                if child.text:
                    text += child.text
                if child.tail:
                    text += child.tail
            if text.strip():
                key = label if label else "TEXT"
                sections[key] = sections.get(key, "") + text.strip() + " "
        if sections:
            results[pmid] = {k: v.strip() for k, v in sections.items()}
    return results


async def _pubmed_fulltext(pmids: list[str]) -> dict[str, str]:
    """Fetch PMC full text via curl subprocess with retry.

    Three attempts per article, exponential backoff, ."""
    if not pmids:
        return {}
    # Step 1: get PMCIDs via elink
    params = {
        "dbfrom": "pubmed", "db": "pmc", "id": ",".join(pmids),
        "retmode": "xml", "linkname": "pubmed_pmc",
    }
    try:
        resp = await _ncbi_get(f"{EUTILS}/elink.fcgi", params)
        root = ET.fromstring(resp.text)
    except Exception:
        return {}
    pmid_to_pmcid: dict[str, str] = {}
    for link_set in root.findall(".//LinkSet"):
        pmid_el = link_set.find(".//Id")
        if pmid_el is None or not pmid_el.text:
            continue
        for link in link_set.findall(".//Link/Id"):
            if link.text:
                link_id = link.text
                if not link_id.startswith("PMC"):
                    link_id = "PMC" + link_id
                pmid_to_pmcid[pmid_el.text] = link_id
                break
    if not pmid_to_pmcid:
        return {}
    # Step 2: fetch via curl with retry
    fulltexts: dict[str, str] = {}
    api_key_param = f"&api_key={_NCBI_API_KEY}" if _NCBI_API_KEY else ""
    for pmid, pmcid in pmid_to_pmcid.items():
        url = f"{EUTILS}/efetch.fcgi?db=pmc&id={pmcid}&retmode=xml{api_key_param}"
        for attempt in range(3):
            proc = await asyncio.create_subprocess_exec(
                "curl", "-sS", "--max-time", "45", "--retry", "2", url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            if proc.returncode != 0 or not stdout:
                if attempt < 2:
                    await asyncio.sleep(1.5 * (attempt + 1))
                continue
            try:
                root = ET.fromstring(stdout.decode("utf-8", errors="replace"))
                for article in root.findall(".//article"):
                    body = article.find(".//body")
                    if body is not None:
                        text = ET.tostring(body, encoding="unicode", method="text")
                        # Clean excessive whitespace
                        text = " ".join(text.split())
                        fulltexts[pmid] = text[:5000]
                        break
                break  # success, stop retrying
            except ET.ParseError:
                if attempt < 2:
                    await asyncio.sleep(1.5 * (attempt + 1))
                continue
    return fulltexts


# ── Local corpus search (FTS5) ─────────────────────────────────────────────


def _corpus_conn() -> sqlite3.Connection:
    """Open corpus DB with fulltext attached (read-only)."""
    conn = sqlite3.connect(f"file:{_CORPUS_DB}?mode=ro", uri=True)
    conn.execute("ATTACH DATABASE ? AS ft", (f"file:{_FULLTEXT_DB}?mode=ro",))
    conn.row_factory = sqlite3.Row
    return conn


def _corpus_list_subdomains() -> list[dict]:
    """Return subdomain IDs with paper counts and descriptions."""
    if not _CORPUS_AVAILABLE:
        return []
    conn = _corpus_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT subdomain_id, COUNT(DISTINCT work_id) AS n
        FROM subdomain_assignments
        GROUP BY subdomain_id ORDER BY n DESC
    """)
    rows = cur.fetchall()
    conn.close()
    return [
        {
            "id": r["subdomain_id"],
            "paper_count": r["n"],
            "description": SUBDOMAIN_DESCRIPTIONS.get(r["subdomain_id"], ""),
        }
        for r in rows
    ]


def _corpus_search(
    fts_query: str,
    subdomain: str | None = None,
    top_n: int = 8,
) -> dict:
    """FTS5 search over the local neurointerventional corpus.

    Returns ranked papers with metadata, abstract, and conclusion passages.
    """
    if not _CORPUS_AVAILABLE:
        return {"error": "Local corpus not available", "papers": [], "total_matches": 0}

    top_n = min(max(top_n, 1), 25)
    conn = _corpus_conn()
    try:
        cur = conn.cursor()

        # Ranked FTS5 search with optional subdomain filter
        if subdomain:
            cur.execute("""
                SELECT DISTINCT w.id, bm25(works_fts) AS rank
                FROM works_fts
                JOIN works w ON w.rowid = works_fts.rowid
                JOIN subdomain_assignments sa ON sa.work_id = w.id
                WHERE works_fts MATCH ? AND sa.subdomain_id = ?
                ORDER BY rank LIMIT ?
            """, (fts_query, subdomain, top_n))
        else:
            cur.execute("""
                SELECT w.id, bm25(works_fts) AS rank
                FROM works_fts
                JOIN works w ON w.rowid = works_fts.rowid
                WHERE works_fts MATCH ?
                ORDER BY rank LIMIT ?
            """, (fts_query, top_n))
        top_ids = [(r["id"], r["rank"]) for r in cur.fetchall()]

        # Total match count + subdomain distribution
        if subdomain:
            cur.execute("""
                SELECT COUNT(DISTINCT w.id) FROM works_fts
                JOIN works w ON w.rowid = works_fts.rowid
                JOIN subdomain_assignments sa ON sa.work_id = w.id
                WHERE works_fts MATCH ? AND sa.subdomain_id = ?
            """, (fts_query, subdomain))
            total = cur.fetchone()[0]
            subdomain_dist = {subdomain: total}
        else:
            cur.execute("SELECT COUNT(*) FROM works_fts WHERE works_fts MATCH ?", (fts_query,))
            total = cur.fetchone()[0]
            cur.execute("""
                SELECT sa.subdomain_id, COUNT(DISTINCT w.id) AS n
                FROM works_fts
                JOIN works w ON w.rowid = works_fts.rowid
                JOIN subdomain_assignments sa ON sa.work_id = w.id
                WHERE works_fts MATCH ?
                GROUP BY sa.subdomain_id ORDER BY n DESC
            """, (fts_query,))
            subdomain_dist = {r["subdomain_id"]: r["n"] for r in cur.fetchall()}

        papers = []
        for wid, rank in top_ids:
            cur.execute("""
                SELECT w.title, w.pub_year, w.study_design, w.evidence_tier,
                       w.citation_count, w.article_type, j.title AS journal,
                       (SELECT value FROM identifiers WHERE work_id=w.id AND scheme='pmid' LIMIT 1) AS pmid,
                       (SELECT value FROM identifiers WHERE work_id=w.id AND scheme='doi' LIMIT 1) AS doi
                FROM works w
                LEFT JOIN journals j ON w.journal_id = j.id
                WHERE w.id = ?
            """, (wid,))
            meta = cur.fetchone()
            if not meta:
                continue

            # Abstract from fulltext DB
            cur.execute("SELECT abstract FROM ft.works WHERE id = ?", (wid,))
            ft_row = cur.fetchone()
            abstract = ft_row["abstract"] if ft_row and ft_row["abstract"] else None

            # Conclusion passages from fulltext
            cur.execute("""
                SELECT content FROM ft.text_passages
                WHERE work_id = ? AND section_type = 'conclusion'
                ORDER BY sequence_number
            """, (wid,))
            conclusion_parts = [r["content"] for r in cur.fetchall()]
            conclusion = " ".join(conclusion_parts) if conclusion_parts else None

            # Subdomain tags
            cur.execute(
                "SELECT DISTINCT subdomain_id FROM subdomain_assignments WHERE work_id = ?",
                (wid,),
            )
            subdomains = [r["subdomain_id"] for r in cur.fetchall()]

            papers.append({
                "work_id": wid,
                "rank": rank,
                "title": meta["title"],
                "year": meta["pub_year"],
                "journal": meta["journal"],
                "study_design": meta["study_design"],
                "evidence_tier": meta["evidence_tier"],
                "article_type": meta["article_type"],
                "citation_count": meta["citation_count"],
                "subdomains": subdomains,
                "pmid": meta["pmid"],
                "doi": meta["doi"],
                "pubmed_url": f"https://pubmed.ncbi.nlm.nih.gov/{meta['pmid']}/" if meta["pmid"] else None,
                "doi_url": f"https://doi.org/{meta['doi']}" if meta["doi"] else None,
                "abstract": abstract,
                "conclusion": conclusion,
            })

        return {
            "fts_query": fts_query,
            "subdomain": subdomain,
            "total_matches": total,
            "returned": len(papers),
            "subdomain_distribution": subdomain_dist,
            "papers": papers,
        }
    except sqlite3.OperationalError as exc:
        return {
            "error": f"Invalid FTS query: {exc}",
            "papers": [],
            "total_matches": 0,
        }
    finally:
        conn.close()


def _corpus_get_paper(work_id: str) -> dict | None:
    """Retrieve full paper details including all section passages."""
    if not _CORPUS_AVAILABLE:
        return None
    conn = _corpus_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT w.id, w.title, w.pub_year, w.study_design, w.evidence_tier,
               w.citation_count, w.language, w.tier, j.title AS journal,
               (SELECT value FROM identifiers WHERE work_id=w.id AND scheme='pmid' LIMIT 1) AS pmid,
               (SELECT value FROM identifiers WHERE work_id=w.id AND scheme='doi' LIMIT 1) AS doi
        FROM works w
        LEFT JOIN journals j ON w.journal_id = j.id
        WHERE w.id = ?
    """, (work_id,))
    meta = cur.fetchone()
    if not meta:
        conn.close()
        return None

    # Abstract
    cur.execute("SELECT abstract FROM ft.works WHERE id = ?", (work_id,))
    ft_row = cur.fetchone()
    abstract = ft_row["abstract"] if ft_row and ft_row["abstract"] else None

    # All section passages
    from collections import defaultdict
    cur.execute("""
        SELECT section_type, content, sequence_number
        FROM ft.text_passages WHERE work_id = ?
        ORDER BY section_type, sequence_number
    """, (work_id,))
    sections = defaultdict(list)
    for r in cur.fetchall():
        sections[r["section_type"]].append(r["content"])
    sections_out = {k: " ".join(v) for k, v in sections.items()}

    # Subdomains
    cur.execute(
        "SELECT DISTINCT subdomain_id FROM subdomain_assignments WHERE work_id = ?",
        (work_id,),
    )
    subdomains = [r["subdomain_id"] for r in cur.fetchall()]

    # MeSH + keywords
    cur.execute("""
        SELECT s.scheme, s.value FROM work_subjects ws
        JOIN subjects s ON ws.subject_id = s.id WHERE ws.work_id = ?
    """, (work_id,))
    mesh, keywords = [], []
    for r in cur.fetchall():
        (mesh if r["scheme"] == "mesh" else keywords).append(r["value"])

    conn.close()
    return {
        "work_id": meta["id"],
        "title": meta["title"],
        "year": meta["pub_year"],
        "journal": meta["journal"],
        "language": meta["language"],
        "study_design": meta["study_design"],
        "evidence_tier": meta["evidence_tier"],
        "journal_tier": meta["tier"],
        "citation_count": meta["citation_count"],
        "subdomains": subdomains,
        "mesh_terms": mesh,
        "keywords": keywords,
        "pmid": meta["pmid"],
        "doi": meta["doi"],
        "pubmed_url": f"https://pubmed.ncbi.nlm.nih.gov/{meta['pmid']}/" if meta["pmid"] else None,
        "doi_url": f"https://doi.org/{meta['doi']}" if meta["doi"] else None,
        "abstract": abstract,
        "sections": sections_out,
    }


# ── Open-i radiology image search ────────────────────────────────────────────

async def _openi_search(
    query: str,
    max_results: int = 5,
    modality: str | None = None,
    query_terms: list[str] | None = None,
) -> tuple[list[dict], int]:
    """Search Open-i for radiology images. Returns (results, total_count).

    Each result: uid, pmid, pmcid, title, journal, authors, pubdate,
    caption (cleaned), img_thumb, img_large, img_grid, pmc_url, pubmed_url,
    article_type.

    If *query_terms* is provided, results are post-filtered — only images
    whose title or caption contains at least one query term are returned.
    Fetches more results from Open-i (up to 20) to compensate for filtering.
    """
    it_code = OPENI_MODALITY.get((modality or "").strip().lower(), "x")
    # Fetch more from Open-i to compensate for post-filtering
    fetch_n = min(max(max_results * 4, 10), 20)
    params = {
        "query": query,
        "it": it_code,
        "m": 1,
        "n": str(fetch_n),
    }
    try:
        resp = await _client().get(f"{OPENI}/search", params=params)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        msg = str(exc)[:200]
        print(f"  [Open-i API error: {msg}]", file=__import__("sys").stderr)
        return [], 0

    total = int(data.get("total", 0))
    results: list[dict] = []
    for item in data.get("list", []):
        img = item.get("image", {})
        caption_raw = img.get("caption", "")
        # Strip HTML bold tags from captions
        caption_clean = caption_raw.replace("<b>", "").replace("</b>", "").replace("\\/", "/")
        title = item.get("title", "")

        # Post-filter by relevance: require title or caption to contain a query term
        if query_terms:
            title_lower = title.lower()
            caption_lower = caption_clean.lower()
            if not any(
                term in title_lower or term in caption_lower
                for term in query_terms
            ):
                continue

        journal_date = item.get("journal_date", {})
        pubdate = f"{journal_date.get('year','')}-{journal_date.get('month','')}-{journal_date.get('day','')}"
        pubdate = pubdate.strip("-")
        # Image URLs are top-level fields on the item (not inside 'image' dict)
        thumb = item.get("imgThumb", "") or ""
        large = item.get("imgLarge", "") or ""
        grid = item.get("imgGrid150", "") or ""
        results.append({
            "uid": item.get("uid", ""),
            "pmid": item.get("pmid", ""),
            "pmcid": item.get("pmcid", ""),
            "title": title,
            "journal": item.get("journal_title", "") or item.get("journal_abbr", ""),
            "authors": item.get("authors", ""),
            "pubdate": pubdate,
            "caption": caption_clean,
            "img_thumb": f"https://openi.nlm.nih.gov{thumb}" if thumb else "",
            "img_large": f"https://openi.nlm.nih.gov{large}" if large else "",
            "img_grid": f"https://openi.nlm.nih.gov{grid}" if grid else "",
            "pmc_url": item.get("pmc_url", ""),
            "pubmed_url": item.get("pubMed_url", ""),
            "article_type": item.get("articleType", ""),
        })
        if len(results) >= max_results:
            break
    return results, total


async def _download_images(
    results: list[dict],
    output_dir: Path,
    max_images: int = 5,
) -> list[dict]:
    """Download radiology images from Open-i and add local_path to each result.

    Tries img_large first, falls back to img_grid, then img_thumb.
    Saves files as <nn>_<uid>.<ext> in *output_dir*.
    Errors are captured in local_path as "Error: …" strings.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    for i, r in enumerate(results[:max_images]):
        img_url = r["img_large"] or r["img_grid"] or r["img_thumb"]
        if not img_url:
            r["local_path"] = "Error: no image URL"
            continue
        try:
            resp = await _client().get(img_url)
            resp.raise_for_status()
            # Determine extension from content-type header
            ct = resp.headers.get("content-type", "")
            if "jpeg" in ct or "jpg" in ct:
                ext = ".jpg"
            elif "png" in ct:
                ext = ".png"
            elif img_url.lower().endswith(".png"):
                ext = ".png"
            else:
                ext = ".jpg"
            filename = f"{i + 1:02d}_{r['uid']}{ext}"
            filepath = output_dir / filename
            filepath.write_bytes(resp.content)
            r["local_path"] = str(filepath.resolve())
        except Exception as exc:
            r["local_path"] = f"Error: {exc}"
    return results


def _fmt_authors(authors: list[dict]) -> str:
    names = [a.get("name", "") for a in authors[:5]]
    suffix = " et al." if len(authors) > 5 else ""
    return ", ".join(names) + suffix


# ── Formatters ──────────────────────────────────────────────────────────────

def _fmt_paper(
    paper: dict,
    num: int,
    *,
    abstract: str | None = None,
    structured: dict[str, str] | None = None,
    fulltext: str | None = None,
    evidence_tier: str | None = None,
    evidence_grade: EvidenceGrade | None = None,
    study_design: str | None = None,
    citation_count: int | None = None,
) -> list[str]:
    """Format a paper with best-available content.

    Precedence: structured abstract sections > plain abstract > nothing.
    PMC full text appended separately when available.
    """
    lines = [
        f"{num}. **{paper['title']}**",
        f"   {paper['authors']}",
        f"   *{paper['source']}* ({paper['pubdate']})",
    ]
    if paper["doi"]:
        lines.append(f"   DOI: {paper['doi']}")
    lines.append(f"   {paper['url']}")

    # Evidence tier + study design (when available from local corpus or PubMed)
    meta_parts = []
    if evidence_grade:
        meta_parts.append(f"{evidence_grade.label} ({evidence_grade.quality_label})")
    if evidence_tier:
        label = EVIDENCE_TIER_LABELS.get(evidence_tier, evidence_tier)
        meta_parts.append(label)
    if study_design:
        meta_parts.append(study_design.replace("_", " ").title())
    if citation_count is not None and citation_count > 0:
        meta_parts.append(f"cited {citation_count}×")
    if meta_parts:
        lines.append(f"   Evidence: {' | '.join(meta_parts)}")

    # Show structured abstract sections (best quality)
    if structured:
        for label in ("BACKGROUND", "METHODS", "RESULTS", "CONCLUSIONS"):
            if label in structured:
                text = structured[label]
                if len(text) > 400:
                    text = text[:400] + "…"
                lines.append(f"   {label.title()}: {text}")
    elif abstract:
        ab = abstract[:500] + ("…" if len(abstract) > 500 else "")
        lines.append(f"   Abstract: {ab}")

    if fulltext:
        ft = fulltext[:1000] + ("…" if len(fulltext) > 1000 else "")
        lines.append(f"   PMC: {ft}")

    lines.append("")
    return lines


def _fmt_corpus_paper(paper: dict, num: int) -> list[str]:
    """Format a paper from the local corpus with evidence tier metadata.

    Corpus papers have a different shape than PubMed summaries —
    title, year, journal, study_design, evidence_tier, citation_count, etc.
    """
    title = paper.get("title", "") or "(untitled)"
    title_display = title[:150] + ("…" if len(title) > 150 else "")

    lines = [f"{num}. **{title_display}**"]

    journal = paper.get("journal", "")
    year = paper.get("year", "")
    if journal and year:
        lines.append(f"   *{journal}* ({year})")
    elif journal:
        lines.append(f"   *{journal}*")
    elif year:
        lines.append(f"   ({year})")

    work_id = paper.get("work_id") or paper.get("id")
    if work_id:
        lines.append(f"   Work ID: {work_id}")

    # Evidence tier + study design
    meta_parts = []
    evidence_tier = paper.get("evidence_tier", "")
    if evidence_tier:
        label = EVIDENCE_TIER_LABELS.get(evidence_tier, evidence_tier)
        meta_parts.append(label)
    study_design = paper.get("study_design", "")
    if study_design:
        meta_parts.append(study_design.replace("_", " ").title())
    citation_count = paper.get("citation_count")
    if citation_count and citation_count > 0:
        meta_parts.append(f"cited {citation_count}×")
    if meta_parts:
        lines.append(f"   Evidence: {' | '.join(meta_parts)}")

    # Subdomain tags
    subdomains = paper.get("subdomains", [])
    if subdomains:
        subdomain_labels = [
            SUBDOMAIN_DESCRIPTIONS.get(s, s).split(",")[0]
            for s in subdomains[:3]
        ]
        lines.append(f"   Topics: {', '.join(subdomain_labels)}")

    # Links
    if paper.get("pubmed_url"):
        lines.append(f"   PubMed: {paper['pubmed_url']}")
    if paper.get("doi"):
        lines.append(f"   DOI: {paper['doi']}")

    # Abstract
    abstract = paper.get("abstract", "")
    if abstract:
        ab = abstract[:500] + ("…" if len(abstract) > 500 else "")
        lines.append(f"   Abstract: {ab}")

    # Conclusion
    conclusion = paper.get("conclusion", "")
    if conclusion:
        cc = conclusion[:400] + ("…" if len(conclusion) > 400 else "")
        lines.append(f"   Conclusion: {cc}")

    lines.append("")
    return lines


# ── MCP Server ──────────────────────────────────────────────────────────────

server = Server("caseprep-mcp")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="search_pubmed",
            description=(
                "Search PubMed via NCBI E-utilities API with optional clinical query "
                "filters and abstract fetching. Returns title, authors, journal, date, "
                "DOI, and direct link. Optionally includes full abstract text. "
                "Supports clinical filters: therapy, prognosis, etiology, diagnosis, "
                "systematic_review."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "PubMed search query (supports full PubMed syntax)",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum results (default: 10, max: 20)",
                        "default": 10,
                    },
                    "filter_type": {
                        "type": "string",
                        "description": (
                            "Clinical query filter: therapy, prognosis, etiology, "
                            "diagnosis, systematic_review. Omit for unfiltered search."
                        ),
                        "enum": ["therapy", "prognosis", "etiology", "diagnosis", "systematic_review"],
                    },
                    "include_abstracts": {
                        "type": "boolean",
                        "description": "Include abstract text for each result (default: false)",
                        "default": False,
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="build_caseplan",
            description=(
                "Run 5 targeted PubMed searches for a neurosurgical topic, fetch "
                "abstracts for the top results, and write a filled-in case prep folder. "
                "Searches cover: anatomy/relevant structures, outcomes/therapy, surgical technique, complications, "
                "and landmark/systematic reviews. Returns organized findings and writes "
                "completed templates to disk."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "The case or procedure (e.g., 'retrosigmoid vestibular schwannoma')",
                    },
                    "output_dir": {
                        "type": "string",
                        "description": "Output directory (default: {slug}-caseprep/)",
                    },
                    "max_per_category": {
                        "type": "integer",
                        "description": "Max papers per search category (default: 3, max: 5)",
                        "default": 3,
                    },
                },
                "required": ["topic"],
            },
        ),
        Tool(
            name="generate_caseprep",
            description=(
                "Generate a blank (fill-in-the-blanks) structured case-prep folder "
                "with Markdown templates and a resource-links.html file."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Case or topic"},
                    "output_dir": {
                        "type": "string",
                        "description": "Output directory (default: {slug}-caseprep/)",
                    },
                },
                "required": ["topic"],
            },
        ),
        Tool(
            name="get_fulltext",
            description=(
                "Fetch the best available full content for a specific PMID. "
                "Tries three tiers: (1) PMC full text via curl, "
                "(2) structured abstract sections (BACKGROUND/METHODS/RESULTS/CONCLUSIONS), "
                "(3) plain abstract text. Returns whatever tier succeeds."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "pmid": {
                        "type": "string",
                        "description": "PubMed ID to fetch full text for",
                    },
                },
                "required": ["pmid"],
            },
        ),
        Tool(
            name="search_local_pdfs",
            description=(
                "Search a directory of local PDF files for topic matches using PyMuPDF. "
                "Returns filename matches and text snippets from first 3 pages."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Topic to search for"},
                    "pdf_dir": {"type": "string", "description": "Directory with PDFs"},
                },
                "required": ["topic", "pdf_dir"],
            },
        ),
        Tool(
            name="search_radiology",
            description=(
                "Search Open-i (NIH) for radiology images — MRI, CT, X-ray, ultrasound — "
                "from PubMed Central articles. Images are downloaded to disk as PNG/JPEG "
                "by default (set download_images=false to skip). Results are filtered for "
                "relevance: title or caption must contain at least one query term. "
                "Filter by modality: any (default), mri, ct, xray, ultrasound."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (e.g., 'vestibular schwannoma MRI CPA angle')",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum image results (default: 5, max: 10)",
                        "default": 5,
                    },
                    "modality": {
                        "type": "string",
                        "description": (
                            "Image modality filter: any (all radiology, default), "
                            "mri, ct, xray, ultrasound"
                        ),
                        "enum": ["any", "mri", "ct", "xray", "ultrasound"],
                    },
                    "download_images": {
                        "type": "boolean",
                        "description": (
                            "Download images to disk as PNG/JPEG (default: true). "
                            "Set false to return URLs only."
                        ),
                        "default": True,
                    },
                    "output_dir": {
                        "type": "string",
                        "description": (
                            "Directory to save downloaded images. Default: "
                            "<query>-images/ in the current working directory."
                        ),
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="send_email",
            description=(
                "Send an email via Resend REST API. Requires RESEND_API_KEY in environment. "
                "Supports plain text body. Default sender: CasePrep <onboarding@resend.dev>. "
                "Returns the Resend email ID on success."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "to": {
                        "type": "string",
                        "description": "Recipient email address",
                    },
                    "subject": {
                        "type": "string",
                        "description": "Email subject line",
                    },
                    "body": {
                        "type": "string",
                        "description": "Plain text email body",
                    },
                    "from_": {
                        "type": "string",
                        "description": (
                            "Sender address. Default: CasePrep <onboarding@resend.dev>. "
                            "Custom domains must be verified in Resend dashboard."
                        ),
                    },
                },
                "required": ["to", "subject", "body"],
            },
        ),
        Tool(
            name="list_subdomains",
            description=(
                "List available clinical subdomains in the local neurointerventional "
                "corpus with paper counts and descriptions. Use this first to see what "
                "evidence buckets are available before searching the corpus."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        Tool(
            name="search_corpus",
            description=(
                "Search the local neurointerventional literature corpus using FTS5 "
                "(full-text search) with BM25 ranking, optionally filtered by subdomain. "
                "Returns ranked papers with title, year, journal, study design, evidence "
                "tier, citation count, abstract, and conclusion. Much faster than PubMed "
                "— sub-second local search over 51,980 pre-indexed papers."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "fts_query": {
                        "type": "string",
                        "description": (
                            "SQLite FTS5 query. Use boolean operators (AND, OR), "
                            "quoted phrases, parentheses. Example: "
                            "'thrombectomy AND (\"stent retriever\" OR aspiration)'"
                        ),
                    },
                    "subdomain": {
                        "type": "string",
                        "description": (
                            "Optional subdomain ID from list_subdomains() to filter. "
                            "Use for clinically-bounded questions. Omit for "
                            "cross-cutting topics."
                        ),
                    },
                    "top_n": {
                        "type": "integer",
                        "description": "Number of top-ranked papers to return (default: 8, max: 25)",
                        "default": 8,
                    },
                },
                "required": ["fts_query"],
            },
        ),
        Tool(
            name="get_paper",
            description=(
                "Retrieve detailed information for a specific paper from the local "
                "neurointerventional corpus by work_id. Returns full metadata (title, "
                "journal, year, study design, evidence tier, citation count, MeSH terms, "
                "keywords), plus all available full-text section passages (introduction, "
                "methods, results, discussion, conclusion). Use for drill-down after "
                "search_corpus surfaces a paper that needs deeper inspection."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "work_id": {
                        "type": "string",
                        "description": "The work_id from a search_corpus result",
                    },
                },
                "required": ["work_id"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        match name:
            case "search_pubmed":
                result = await _handle_pubmed(arguments)
            case "build_caseplan":
                result = await _handle_build_caseplan(arguments)
            case "generate_caseprep":
                result = _handle_generate(arguments)
            case "search_local_pdfs":
                result = _handle_pdfs(arguments)
            case "get_fulltext":
                result = await _handle_get_fulltext(arguments)
            case "search_radiology":
                result = await _handle_radiology(arguments)
            case "send_email":
                result = await _handle_send_email(arguments)
            case "list_subdomains":
                result = _handle_list_subdomains(arguments)
            case "search_corpus":
                result = _handle_search_corpus(arguments)
            case "get_paper":
                result = _handle_get_paper(arguments)
            case _:
                result = f"Unknown tool: {name}"
        return [TextContent(type="text", text=result)]
    except Exception as exc:
        return [TextContent(type="text", text=f"Error: {exc}")]


# ── Tool handlers ───────────────────────────────────────────────────────────

async def _handle_pubmed(args: dict) -> str:
    query = args["query"]
    max_results = min(args.get("max_results", 10), 20)
    filter_type = args.get("filter_type")
    include_abstracts = args.get("include_abstracts", False)

    pmids, total = await _pubmed_search(query, max_results, filter_type)
    if not pmids:
        filter_note = f" (filter: {filter_type})" if filter_type else ""
        return f"No PubMed results for: {query}{filter_note}"

    articles = await _pubmed_summaries(pmids[:max_results])

    abstracts = {}
    if include_abstracts:
        abstracts = await _pubmed_abstracts([a["pmid"] for a in articles])

    for article in articles:
        abstract = abstracts.get(article["pmid"])
        article["_relevance_score"] = neurosurg_relevance_score(
            article.get("title", ""),
            abstract,
        )
        article["_evidence_grade"] = grade_evidence(article.get("pub_types", []))
    articles.sort(key=lambda a: a.get("_relevance_score", 0.0), reverse=True)

    filter_note = f" — filter: {filter_type}" if filter_type else ""
    lines = [
        f"## PubMed{filter_note} — {query}",
        f"({len(articles)} shown of {total} total)\n",
    ]
    for i, a in enumerate(articles, 1):
        lines.extend(_fmt_paper(
            a,
            i,
            abstract=abstracts.get(a["pmid"]),
            evidence_grade=a.get("_evidence_grade"),
        ))

    return "\n".join(lines)


async def _handle_build_caseplan(args: dict) -> str:
    topic = args["topic"]
    max_per = min(args.get("max_per_category", 5), 10)
    slug = topic.strip().lower().replace(" ", "-")
    out_dir = Path(args.get("output_dir", "") or f"{slug}-caseprep")
    if not out_dir.is_absolute():
        out_dir = Path.cwd() / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    # Detect profile early to inform search queries
    profile_name, profile_confidence = _detect_profile(topic)
    profile_kw = _build_keywords(profile_name)

    # Build anatomy search query with profile-specific terms
    # Generic "anatomy relevant structures" returns treatment papers;
    # injecting top profile anatomy keywords focuses PubMed on actual anatomy.
    top_anatomy_terms = profile_kw["anatomy"][:5]  # top 5 domain-specific terms
    anatomy_query = build_enriched_query(topic, top_anatomy_terms)
    # Keep query under PubMed's practical length (~256 chars works well)
    if len(anatomy_query) > 200:
        anatomy_query = anatomy_query[:200].rsplit(" ", 1)[0]

    # ── Define the 5 search axes ────────────────────────────────────────
    # Anatomy axis uses profile-specific anatomical terms to find actual
    # anatomy papers rather than generic treatment/outcome studies.
    searches: list[tuple[str, str, str | None]] = [
        # (label, query suffix, filter_type)
        ("Anatomy / Relevant Structures", anatomy_query, None),
        ("Outcomes / Evidence", f"{topic} outcomes", "therapy"),
        ("Surgical Technique", f"{topic} surgical technique approach", None),
        ("Complications", f"{topic} complications adverse", "etiology"),
        ("Reviews / Landmarks", topic, "systematic_review"),
    ]

    lines = [f"# Case Plan — {topic}\n"]
    all_articles: list[dict] = []
    axis_data: dict[str, list[dict]] = {}

    for label, query, filt in searches:
        lines.append(f"## {label}\n")

        pmids, total = await _pubmed_search(query, max_per, filt)
        if not pmids:
            lines.append(f"  No results ({total} total in PubMed).\n")
            axis_data[label] = []
            continue

        articles = await _pubmed_summaries(pmids[:max_per])
        abstracts = await _pubmed_abstracts([a["pmid"] for a in articles])
        structured = await _pubmed_structured_abstracts([a["pmid"] for a in articles])
        all_articles.extend(articles)

        # Store enriched articles for template population
        enriched = []
        for a in articles:
            abstract = abstracts.get(a["pmid"], "")
            a["_relevance_score"] = neurosurg_relevance_score(
                a.get("title", ""),
                abstract,
            )
            a["_evidence_grade"] = grade_evidence(a.get("pub_types", []))
            a["_study_type"] = classify_study_type(a.get("pub_types", []))
            a["_n_value"] = extract_n_value(abstract)
            entry = dict(a)
            entry["_abstract"] = abstract
            entry["_structured"] = structured.get(a["pmid"], {})
            enriched.append(entry)
        axis_data[label] = enriched

        lines.append(f"  ({len(articles)} shown of {total} total)\n")
        for i, a in enumerate(articles, 1):
            lines.extend(_fmt_paper(
                a, i,
                abstract=abstracts.get(a["pmid"]),
                structured=structured.get(a["pmid"]),
                evidence_grade=a.get("_evidence_grade"),
            ))

    # Fetch PMC full text for all papers
    if all_articles:
        fulltexts = await _pubmed_fulltext([a["pmid"] for a in all_articles])
        if fulltexts:
            lines.append("\n## PMC Full Text Available\n")
            for pmid, ft in fulltexts.items():
                lines.append(f"  PMID {pmid}: {len(ft)} chars\n")
                lines.append(f"  {ft[:800]}…\n")

    summary = "\n".join(lines)

    # ── Write filled-in templates to disk ───────────────────────────────
    await _write_filled_templates(out_dir, topic, summary, axis_data)

    links = build_search_links(topic)
    resource_path = out_dir / "resource-links.html"
    resource_path.write_text(_resource_html(topic, links), encoding="utf-8")

    return f"{summary}\n\n---\nCase plan written to {out_dir.resolve()}/"


# ── Template population: domain-aware keyword extraction ──────────────────
#
# Each domain profile has keyword lists tailored to specific neurosurgical
# subspecialties. The pipeline auto-detects the best profile from the topic
# string. Profiles are additive — base keywords apply to all, profile-specific
# keywords are merged on top.

# Base keywords — always included regardless of profile
_BASE_ANATOMY = [
    "anatomy", "anatomic", "structure", "nerve", "artery", "vein",
    "nucleus", "tract", "cortex", "lobe", "foramen", "fissure",
    "sulcus", "gyrus", "ventricle", "cistern",
]
_BASE_APPROACH = [
    "approach", "technique", "positioning", "craniotomy", "incision",
    "resection", "dissection", "exposure", "retraction",
    "microsurgical", "endoscopic", "minimally invasive",
    "monitoring", "neuromonitoring", "intraoperative",
    "neuronavigation", "bone flap", "dura", "closure", "hemostasis",
]
_BASE_COMPLICATIONS = [
    "complication", "risk", "mortality", "morbidity", "deficit",
    "infection", "meningitis", "hematoma", "hemorrhage", "ischemia",
    "infarction", "edema", "seizure", "hydrocephalus",
    "thromboembolism", "rate", "%", "percent", "incidence", "n=",
]

# Domain profiles — merged with base keywords
_DOMAIN_PROFILES: dict[str, dict[str, list[str]]] = {
    "skull_base": {
        "anatomy": [
            "cranial nerve", "cn vii", "cn viii", "cn v", "cn ix", "cn x",
            "brainstem", "cerebell", "temporal bone", "sigmoid", "petrous",
            "cavernous", "sella", "clivus", "jugular", "meckel", "cpa",
            "cerebellopontine", "internal acoustic", "geniculate",
            "sphenoid", "petroclival", "tentorium",
        ],
        "approach": [
            "retrosigmoid", "translabyrinthine", "middle fossa",
            "transpetrosal", "presigmoid", "drilling",
            "ssep", "mep", "emg", "baer", "facial nerve monitor",
            "keyhole", "endonasal", "transsphenoidal",
        ],
        "complications": [
            "cerebrospinal fluid leak", "csf leak", "facial nerve",
            "hearing loss", "anosmia", "diplopia", "dysphagia",
            "aspiration", "hoarseness", "dvt", "pe",
        ],
    },
    "supratentorial_tumor": {
        "anatomy": [
            "eloquent", "frontal", "temporal", "parietal", "occipital",
            "broca", "wernicke", "supplementary motor", "sma", "insula",
            "corpus callosum", "basal ganglia", "thalamus",
            "white matter", "corticospinal", "arcuate", "precentral",
            "postcentral", "language", "motor cortex", "sensory",
            "visual cortex", "optic radiation", "internal capsule",
        ],
        "approach": [
            "awake craniotomy", "asleep", "frameless", "stereotactic",
            "neuronavigation", "intraoperative mri", "fluorescence",
            "5-ala", "aminolevulinic", "mapping", "cortical mapping",
            "subcortical", "des", "direct electrical stimulation",
            "keyhole", "tubular", "ssep", "mep", "emg",
        ],
        "complications": [
            "aphasia", "dysphasia", "hemiparesis", "visual field",
            "neglect", "cognitive", "personality", "mood",
            "wound", "dehiscence", "pseudomeningocele",
        ],
    },
    "vascular": {
        # Derived from Neurointerventional Evidence Taxonomy (7-axis faceted system).
        # Axis 2 (Vascular Territory) + Axis 3 (Pathology) → anatomy keywords.
        # Axis 4 (Procedure/Technique) → approach keywords.
        # Axis 7 (Outcome Domain, complication subtree) → complications keywords.
        "anatomy": [
            # ── Vascular territories (Axis 2) ──
            "aca", "a1", "a2", "pericallosal", "distal aca",
            "mca", "m1", "m2", "m3", "m4",
            "ica", "cavernous", "petrous", "paraophthalmic", "terminus", "bifurcation",
            "pcom", "anterior choroidal",
            "anterior circulation", "anterior perforators",
            "vertebral", "v1", "v2", "v3", "v4",
            "basilar", "mid basilar", "distal basilar",
            "pca", "p1", "p2",
            "pica", "aica", "sca", "cerebellar",
            "posterior circulation",
            "acom", "lenticulostriate", "perforators",
            # ── Venous (Axis 2) ──
            "superior sagittal sinus", "transverse sinus", "sigmoid sinus",
            "straight sinus", "torcula", "cavernous sinus", "jugular bulb",
            "internal cerebral veins", "vein of galen", "basal veins of rosenthal",
            "cortical veins", "dural sinuses",
            # ── Extracranial / spinal (Axis 2) ──
            "common carotid", "brachiocephalic", "subclavian",
            "extracranial carotid", "vertebral origin",
            "radicular arteries", "segmental arteries",
            # ── Pathology (Axis 3) ──
            "aneurysm", "saccular", "sidewall", "fusiform", "dolichoectatic",
            "blister", "dissecting", "mycotic", "traumatic pseudoaneurysm",
            "avm", "arteriovenous malformation", "compact", "diffuse",
            "spetzler-martin grade", "lawton-young supplementary grade",
            "davf", "borden i", "borden ii", "borden iii",
            "cognard i-iia", "cognard iib", "cognard iii-iv",
            "ccf", "barrow a", "barrow b", "barrow c", "barrow d",
            "atherosclerotic stenosis", "intracranial stenosis", "icad",
            "acute occlusion", "cardioembolic", "cryptogenic", "esus",
            "arterial dissection", "tandem occlusion",
            "vasospasm", "post-asah", "rcvs",
            "sinus thrombosis", "sinus stenosis", "venous sinus atresia",
            "cavernous malformation", "developmental venous anomaly",
            "capillary telangiectasia", "sinus pericranii",
            "hemorrhage", "sah", "ich", "ivh", "csdh", "subarachnoid",
            "tumor", "meningioma", "glomus tumor", "paraganglioma",
            "hemangioblastoma", "hemangiopericytoma", "metastasis",
            "juvenile nasopharyngeal angiofibroma",
            "flow-related", "with intranidal aneurysm", "ruptured vs unruptured",
            # ── Access / traversal terms (surgical context) ──
            "sylvian", "interhemispheric", "pterional", "transsylvian",
        ],
        "approach": [
            # ── Aneurysm treatment (Axis 4) ──
            "primary coiling", "coiling", "balloon-assisted coiling",
            "stent-assisted coiling", "jailing", "coil-through-stent",
            "y-stenting", "flow diversion", "telescoping",
            "intrasaccular flow disruption", "parent vessel sacrifice",
            "with adjunctive coiling",
            # ── Thrombectomy (Axis 4) ──
            "mechanical thrombectomy", "aspiration alone",
            "stent retriever alone", "contact aspiration",
            # ── AVM/dAVF/embolization (Axis 4) ──
            "avm embolization", "davf embolization", "tumor embolization",
            "mma embolization", "epistaxis embolization",
            "transarterial", "transvenous", "combined transarterial + transvenous",
            "direct puncture", "liquid embolic", "coils",
            "preoperative devascularization", "preradiosurgical",
            "staged", "multi-session",
            # ── Carotid / stenting (Axis 4) ──
            "carotid revascularization", "transfemoral cas", "transcarotid",
            "intracranial stenting", "angioplasty", "angioplasty + stenting",
            "balloon angioplasty alone", "drug-coated balloon angioplasty",
            "self-expanding", "balloon-expandable",
            "with distal embolic protection", "with proximal protection",
            "flow reversal",
            # ── Access / closure (Axis 4) ──
            "transfemoral", "transradial", "transulnar", "direct carotid",
            "closure device", "closure",
            # ── Venous / spinal / diagnostic (Axis 4) ──
            "venous sinus stenting", "venous thrombectomy", "venous manometry",
            "venous interventions", "thrombolysis",
            "spinal angiography", "spinal avm embolization", "spinal davf embolization",
            "diagnostic angiography", "4-vessel cerebral angiogram",
            "selective catheterization", "provocative testing",
            "balloon test occlusion",
            # ── Surgical open-vascular (surgeon's terms, not taxonomy) ──
            "clipping", "bypass", "ec-ic", "temporary clip",
            "burst suppression", "adenosine", "indocyanine", "icg",
            "doppler", "microdoppler", "orbitozygomatic", "far lateral",
            "subtemporal", "supraorbital",
        ],
        "complications": [
            # ── Hemorrhagic (Axis 7) ──
            "sich", "parenchymal hematoma", "sah",
            "access site hematoma", "retroperitoneal hematoma",
            "hemorrhage", "rebleed", "rebleed rate", "delayed rupture",
            # ── Ischemic (Axis 7) ──
            "territorial infarct", "perforator infarct", "distal emboli",
            "vasospasm", "delayed cerebral ischemia", "dci",
            # ── Device-related (Axis 7) ──
            "thrombosis", "in-stent stenosis", "in-stent restenosis",
            "migration", "fracture", "malapposition",
            "braid deformation", "foreshortening", "fish-mouthing",
            "wall apposition",
            # ── Access site (Axis 7) ──
            "pseudoaneurysm", "dissection", "radial artery occlusion",
            "access site",
            # ── Contrast / systemic (Axis 7) ──
            "contrast-induced nephropathy", "allergic reaction",
            "infection", "cranial neuropathy", "seizure",
            # ── Outcomes / grading (Axis 7) ──
            "mrs 0-2", "mrs 0-1", "mrs at 90 days", "mrs at discharge",
            "mrs shift", "mtici 2b", "mtici 2c", "mtici 3",
            "first-pass effect", "reperfusion",
            "nihss change", "barthel index", "cognitive outcomes",
            "mortality", "30-day", "90-day", "in-hospital",
            "aneurysm occlusion", "class i", "class ii", "class iiia",
            "aneurysm recanalization", "retreatment rate", "regrowth",
            "obliteration rate",
            "complication rate", "complications",
            # ── Disease-specific (Axis 7) ──
            "hydrocephalus", "shunt", "csf",
            "seizure freedom", "papilledema grade",
            "visual acuity", "visual field",
            "pulsatile tinnitus resolution",
            "myelopathy improvement",
            "radiation dose", "fluoroscopy time",
            # ── Surgical (surgeon's terms) ──
            "clip slippage", "parent vessel", "stroke", "infarct",
            "nimodipine",
        ],
    },
    "spine": {
        "anatomy": [
            "cervical", "thoracic", "lumbar", "sacral", "vertebra",
            "disc", "pedicle", "lamina", "facet", "foramen",
            "spinal cord", "nerve root", "cauda equina", "conus",
            "thecal sac", "ligamentum", "odontoid", "atlantoaxial",
            "spinous", "transverse process", "pars",
        ],
        "approach": [
            "laminectomy", "laminoplasty", "discectomy", "microdiscectomy",
            "fusion", "instrumentation", "pedicle screw", "cage",
            "corpectomy", "foraminotomy", "tlif", "plif", "alif",
            "xlif", "oblique", "lateral", "minimally invasive spine",
            "tubular", "endoscopic spine", "neuronavigation spine",
            "o-arm", "navigation", "robotic",
        ],
        "complications": [
            "dural tear", "nerve root injury", "pseudarthrosis",
            "adjacent segment", "instrumentation failure", "screw",
            "misplacement", "dysphagia", "hoarseness", "c5 palsy",
            "kyphosis", "sagittal", "flat back", "proximal junctional",
        ],
    },
    "functional": {
        "anatomy": [
            "basal ganglia", "thalamus", "subthalamic", "stn", "gpi",
            "vop", "vim", "striatum", "globus pallidus", "substantia nigra",
            "motor cortex", "premotor", "sma", "cingulate", "insula",
            "hippocampus", "amygdala", "anterior nucleus", "centromedian",
        ],
        "approach": [
            "deep brain stimulation", "dbs", "stereotactic", "frame",
            "frameless", "microelectrode", "mer", "macroelectrode",
            "impedance", "electrode", "lead", "pulse generator",
            "programming", "theta", "beta", "gamma",
            "radiofrequency", "rft", "rhizotomy", "thermocoagulation",
            "laser ablation", "litt", "focused ultrasound", "mrgfus",
        ],
        "complications": [
            "hemorrhage dbs", "infection dbs", "lead migration",
            "lead fracture", "erosion", "ipg", "stimulation side effects",
            "dysarthria", "gait", "cognitive dbs", "mood dbs",
            "suicide", "impulse control", "status dystonicus",
        ],
    },
    "pediatric": {
        "anatomy": [
            "fontanelle", "suture", "craniosynostosis", "hydrocephalus",
            "ventricle", "choroid plexus", "myelination", "germinal matrix",
            "posterior fossa", "fourth ventricle", "brainstem",
            "cerebell", "vermis", "tectal", "pineal",
        ],
        "approach": [
            "endoscopic third ventriculostomy", "etv", "shunt",
            "vps", "vetriculoperitoneal", "programmable",
            "posterior fossa craniotomy", "telovelar",
            "endoscopic biopsy", "navigated biopsy",
            "intraoperative ultrasound", "vagal nerve stimulator", "vns",
            "corpus callosotomy", "hemispherectomy", "lobar",
            "grid", "depth electrode", "seeg", "ecog",
        ],
        "complications": [
            "shunt infection", "shunt malfunction", "overdrainage",
            "slit ventricle", "cranial defect", "infection pediatric",
            "mutism", "cerebellar mutism", "posterior fossa syndrome",
            "endocrine", "growth", "developmental", "cognitive pediatric",
            "seizure pediatric", "hydrocephalus acquired",
        ],
    },
}

# Alias map: common topic terms → profile name
_TOPIC_TO_PROFILE: dict[str, str] = {
    # Skull base
    "vestibular schwannoma": "skull_base",
    "acoustic neuroma": "skull_base",
    "meningioma": "skull_base",
    "chordoma": "skull_base",
    "chondrosarcoma": "skull_base",
    "craniopharyngioma": "skull_base",
    "pituitary": "skull_base",
    "epidermoid": "skull_base",
    "petroclival": "skull_base",
    "cerebellopontine": "skull_base",
    "cpa": "skull_base",
    "jugular": "skull_base",
    "glomus": "skull_base",
    # Supratentorial tumor
    "glioblastoma": "supratentorial_tumor",
    "gbm": "supratentorial_tumor",
    "glioma": "supratentorial_tumor",
    "astrocytoma": "supratentorial_tumor",
    "oligodendroglioma": "supratentorial_tumor",
    "oligoastrocytoma": "supratentorial_tumor",
    "metastasis": "supratentorial_tumor",
    "brain metastasis": "supratentorial_tumor",
    "lymphoma": "supratentorial_tumor",
    # Vascular
    "aneurysm": "vascular",
    "clipping": "vascular",
    "coiling": "vascular",
    "anterior communicating": "vascular",
    "posterior communicating": "vascular",
    "anterior choroidal": "vascular",
    "basilar": "vascular",
    "avm": "vascular",
    "arteriovenous malformation": "vascular",
    "cavernous malformation": "vascular",
    "cavernoma": "vascular",
    "moyamoya": "vascular",
    "bypass": "vascular",
    "ec-ic": "vascular",
    "subarachnoid": "vascular",
    "sah": "vascular",
    "intracerebral hemorrhage": "vascular",
    "ich": "vascular",
    "hemorrhagic stroke": "vascular",
    "embolization": "vascular",
    "flow diversion": "vascular",
    "stent retriever": "vascular",
    "thrombectomy": "vascular",
    "davf": "vascular",
    "dural arteriovenous fistula": "vascular",
    "ccf": "vascular",
    "carotid cavernous fistula": "vascular",
    "carotid stenosis": "vascular",
    "carotid stenting": "vascular",
    "carotid endarterectomy": "vascular",
    "vasospasm": "vascular",
    "mechanical thrombectomy": "vascular",
    "acute ischemic stroke": "vascular",
    # Spine
    "spine": "spine",
    "spinal": "spine",
    "discectomy": "spine",
    "laminectomy": "spine",
    "fusion": "spine",
    "cervical": "spine",
    "lumbar": "spine",
    "thoracic": "spine",
    "scoliosis": "spine",
    "spondylolisthesis": "spine",
    "stenosis": "spine",
    "myelopathy": "spine",
    "radiculopathy": "spine",
    "cord": "spine",
    # Functional
    "deep brain": "functional",
    "dbs": "functional",
    "parkinson": "functional",
    "tremor": "functional",
    "dystonia": "functional",
    "epilepsy surgery": "functional",
    "seizure focus": "functional",
    "temporal lobectomy": "functional",
    "laser ablation": "functional",
    "litt": "functional",
    "focused ultrasound": "functional",
    "mrgfus": "functional",
    # Pediatric
    "pediatric": "pediatric",
    "paediatric": "pediatric",
    "child": "pediatric",
    "hydrocephalus": "pediatric",
    "shunt": "pediatric",
    "craniosynostosis": "pediatric",
    "myelomeningocele": "pediatric",
    "tethered cord": "pediatric",
    "medulloblastoma": "pediatric",
    "ependymoma": "pediatric",
}

# Build merged keyword lists from base + profile
def _build_keywords(profile: str) -> dict[str, list[str]]:
    """Merge base keywords with profile-specific keywords. Returns {anatomy, approach, complications}."""
    pd = _DOMAIN_PROFILES.get(profile, {})
    return {
        "anatomy": _BASE_ANATOMY + pd.get("anatomy", []),
        "approach": _BASE_APPROACH + pd.get("approach", []),
        "complications": _BASE_COMPLICATIONS + pd.get("complications", []),
    }


# ── Profile detection ──────────────────────────────────────────────────

def _detect_profile(topic: str) -> tuple[str, float]:
    """Detect the best domain profile for a topic string.

    Returns (profile_name, confidence) where confidence is 0.0–1.0.
    Falls back to 'skull_base' with low confidence if no match.
    """
    topic_lower = topic.lower()

    # First pass: exact substring matches (higher confidence)
    best_match = None
    best_len = 0
    for key, profile in _TOPIC_TO_PROFILE.items():
        if key in topic_lower:
            if len(key) > best_len:  # longest match wins
                best_match = profile
                best_len = len(key)

    if best_match:
        # Confidence = how much of the token space the matched key covers
        confidence = min(1.0, best_len / max(len(topic_lower), 10))
        return (best_match, confidence)

    # Second pass: word-level matching (lower confidence)
    topic_words = set(topic_lower.replace("-", " ").replace("/", " ").split())
    word_hits: dict[str, int] = {}
    for key, profile in _TOPIC_TO_PROFILE.items():
        key_words = set(key.split())
        overlap = topic_words & key_words
        if overlap:
            word_hits[profile] = word_hits.get(profile, 0) + len(overlap)

    if word_hits:
        best_profile = max(word_hits, key=lambda p: word_hits[p])  # type: ignore[arg-type]
        confidence = min(0.5, word_hits[best_profile] / max(len(topic_words), 5))
        return (best_profile, confidence)

    # Fallback: skull_base (most general neurosurgical profile)
    return ("skull_base", 0.0)


# ── Open-i radiology image search ────────────────────────────────────────────


async def _write_filled_templates(
    out_dir: Path, topic: str, summary: str,
    axis_data: dict[str, list[dict]] | None = None,
) -> None:
    """Write filled-in markdown templates using keyword-extracted content from search results."""
    profile_name, profile_confidence = _detect_profile(topic)
    if axis_data:
        schema = build_caseprep_schema_from_axis_data(
            topic,
            axis_data,
            profile=profile_name,
        )
    else:
        schema = build_caseprep_schema(topic, profile=profile_name)

    rendered_files = render_caseprep_files(schema, literature_summary=summary)
    for filename, content in rendered_files.items():
        (out_dir / filename).write_text(content, encoding="utf-8")

    # Schema + evidence-level metadata are already written above.
    # LLM-based extract→synthesize→guardrail template population is removed
    # because it produced unreliable content. The citation table with
    # evidence_level fields is the canonical output.


def _resource_html(topic: str, links: dict[str, str]) -> str:
    items = "\n".join(
        f'  <li><a href="{url}" target="_blank" rel="noopener">{name}</a></li>'
        for name, url in links.items()
    )
    return (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n"
        "<meta charset=\"utf-8\">\n"
        f"<title>Resource Links — {topic}</title>\n"
        "<style>\n"
        "  body { font-family: system-ui, sans-serif; max-width: 700px; margin: 2em auto; padding: 0 1em; }\n"
        "  h1 { font-size: 1.4em; }\n"
        "  ul { list-style: none; padding: 0; }\n"
        "  li { margin: 0.5em 0; }\n"
        "  a { color: #1a56db; }\n"
        "</style>\n</head>\n<body>\n"
        f"<h1>Resource Links — {topic}</h1>\n<ul>\n{items}\n</ul>\n"
        "</body>\n</html>\n"
    )


def _handle_generate(args: dict) -> str:
    topic = args["topic"]
    output_dir = args.get("output_dir", "")
    out = Path(output_dir) if output_dir else None
    slug = topic.lower().replace(" ", "-")
    resource_path = _generate_caseprep(topic, out or f"{slug}-caseprep")
    return (
        f"Case prep generated.\n"
        f"  Output: {resource_path.parent.resolve()}\n"
        f"  Resources: {resource_path}\n"
    )


def _handle_pdfs(args: dict) -> str:
    topic = args["topic"]
    pdf_dir = Path(args["pdf_dir"])
    results = _search_local_pdfs(topic, pdf_dir)
    return format_pdf_results(results)


async def _handle_get_fulltext(args: dict) -> str:
    """Fetch best available content for a single PMID: PMC > structured > plain."""
    pmid = args["pmid"]
    summaries = await _pubmed_summaries([pmid])
    if not summaries:
        return f"PMID {pmid} not found."
    paper = summaries[0]
    lines = [f"## {paper['title']}", f"{paper['authors']} — *{paper['source']}* ({paper['pubdate']})", ""]

    # Tier 1: PMC full text
    fulltexts = await _pubmed_fulltext([pmid])
    if pmid in fulltexts:
        lines.append("### PMC Full Text\n")
        lines.append(fulltexts[pmid][:5000])
        return "\n".join(lines)

    # Tier 2: Structured abstract (only accept if it has recognized sections)
    structured = await _pubmed_structured_abstracts([pmid])
    if pmid in structured:
        sections = structured[pmid]
        has_content = any(
            sections.get(k) for k in ("BACKGROUND", "METHODS", "RESULTS", "CONCLUSIONS", "TEXT")
        )
        if has_content:
            lines.append("### Structured Abstract\n")
            for label in ("BACKGROUND", "METHODS", "RESULTS", "CONCLUSIONS"):
                if label in sections:
                    lines.append(f"**{label.title()}:** {sections[label]}\n")
            if "TEXT" in sections:
                lines.append(f"{sections['TEXT']}\n")
            return "\n".join(lines)

    # Tier 3: Plain abstract
    abstracts = await _pubmed_abstracts([pmid])
    if pmid in abstracts:
        lines.append("### Abstract\n")
        lines.append(abstracts[pmid])
        return "\n".join(lines)

    return f"No full text or abstract available for PMID {pmid}."


async def _handle_radiology(args: dict) -> str:
    """Search Open-i for radiology images, download them, return local paths.

    Extracts query terms for relevance filtering: a result's title or caption
    must contain at least one term to be included.  Fetches more results from
    Open-i to compensate for the filter.

    Images are downloaded to <query>-images/ (or *output_dir* if provided).
    Set download_images=false to skip downloading and return URLs only.
    """
    query = args["query"]
    max_results = min(args.get("max_results", 5), 10)
    modality = args.get("modality")
    download = args.get("download_images", True)
    output_dir = args.get("output_dir", "")

    # Extract terms for relevance post-filtering
    terms = _query_terms(query)

    results, total = await _openi_search(query, max_results, modality, query_terms=terms)

    mod_note = f" — modality: {modality}" if modality and modality != "any" else ""
    filter_note = f" (filtered by: {', '.join(terms)})" if terms else ""
    lines = [
        f"## Radiology Images{mod_note} — {query}{filter_note}",
        f"({len(results)} shown of {total} total)\n",
    ]

    if not results:
        lines.append("No radiology images found. Try a broader query or a different modality.")
        return "\n".join(lines)

    # Download images if requested
    if download and results:
        slug = query.strip().lower().replace(" ", "-")[:60]
        out_dir = Path(output_dir) if output_dir else Path(f"{slug}-images")
        if not out_dir.is_absolute():
            out_dir = Path.cwd() / out_dir
        results = await _download_images(results, out_dir, max_images=max_results)
        lines.append(f"*Images saved to {out_dir.resolve()}/*\n")

    for i, r in enumerate(results, 1):
        lines.append(f"{i}. **{r['title'][:120]}{'…' if len(r['title']) > 120 else ''}**")
        lines.append(f"   *{r['journal']}* ({r['pubdate']}) — {r['authors'][:80]}")
        if r["pmid"]:
            lines.append(f"   PMID: [{r['pmid']}](https://pubmed.ncbi.nlm.nih.gov/{r['pmid']}/)")
        if r.get("article_type"):
            lines.append(f"   Type: {r['article_type']}")
        if r["caption"]:
            cap = r["caption"][:300] + ("…" if len(r["caption"]) > 300 else "")
            lines.append(f"   Caption: {cap}")
        local = r.get("local_path", "")
        if local and not local.startswith("Error"):
            lines.append(f"   Image: {local}")
            # MEDIA tag so Hermes can show the image inline
            lines.append(f"   MEDIA:{local}")
        elif local:
            lines.append(f"   Download error: {local}")
        lines.append("")

    return "\n".join(lines)


def _handle_list_subdomains(args: dict) -> str:
    """List available clinical subdomains in the local corpus."""
    if not _CORPUS_AVAILABLE:
        return (
            "Local corpus not available.\n\n"
            "The neurointerventional corpus databases were not found at:\n"
            f"  Corpus: {_CORPUS_DB}\n"
            f"  Fulltext: {_FULLTEXT_DB}\n\n"
            "Set CASEPREP_CORPUS_DB and CASEPREP_FULLTEXT_DB environment variables "
            "to point to your NSGY_DB_lean databases."
        )
    subdomains = _corpus_list_subdomains()
    lines = [
        f"## Neurointerventional Corpus — {len(subdomains)} Subdomains",
        f"({sum(s['paper_count'] for s in subdomains):,} total paper assignments across 51,980 papers)\n",
    ]
    for sd in subdomains:
        desc = sd["description"][:80]
        lines.append(f"- **{sd['id']}** ({sd['paper_count']:,} papers): {desc}")
    return "\n".join(lines)


def _handle_search_corpus(args: dict) -> str:
    """Search the local corpus via FTS5."""
    fts_query = args["fts_query"]
    subdomain = args.get("subdomain")
    top_n = min(args.get("top_n", 8), 25)

    result = _corpus_search(fts_query, subdomain, top_n)

    if "error" in result:
        if str(result["error"]).startswith("Invalid FTS query:"):
            return (
                f"{result['error']}\n\n"
                "Check the FTS5 syntax in fts_query, then retry the corpus search."
            )
        return (
            f"Corpus search unavailable: {result['error']}\n\n"
            f"  Corpus: {_CORPUS_DB}\n"
            f"  Fulltext: {_FULLTEXT_DB}"
        )

    papers = result["papers"]
    total = result["total_matches"]
    returned = result["returned"]
    subdomain_dist = result.get("subdomain_distribution", {})

    sd_note = f" — subdomain: {subdomain}" if subdomain else ""

    lines = [
        f"## Corpus Search{sd_note} — `{fts_query}`",
        f"({returned} shown of {total:,} total matches)\n",
    ]

    # Subdomain distribution (only when no subdomain filter)
    if not subdomain and subdomain_dist:
        top_sds = sorted(subdomain_dist.items(), key=lambda x: x[1], reverse=True)[:5]
        sd_parts = []
        for sd_id, count in top_sds:
            desc = SUBDOMAIN_DESCRIPTIONS.get(sd_id, sd_id).split(",")[0]
            sd_parts.append(f"{desc} ({count})")
        lines.append(f"Top domains: {' | '.join(sd_parts)}\n")

    for i, paper in enumerate(papers, 1):
        lines.extend(_fmt_corpus_paper(paper, i))

    # Corpus availability note
    lines.append(
        f"---\n*Searched local neurointerventional corpus ({total:,} papers indexed). "
        "Use search_pubmed for live PubMed queries or get_paper with a work_id for "
        "full section-by-section detail.*"
    )

    return "\n".join(lines)


def _handle_get_paper(args: dict) -> str:
    """Retrieve full paper details from the local corpus."""
    work_id = args["work_id"]

    if not _CORPUS_AVAILABLE:
        return "Local corpus not available."

    paper = _corpus_get_paper(work_id)
    if not paper:
        return f"Paper '{work_id}' not found in local corpus."

    lines = [
        f"## {paper['title']}",
        f"*{paper['journal']}* ({paper['year']})",
        "",
    ]

    # Evidence metadata
    meta_parts = []
    if paper["evidence_tier"]:
        label = EVIDENCE_TIER_LABELS.get(paper["evidence_tier"], paper["evidence_tier"])
        meta_parts.append(label)
    if paper["study_design"]:
        meta_parts.append(paper["study_design"].replace("_", " ").title())
    if paper["citation_count"] and paper["citation_count"] > 0:
        meta_parts.append(f"cited {paper['citation_count']}×")
    if paper["journal_tier"]:
        meta_parts.append(f"journal tier {paper['journal_tier']}")
    if meta_parts:
        lines.append(f"**Evidence:** {' | '.join(meta_parts)}")
        lines.append("")

    # Subdomains
    if paper["subdomains"]:
        sd_labels = [
            f"{s} ({SUBDOMAIN_DESCRIPTIONS.get(s, '').split(',')[0]})"
            for s in paper["subdomains"]
        ]
        lines.append(f"**Topics:** {', '.join(sd_labels)}")
        lines.append("")

    # Links
    if paper["pubmed_url"]:
        lines.append(f"PubMed: {paper['pubmed_url']}")
    if paper["doi_url"]:
        lines.append(f"DOI: {paper['doi_url']}")
    lines.append("")

    # MeSH and keywords
    if paper["mesh_terms"]:
        lines.append(f"**MeSH:** {', '.join(paper['mesh_terms'][:20])}")
    if paper["keywords"]:
        lines.append(f"**Keywords:** {', '.join(paper['keywords'][:20])}")
    if paper["mesh_terms"] or paper["keywords"]:
        lines.append("")

    # Abstract
    if paper["abstract"]:
        lines.append("### Abstract\n")
        lines.append(paper["abstract"][:2000])
        lines.append("")

    # Sections
    sections = paper.get("sections", {})
    for section_type in ("introduction", "methods", "results", "discussion", "conclusion"):
        if section_type in sections:
            content = sections[section_type]
            display = content[:1500] + ("…" if len(content) > 1500 else "")
            lines.append(f"### {section_type.title()}\n")
            lines.append(display)
            lines.append("")

    # Other section types
    for st, content in sections.items():
        if st not in ("introduction", "methods", "results", "discussion", "conclusion"):
            display = content[:800] + ("…" if len(content) > 800 else "")
            lines.append(f"### {st.replace('_', ' ').title()}\n")
            lines.append(display)
            lines.append("")

    return "\n".join(lines)


async def _handle_send_email(args: dict) -> str:
    """Send an email via Resend REST API."""
    if not _RESEND_API_KEY:
        return (
            "Error: RESEND_API_KEY not set. Set it in your environment:\n"
            "  export RESEND_API_KEY=re_xxxx\n"
            "Get a key at https://resend.com/api-keys"
        )

    to = args["to"]
    subject = args["subject"]
    body = args["body"]
    sender = args.get("from_", "").strip() or RESEND_DEFAULT_FROM

    payload = {
        "from": sender,
        "to": [to],
        "subject": subject,
        "text": body,
    }

    resp = await _client().post(
        f"{RESEND_API}/emails",
        json=payload,
        headers={
            "Authorization": f"Bearer {_RESEND_API_KEY}",
            "Content-Type": "application/json",
        },
    )

    if resp.status_code == 200:
        data = resp.json()
        email_id = data.get("id", "unknown")
        return f"Email sent ✓\n  From: {sender}\n  To: {to}\n  Subject: {subject}\n  Resend ID: {email_id}"
    else:
        try:
            detail = resp.json()
        except Exception:
            detail = {"message": resp.text}
        msg = detail.get("message", resp.text)
        return f"Email failed (HTTP {resp.status_code}): {msg}"


# ── Entry point ─────────────────────────────────────────────────────────────

def run():
    """Run the MCP server on stdio."""
    async def _main():
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())
    asyncio.run(_main())


if __name__ == "__main__":
    run()
