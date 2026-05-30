# Image-Bank → Thrombectomy Briefing Integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bind curated image-bank figures to the thrombectomy briefing's existing `images_to_display_in_or` specs via a deterministic structured+lexical matcher, with full source provenance and inline rendering.

**Architecture:** An offline `ImageIndex` flattens the live `bank.db` (images ⋈ labels) into a fast sidecar. A pure `ImageBankRetriever` matches a spec string → ranked images by modality-hint prefilter + cluster restriction + token-overlap score + threshold. A binding step in `core/builder.py` attaches matches to `schema["imaging_review"]["bound_images"]` and appends `ProvenanceRecord`s (`value_status="generated"`, source = PMCID/PMID). The imaging renderer emits each spec with its matched images + PMC source links beneath.

**Tech Stack:** Python 3.10+, stdlib `sqlite3`/`json`/`re`, pytest. No new dependencies (no embedding model).

**Reference spec:** `docs/superpowers/specs/2026-05-29-image-bank-briefing-integration-design.md`

---

## File Structure

- **Create** `caseprep/image_bank/image_index.py` — `ImageIndex` (build/load the sidecar over `bank.db`).
- **Create** `caseprep/retrievers/image_bank.py` — `ImageMatch`, modality-hint parser, `ImageBankRetriever`.
- **Create** `caseprep/image_binding.py` — `bind_images_to_schema(schema, retriever)` → mutates schema + returns provenance records.
- **Modify** `caseprep/core/builder.py` (~line 730–822) — call binding after schema build, extend provenance before render.
- **Modify** `caseprep/schema.py` (`_render_imaging`, `_render_thrombectomy_imaging`, ~1834–1920) — render bound images.
- **Modify** `caseprep/renderers/html.py` — render bound images for HTML output.
- **Create** tests: `tests/test_image_index.py`, `tests/test_image_bank_retriever.py`, `tests/test_image_binding.py`, `tests/test_image_render.py`.

### Shared types & constants (defined in Task 2, referenced everywhere)

```python
# caseprep/retrievers/image_bank.py
THROMBECTOMY_CLUSTERS = frozenset({
    "stroke_thrombectomy",
    "carotid_cervical_vascular",
    "intracranial_atherosclerosis",
    "general_neurointerventional",
})

# spec keyword (lowercase) → bank `modality` label value
MODALITY_HINTS = {
    "ncct": "CT", "noncontrast": "CT", "non-contrast": "CT", "ct": "CT",
    "ctp": "CT", "perfusion": "CT",
    "cta": "CT_angiography",
    "dsa": "DSA/angiogram", "angiogram": "DSA/angiogram", "angio": "DSA/angiogram",
    "fluoroscopic": "DSA/angiogram", "fluoroscopy": "DSA/angiogram",
    "mri": "MRI", "dwi": "MRI", "adc": "MRI", "flair": "MRI",
    "mra": "MR_angiography",
}

# tokens that carry no discriminating signal for matching
SPEC_STOPWORDS = frozenset({
    "image", "images", "view", "views", "axial", "coronal", "sagittal",
    "show", "showing", "display", "displayed", "and", "or", "the", "a", "an",
    "of", "in", "for", "with", "if", "to", "from", "on", "map", "maps",
})

MIN_SCORE = 0.20   # conservative: precision over recall
DEFAULT_TOP_K = 2
```

```python
# caseprep/retrievers/image_bank.py
from dataclasses import dataclass, field

@dataclass
class ImageMatch:
    fig_id: str
    local_path: str
    caption: str
    pmcid: str
    pmid: str
    score: float
    matched_spec: str
    matched_tokens: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "fig_id": self.fig_id,
            "local_path": self.local_path,
            "caption": self.caption,
            "pmcid": self.pmcid,
            "pmid": self.pmid,
            "score": round(self.score, 4),
            "matched_spec": self.matched_spec,
            "matched_tokens": list(self.matched_tokens),
        }
```

The index record (one per usable bank row), produced by `ImageIndex`:

```python
{
  "fig_id": str, "local_path": str, "pmcid": str, "pmid": str,
  "cluster": str, "modality": str, "caption": str,
  "surgical_usefulness": int,
  "tokens": list[str],   # tokenized caption_summary + keywords + anatomy + procedure
}
```

---

## Task 1: `ImageIndex` — build & load the sidecar

**Files:**
- Create: `caseprep/image_bank/image_index.py`
- Test: `tests/test_image_index.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_image_index.py
import json
import sqlite3
from pathlib import Path

from caseprep.image_bank.image_index import ImageIndex, _tokenize


def _make_bank(tmp_path: Path) -> Path:
    db = tmp_path / "bank.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE images (fig_id TEXT, cluster TEXT, pmcid TEXT, pmid TEXT, "
        "caption TEXT, local_path TEXT)"
    )
    conn.execute(
        "CREATE TABLE labels (fig_id TEXT, modality TEXT, surgical_usefulness INTEGER, "
        "anatomy TEXT, pathology TEXT, procedure TEXT, caption_summary TEXT, "
        "keywords TEXT, is_neurosurgical INTEGER)"
    )
    good = tmp_path / "good.jpg"
    good.write_bytes(b"\xff\xd8\xff" + b"x" * 5000)        # plausible jpeg
    tiny = tmp_path / "tiny.jpg"
    tiny.write_bytes(b"x" * 100)                            # too small → excluded
    rows = [
        ("PMC1_Fig1", "stroke_thrombectomy", "PMC1", "111",
         "Final DSA after thrombectomy", str(good)),
        ("PMC2_Fig1", "stroke_thrombectomy", "PMC2", "222",
         "Tiny broken", str(tiny)),
        ("PMC3_Fig1", "stroke_thrombectomy", "PMC3", "333",
         "Missing file", str(tmp_path / "nope.jpg")),
    ]
    conn.executemany("INSERT INTO images VALUES (?,?,?,?,?,?)", rows)
    conn.executemany(
        "INSERT INTO labels VALUES (?,?,?,?,?,?,?,?,?)",
        [
            ("PMC1_Fig1", "DSA/angiogram", 5, "MCA", "LVO", "thrombectomy",
             "Final DSA showing TICI 3 recanalization", "dsa,tici,thrombectomy", 1),
            ("PMC2_Fig1", "CT", 4, "", "", "", "broken", "ct", 1),
            ("PMC3_Fig1", "CT", 4, "", "", "", "missing", "ct", 1),
        ],
    )
    conn.commit()
    conn.close()
    return db


def test_tokenize_lowercases_and_splits():
    assert _tokenize("Final DSA, showing TICI-3!") == {"final", "dsa", "showing", "tici", "3"}


def test_build_excludes_tiny_and_missing_files(tmp_path):
    db = _make_bank(tmp_path)
    out = tmp_path / "image_index.json"
    idx = ImageIndex(db_path=db, index_path=out)
    records = idx.build()
    # Only the good file survives (tiny + missing dropped)
    assert [r["fig_id"] for r in records] == ["PMC1_Fig1"]
    assert out.exists()
    rec = records[0]
    assert rec["modality"] == "DSA/angiogram"
    assert rec["pmcid"] == "PMC1"
    assert "tici" in rec["tokens"]


def test_load_returns_built_records(tmp_path):
    db = _make_bank(tmp_path)
    out = tmp_path / "image_index.json"
    ImageIndex(db_path=db, index_path=out).build()
    loaded = ImageIndex(db_path=db, index_path=out).load()
    assert loaded is not None
    assert loaded[0]["fig_id"] == "PMC1_Fig1"


def test_load_missing_index_returns_none(tmp_path):
    idx = ImageIndex(db_path=tmp_path / "bank.db", index_path=tmp_path / "none.json")
    assert idx.load() is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_image_index.py -v`
Expected: FAIL — `ModuleNotFoundError: caseprep.image_bank.image_index`

- [ ] **Step 3: Write minimal implementation**

```python
# caseprep/image_bank/image_index.py
"""Offline sidecar index over the curated image bank (images ⋈ labels).

Flattens the live bank into a small JSON file of per-image records used by
``ImageBankRetriever``. Excludes rows whose file is missing or too small to be
a real figure (catches the 0-byte / 1x1 px artifacts found in the bank).
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

BANK_DIR = Path(__file__).parent.resolve()
DEFAULT_DB_PATH = BANK_DIR / "bank.db"
DEFAULT_INDEX_PATH = BANK_DIR / "image_index.json"

MIN_FILE_BYTES = 2048  # smaller than this is a placeholder/broken figure

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> set[str]:
    return set(_TOKEN_RE.findall((text or "").lower()))


class ImageIndex:
    def __init__(
        self,
        *,
        db_path: Path = DEFAULT_DB_PATH,
        index_path: Path = DEFAULT_INDEX_PATH,
    ) -> None:
        self._db_path = Path(db_path)
        self._index_path = Path(index_path)

    def build(self) -> list[dict[str, Any]]:
        conn = sqlite3.connect(str(self._db_path))
        try:
            rows = conn.execute(
                """
                SELECT i.fig_id, i.cluster, i.pmcid, i.pmid, i.caption, i.local_path,
                       l.modality, l.surgical_usefulness, l.anatomy, l.procedure,
                       l.caption_summary, l.keywords
                FROM images i JOIN labels l ON i.fig_id = l.fig_id
                WHERE l.is_neurosurgical = 1
                """
            ).fetchall()
        finally:
            conn.close()

        records: list[dict[str, Any]] = []
        for (fig_id, cluster, pmcid, pmid, caption, local_path, modality,
             usefulness, anatomy, procedure, caption_summary, keywords) in rows:
            path = Path(local_path or "")
            if not path.is_file() or path.stat().st_size < MIN_FILE_BYTES:
                continue
            token_text = " ".join(
                str(x or "") for x in (caption_summary, keywords, anatomy, procedure)
            )
            records.append({
                "fig_id": fig_id,
                "local_path": str(local_path),
                "pmcid": str(pmcid or ""),
                "pmid": str(pmid or ""),
                "cluster": str(cluster or ""),
                "modality": str(modality or ""),
                "caption": str(caption_summary or caption or ""),
                "surgical_usefulness": int(usefulness or 0),
                "tokens": sorted(_tokenize(token_text)),
            })

        self._index_path.write_text(json.dumps(records), encoding="utf-8")
        return records

    def load(self) -> list[dict[str, Any]] | None:
        if not self._index_path.is_file():
            return None
        return json.loads(self._index_path.read_text(encoding="utf-8"))


if __name__ == "__main__":  # manual rebuild: python -m caseprep.image_bank.image_index
    built = ImageIndex().build()
    print(f"Indexed {len(built)} images → {ImageIndex()._index_path}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_image_index.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add caseprep/image_bank/image_index.py tests/test_image_index.py
git commit -m "feat(image-bank): offline ImageIndex sidecar over bank.db"
```

---

## Task 2: Modality-hint parser + `ImageMatch` type

**Files:**
- Create: `caseprep/retrievers/image_bank.py` (types + parser only; retriever added in Task 3)
- Test: `tests/test_image_bank_retriever.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_image_bank_retriever.py
from caseprep.retrievers.image_bank import (
    ImageMatch, parse_modality_hint, spec_tokens,
)


def test_parse_modality_hint_ncct_is_ct():
    assert parse_modality_hint("NCCT axial ASPECTS/hemorrhage-exclusion images.") == "CT"


def test_parse_modality_hint_dsa():
    assert parse_modality_hint("Planned DSA working projections for access route.") == "DSA/angiogram"


def test_parse_modality_hint_none_when_unknown():
    assert parse_modality_hint("Anatomic relationships overview.") is None


def test_spec_tokens_drops_stopwords():
    toks = spec_tokens("NCCT axial ASPECTS/hemorrhage-exclusion images.")
    assert "axial" not in toks and "images" not in toks
    assert "ncct" in toks and "aspects" in toks


def test_image_match_to_dict_rounds_score():
    m = ImageMatch("f", "/p.jpg", "cap", "PMC1", "1", 0.123456, "spec", ["a"])
    assert m.to_dict()["score"] == 0.1235
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_image_bank_retriever.py -v`
Expected: FAIL — `ModuleNotFoundError: caseprep.retrievers.image_bank`

- [ ] **Step 3: Write minimal implementation**

```python
# caseprep/retrievers/image_bank.py
"""Deterministic image-bank retriever: spec string → ranked bank images.

Matching is structured (modality hint + cluster prefilter) plus lexical
token-overlap — no embedding model — so every match is explainable via the
exact ``matched_tokens`` it scored on.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

THROMBECTOMY_CLUSTERS = frozenset({
    "stroke_thrombectomy",
    "carotid_cervical_vascular",
    "intracranial_atherosclerosis",
    "general_neurointerventional",
})

MODALITY_HINTS = {
    "ncct": "CT", "noncontrast": "CT", "non-contrast": "CT", "ct": "CT",
    "ctp": "CT", "perfusion": "CT",
    "cta": "CT_angiography",
    "dsa": "DSA/angiogram", "angiogram": "DSA/angiogram", "angio": "DSA/angiogram",
    "fluoroscopic": "DSA/angiogram", "fluoroscopy": "DSA/angiogram",
    "mri": "MRI", "dwi": "MRI", "adc": "MRI", "flair": "MRI",
    "mra": "MR_angiography",
}

SPEC_STOPWORDS = frozenset({
    "image", "images", "view", "views", "axial", "coronal", "sagittal",
    "show", "showing", "display", "displayed", "and", "or", "the", "a", "an",
    "of", "in", "for", "with", "if", "to", "from", "on", "map", "maps",
})

MIN_SCORE = 0.20
DEFAULT_TOP_K = 2

_TOKEN_RE = re.compile(r"[a-z0-9]+")


@dataclass
class ImageMatch:
    fig_id: str
    local_path: str
    caption: str
    pmcid: str
    pmid: str
    score: float
    matched_spec: str
    matched_tokens: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "fig_id": self.fig_id,
            "local_path": self.local_path,
            "caption": self.caption,
            "pmcid": self.pmcid,
            "pmid": self.pmid,
            "score": round(self.score, 4),
            "matched_spec": self.matched_spec,
            "matched_tokens": list(self.matched_tokens),
        }


def parse_modality_hint(spec: str) -> str | None:
    """Return the bank modality implied by a spec string, or None."""
    tokens = _TOKEN_RE.findall((spec or "").lower())
    for tok in tokens:
        if tok in MODALITY_HINTS:
            return MODALITY_HINTS[tok]
    return None


def spec_tokens(spec: str) -> set[str]:
    """Content tokens of a spec, minus stopwords and pure modality tokens."""
    raw = set(_TOKEN_RE.findall((spec or "").lower()))
    return {t for t in raw if t not in SPEC_STOPWORDS and t not in MODALITY_HINTS}


__all__ = [
    "ImageMatch", "parse_modality_hint", "spec_tokens",
    "THROMBECTOMY_CLUSTERS", "MIN_SCORE", "DEFAULT_TOP_K",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_image_bank_retriever.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add caseprep/retrievers/image_bank.py tests/test_image_bank_retriever.py
git commit -m "feat(retrievers): image-bank match types + modality-hint parser"
```

---

## Task 3: `ImageBankRetriever` — rank images for a spec

**Files:**
- Modify: `caseprep/retrievers/image_bank.py` (append the retriever class)
- Test: `tests/test_image_bank_retriever.py` (append)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_image_bank_retriever.py  (append)
from caseprep.retrievers.image_bank import ImageBankRetriever


def _index():
    return [
        {"fig_id": "PMC1_F1", "local_path": "/a.jpg", "pmcid": "PMC1", "pmid": "1",
         "cluster": "stroke_thrombectomy", "modality": "DSA/angiogram",
         "caption": "Final DSA showing TICI 3", "surgical_usefulness": 5,
         "tokens": ["dsa", "tici", "recanalization", "thrombectomy"]},
        {"fig_id": "PMC2_F1", "local_path": "/b.jpg", "pmcid": "PMC2", "pmid": "2",
         "cluster": "stroke_thrombectomy", "modality": "CT",
         "caption": "NCCT ASPECTS", "surgical_usefulness": 4,
         "tokens": ["ncct", "aspects", "hemorrhage", "exclusion"]},
        {"fig_id": "PMC9_F1", "local_path": "/z.jpg", "pmcid": "PMC9", "pmid": "9",
         "cluster": "spine_trauma", "modality": "CT",
         "caption": "Off-topic", "surgical_usefulness": 5,
         "tokens": ["odontoid", "fracture"]},
    ]


def test_retrieve_binds_aspects_to_ct_image():
    r = ImageBankRetriever(index=_index())
    matches = r.retrieve("NCCT axial ASPECTS/hemorrhage-exclusion images.", top_k=2)
    assert matches and matches[0].fig_id == "PMC2_F1"
    assert matches[0].pmcid == "PMC2"
    assert "aspects" in matches[0].matched_tokens


def test_retrieve_excludes_off_cluster_images():
    r = ImageBankRetriever(index=_index())
    matches = r.retrieve("NCCT axial ASPECTS images.", top_k=5)
    assert all(m.fig_id != "PMC9_F1" for m in matches)


def test_retrieve_below_threshold_returns_empty():
    r = ImageBankRetriever(index=_index())
    assert r.retrieve("unrelated thoracic deformity correction.", top_k=2) == []


def test_retrieve_none_index_returns_empty():
    assert ImageBankRetriever(index=None).retrieve("NCCT ASPECTS images.") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_image_bank_retriever.py -v`
Expected: FAIL — `ImportError: cannot import name 'ImageBankRetriever'`

- [ ] **Step 3: Write minimal implementation**

```python
# caseprep/retrievers/image_bank.py  (append before __all__, then add to __all__)

class ImageBankRetriever:
    """Rank curated bank images for a single image-spec string.

    Pure/deterministic: no network, no model. ``index`` is the list produced by
    ``ImageIndex.load()``; ``None`` (missing sidecar) yields ``[]`` so callers
    degrade gracefully, mirroring SemanticCorpusRetriever's contract.
    """

    def __init__(
        self,
        *,
        index: list[dict] | None,
        clusters: frozenset[str] = THROMBECTOMY_CLUSTERS,
        min_score: float = MIN_SCORE,
    ) -> None:
        self._index = index
        self._clusters = clusters
        self._min_score = min_score

    def retrieve(self, spec: str, *, top_k: int = DEFAULT_TOP_K) -> list[ImageMatch]:
        if not self._index:
            return []
        want_tokens = spec_tokens(spec)
        if not want_tokens:
            return []
        modality = parse_modality_hint(spec)

        # Cluster prefilter.
        pool = [r for r in self._index if r["cluster"] in self._clusters]
        # Modality prefilter (relax if it would empty the pool).
        if modality:
            narrowed = [r for r in pool if r["modality"] == modality]
            if narrowed:
                pool = narrowed

        scored: list[ImageMatch] = []
        for rec in pool:
            cand = set(rec["tokens"])
            overlap = want_tokens & cand
            if not overlap:
                continue
            score = len(overlap) / len(want_tokens)
            if score < self._min_score:
                continue
            scored.append(ImageMatch(
                fig_id=rec["fig_id"],
                local_path=rec["local_path"],
                caption=rec["caption"],
                pmcid=rec["pmcid"],
                pmid=rec["pmid"],
                score=score,
                matched_spec=spec,
                matched_tokens=sorted(overlap),
            ))

        # Rank: score desc, then surgical_usefulness desc, then fig_id for stability.
        usefulness = {r["fig_id"]: r["surgical_usefulness"] for r in pool}
        scored.sort(key=lambda m: (-m.score, -usefulness.get(m.fig_id, 0), m.fig_id))
        return scored[:top_k]
```

Update `__all__` to include `"ImageBankRetriever"`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_image_bank_retriever.py -v`
Expected: PASS (9 tests total)

- [ ] **Step 5: Commit**

```bash
git add caseprep/retrievers/image_bank.py tests/test_image_bank_retriever.py
git commit -m "feat(retrievers): ImageBankRetriever deterministic spec→image ranking"
```

---

## Task 4: Binding step — attach images to schema + provenance

**Files:**
- Create: `caseprep/image_binding.py`
- Test: `tests/test_image_binding.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_image_binding.py
from caseprep.image_binding import bind_images_to_schema
from caseprep.retrievers.image_bank import ImageBankRetriever


def _retriever():
    index = [
        {"fig_id": "PMC2_F1", "local_path": "/b.jpg", "pmcid": "PMC2", "pmid": "2",
         "cluster": "stroke_thrombectomy", "modality": "CT",
         "caption": "NCCT ASPECTS", "surgical_usefulness": 4,
         "tokens": ["ncct", "aspects", "hemorrhage", "exclusion"]},
    ]
    return ImageBankRetriever(index=index)


def test_bind_attaches_matches_and_provenance():
    schema = {"imaging_review": {"images_to_display_in_or": [
        "NCCT axial ASPECTS/hemorrhage-exclusion images.",
        "Unrelated thoracic deformity correction.",
    ]}}
    records = bind_images_to_schema(schema, _retriever())

    bound = schema["imaging_review"]["bound_images"]
    assert len(bound) == 1
    assert bound[0]["pmcid"] == "PMC2"
    assert bound[0]["matched_spec"].startswith("NCCT")

    assert len(records) == 1
    rec = records[0]
    assert rec.field_path == "imaging_review.bound_images[0]"
    assert rec.value_status == "generated"
    assert "PMC2" in rec.source_ids and "pmid-2" in rec.source_ids
    assert "aspects" in rec.notes


def test_bind_no_section_is_noop():
    schema = {"topic": "x"}
    assert bind_images_to_schema(schema, _retriever()) == []


def test_bind_empty_retriever_attaches_nothing():
    schema = {"imaging_review": {"images_to_display_in_or": ["NCCT ASPECTS images."]}}
    records = bind_images_to_schema(schema, ImageBankRetriever(index=None))
    assert records == []
    assert schema["imaging_review"].get("bound_images", []) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_image_binding.py -v`
Expected: FAIL — `ModuleNotFoundError: caseprep.image_binding`

- [ ] **Step 3: Write minimal implementation**

```python
# caseprep/image_binding.py
"""Bind curated image-bank figures to a case schema's image specs.

Reads ``imaging_review.images_to_display_in_or`` spec strings, asks the
ImageBankRetriever for matches, attaches them to
``imaging_review.bound_images``, and returns ProvenanceRecords marking each
bound image as ``generated`` with its source PMCID/PMID.
"""
from __future__ import annotations

from typing import Any

from caseprep.core import ProvenanceRecord
from caseprep.retrievers.image_bank import ImageBankRetriever

SPEC_SECTION = "imaging_review"
SPEC_KEY = "images_to_display_in_or"


def bind_images_to_schema(
    schema: dict[str, Any],
    retriever: ImageBankRetriever,
    *,
    top_k: int = 2,
) -> list[ProvenanceRecord]:
    section = schema.get(SPEC_SECTION)
    if not isinstance(section, dict):
        return []
    specs = section.get(SPEC_KEY) or []
    if not isinstance(specs, list) or not specs:
        return []

    bound: list[dict[str, Any]] = []
    records: list[ProvenanceRecord] = []
    seen: set[str] = set()  # de-dup the same figure across multiple specs

    for spec in specs:
        if not isinstance(spec, str):
            continue
        for match in retriever.retrieve(spec, top_k=top_k):
            if match.fig_id in seen:
                continue
            seen.add(match.fig_id)
            idx = len(bound)
            bound.append(match.to_dict())
            source_ids = [s for s in (match.pmcid, f"pmid-{match.pmid}" if match.pmid else "") if s]
            records.append(ProvenanceRecord(
                field_path=f"{SPEC_SECTION}.bound_images[{idx}]",
                source_ids=source_ids,
                value_status="generated",
                generated_by="caseprep.image_binding",
                notes=(
                    f"matched spec '{match.matched_spec}' via tokens "
                    f"{match.matched_tokens} (score {match.score:.2f})"
                ),
            ))

    if bound:
        section["bound_images"] = bound
    return records


__all__ = ["bind_images_to_schema", "SPEC_SECTION", "SPEC_KEY"]
```

> Note: confirm `ProvenanceRecord` is importable from `caseprep.core` (it is re-exported there — see `caseprep/core/builder.py:24` region and `caseprep/core/contracts.py:158`). If not, import from `caseprep.core.contracts`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_image_binding.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add caseprep/image_binding.py tests/test_image_binding.py
git commit -m "feat: bind image-bank matches to schema with provenance"
```

---

## Task 5: Wire binding into the core builder

**Files:**
- Modify: `caseprep/core/builder.py` (insert after `build_caseprep_schema` ~line 735, before `render_caseprep_files` ~line 822)
- Test: `tests/test_core_builder_image_binding.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_core_builder_image_binding.py
from caseprep.core.builder import _bind_image_bank
from caseprep.retrievers.image_bank import ImageBankRetriever


def test_bind_image_bank_extends_provenance_and_schema():
    schema = {"imaging_review": {"images_to_display_in_or": ["NCCT ASPECTS images."]}}
    provenance: list = []
    retriever = ImageBankRetriever(index=[
        {"fig_id": "PMC2_F1", "local_path": "/b.jpg", "pmcid": "PMC2", "pmid": "2",
         "cluster": "stroke_thrombectomy", "modality": "CT", "caption": "NCCT ASPECTS",
         "surgical_usefulness": 4, "tokens": ["ncct", "aspects"]},
    ])
    _bind_image_bank(schema, provenance, retriever=retriever, warnings=[])
    assert schema["imaging_review"]["bound_images"][0]["pmcid"] == "PMC2"
    assert any(p.field_path.startswith("imaging_review.bound_images") for p in provenance)


def test_bind_image_bank_handles_missing_index(tmp_path):
    schema = {"imaging_review": {"images_to_display_in_or": ["NCCT ASPECTS images."]}}
    provenance: list = []
    warnings: list = []
    # No retriever passed → builder constructs one from a non-existent index.
    _bind_image_bank(schema, provenance, retriever=None, warnings=warnings,
                     index_path=tmp_path / "absent.json")
    assert schema["imaging_review"].get("bound_images", []) == []
    assert provenance == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_core_builder_image_binding.py -v`
Expected: FAIL — `ImportError: cannot import name '_bind_image_bank'`

- [ ] **Step 3: Write minimal implementation**

Add imports near the top of `caseprep/core/builder.py` (with the other `from caseprep...` imports, ~line 24–30):

```python
from caseprep.image_bank.image_index import ImageIndex
from caseprep.image_binding import bind_images_to_schema
from caseprep.retrievers.image_bank import ImageBankRetriever
```

Add this helper (place it just above the function that calls `build_caseprep_schema`, near line 700):

```python
def _bind_image_bank(
    schema: dict[str, Any],
    provenance: list[ProvenanceRecord],
    *,
    retriever: ImageBankRetriever | None,
    warnings: list[str] | None,
    index_path=None,
) -> None:
    """Attach curated image-bank figures to the schema's image specs.

    Best-effort and isolated: any failure leaves the briefing unchanged.
    """
    try:
        if retriever is None:
            kwargs = {"index_path": index_path} if index_path is not None else {}
            index = ImageIndex(**kwargs).load()
            retriever = ImageBankRetriever(index=index)
        records = bind_images_to_schema(schema, retriever)
        provenance.extend(records)
        if not records and warnings is not None:
            warnings.append("Image bank: no images bound (index empty or no matches).")
    except Exception as exc:  # never let image binding break a briefing
        if warnings is not None:
            warnings.append(f"Image bank binding failed: {exc}")
```

Insert the call immediately after the `schema["case"]["evidence"]["clinical_questions"] = [...]` block and before `rendered_files = render_caseprep_files(` (~line 821):

```python
    _bind_image_bank(schema, provenance, retriever=None, warnings=warnings)
```

> `provenance` and `warnings` are already in scope as parameters of this function (see signature ~line 726). `Any` and `ProvenanceRecord` are already imported in this module.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_core_builder_image_binding.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Run the full suite to check no regressions**

Run: `pytest -q`
Expected: PASS (existing tests unaffected; binding is additive + guarded)

- [ ] **Step 6: Commit**

```bash
git add caseprep/core/builder.py tests/test_core_builder_image_binding.py
git commit -m "feat(core): wire image-bank binding into the build pipeline"
```

---

## Task 6: Render bound images (Markdown)

**Files:**
- Modify: `caseprep/schema.py` — add `_render_bound_images` helper; call it in `_render_imaging` (~1861) and `_render_thrombectomy_imaging` (~1917)
- Test: `tests/test_image_render.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_image_render.py
from caseprep.schema import _render_bound_images


def test_render_bound_images_groups_by_spec_with_source_link():
    schema = {"imaging_review": {"bound_images": [
        {"local_path": "/img/a.jpg", "caption": "NCCT ASPECTS", "pmcid": "PMC2",
         "pmid": "2", "score": 0.5, "matched_spec": "NCCT axial ASPECTS images."},
    ]}}
    out = _render_bound_images(schema)
    assert "NCCT ASPECTS" in out
    assert "/img/a.jpg" in out
    assert "PMC2" in out                      # source attribution present
    assert "ncbi.nlm.nih.gov" in out          # clickable PMC link


def test_render_bound_images_empty_when_none():
    assert _render_bound_images({"imaging_review": {}}) == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_image_render.py -v`
Expected: FAIL — `ImportError: cannot import name '_render_bound_images'`

- [ ] **Step 3: Write minimal implementation**

Add to `caseprep/schema.py` (near `_render_imaging`, ~line 1830):

```python
def _render_bound_images(schema: dict[str, Any]) -> str:
    """Render image-bank figures bound to the imaging section, grouped by spec."""
    section = schema.get("imaging_review")
    if not isinstance(section, dict):
        return ""
    bound = section.get("bound_images") or []
    if not bound:
        return ""

    by_spec: dict[str, list[dict[str, Any]]] = {}
    for img in bound:
        by_spec.setdefault(img.get("matched_spec", ""), []).append(img)

    lines: list[str] = ["", "### Prep Images From Image Bank", ""]
    for spec, imgs in by_spec.items():
        lines.append(f"**{spec}**")
        lines.append("")
        for img in imgs:
            caption = img.get("caption", "")
            path = img.get("local_path", "")
            pmcid = img.get("pmcid", "")
            link = (
                f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/"
                if pmcid else ""
            )
            lines.append(f"![{caption}]({path})")
            src = f" — source: [{pmcid}]({link})" if link else ""
            lines.append(f"*{caption}*{src}")
            lines.append("")
    return "\n".join(lines)
```

In `_render_imaging` (the non-thrombectomy branch), append after the "Images To Display In OR" block (after line 1863):

```python
{_render_bound_images(schema)}
```

In `_render_thrombectomy_imaging`, append after the "Images To Display In Angio Suite" block (after line 1919):

```python
{_render_bound_images(schema)}
```

> Both are f-strings ending in `"""`; insert the `{_render_bound_images(schema)}` line just before the closing `"""`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_image_render.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Run the imaging/render-related suites**

Run: `pytest tests/test_renderers.py tests/test_image_render.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add caseprep/schema.py tests/test_image_render.py
git commit -m "feat(render): inline bound image-bank figures in imaging section"
```

---

## Task 7: Render bound images (HTML) + end-to-end smoke

**Files:**
- Modify: `caseprep/renderers/html.py` — render bound images if a resource/imaging HTML section exists
- Test: `tests/test_image_render.py` (append an HTML assertion + an end-to-end binding→render check)

- [ ] **Step 1: Inspect the HTML renderer to find the insertion point**

Run: `grep -nE "def |imaging|<figure|<img|resource" caseprep/renderers/html.py`
Expected: identifies the function that builds the imaging/resource HTML. If the HTML renderer only emits resource links (no per-section imaging HTML), add a small `render_bound_images_html(schema)` function and a unit test for it; do **not** force it into an unrelated section.

- [ ] **Step 2: Write the failing test**

```python
# tests/test_image_render.py  (append)
from caseprep.renderers.html import render_bound_images_html


def test_render_bound_images_html_has_figure_and_link():
    schema = {"imaging_review": {"bound_images": [
        {"local_path": "/img/a.jpg", "caption": "Final DSA", "pmcid": "PMC2",
         "pmid": "2", "score": 0.5, "matched_spec": "Final DSA projections."},
    ]}}
    html = render_bound_images_html(schema)
    assert "<figure" in html
    assert 'src="/img/a.jpg"' in html
    assert "PMC2" in html


def test_render_bound_images_html_empty_when_none():
    assert render_bound_images_html({"imaging_review": {}}) == ""
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_image_render.py -v`
Expected: FAIL — `ImportError: cannot import name 'render_bound_images_html'`

- [ ] **Step 4: Write minimal implementation**

Add to `caseprep/renderers/html.py`:

```python
import html as _html


def render_bound_images_html(schema: dict) -> str:
    """HTML <figure> blocks for image-bank figures bound to the imaging section."""
    section = schema.get("imaging_review")
    if not isinstance(section, dict):
        return ""
    bound = section.get("bound_images") or []
    if not bound:
        return ""
    parts: list[str] = ['<section class="bound-images"><h3>Prep Images From Image Bank</h3>']
    for img in bound:
        caption = _html.escape(str(img.get("caption", "")))
        path = _html.escape(str(img.get("local_path", "")))
        pmcid = _html.escape(str(img.get("pmcid", "")))
        link = (
            f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/" if pmcid else ""
        )
        src_html = (
            f' — source: <a href="{link}">{pmcid}</a>' if link else ""
        )
        parts.append(
            f'<figure><img src="{path}" alt="{caption}">'
            f"<figcaption>{caption}{src_html}</figcaption></figure>"
        )
    parts.append("</section>")
    return "\n".join(parts)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_image_render.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: End-to-end smoke test (binding → markdown render)**

```python
# tests/test_image_render.py  (append)
from caseprep.image_binding import bind_images_to_schema
from caseprep.retrievers.image_bank import ImageBankRetriever
from caseprep.schema import _render_bound_images


def test_binding_then_render_round_trip():
    schema = {"imaging_review": {"images_to_display_in_or": [
        "Planned DSA working projections for final mTICI assessment.",
    ]}}
    retriever = ImageBankRetriever(index=[
        {"fig_id": "PMC1_F1", "local_path": "/d.jpg", "pmcid": "PMC1", "pmid": "1",
         "cluster": "stroke_thrombectomy", "modality": "DSA/angiogram",
         "caption": "Final DSA TICI 3", "surgical_usefulness": 5,
         "tokens": ["dsa", "projections", "mtici", "final"]},
    ])
    bind_images_to_schema(schema, retriever)
    out = _render_bound_images(schema)
    assert "Final DSA TICI 3" in out and "PMC1" in out
```

- [ ] **Step 7: Run full suite**

Run: `pytest -q`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add caseprep/renderers/html.py tests/test_image_render.py
git commit -m "feat(render): HTML figures for bound image-bank images + e2e smoke"
```

---

## Task 8: Build the real index & manual verification

**Files:** none (operational step)

- [ ] **Step 1: Build the index against the real bank**

The live `bank.db` lives in the main checkout (gitignored), not the worktree. Point the builder at it:

Run:
```bash
python -c "from pathlib import Path; from caseprep.image_bank.image_index import ImageIndex; \
p=Path.home()/'projects/caseprep/caseprep/image_bank/bank.db'; \
n=len(ImageIndex(db_path=p, index_path=p.parent/'image_index.json').build()); \
print('indexed', n)"
```
Expected: `indexed <N>` where N is close to 20,296 minus excluded broken/missing files.

- [ ] **Step 2: Spot-check a real thrombectomy spec end-to-end**

Run:
```bash
python -c "from pathlib import Path; from caseprep.image_bank.image_index import ImageIndex; \
from caseprep.retrievers.image_bank import ImageBankRetriever; \
p=Path.home()/'projects/caseprep/caseprep/image_bank'; \
idx=ImageIndex(db_path=p/'bank.db', index_path=p/'image_index.json').load(); \
r=ImageBankRetriever(index=idx); \
[print(m.score, m.modality if hasattr(m,'modality') else '', m.pmcid, m.caption[:70]) \
 for m in r.retrieve('NCCT axial ASPECTS/hemorrhage-exclusion images.', top_k=3)]"
```
Expected: 0–3 CT-modality stroke images with sensible captions and real PMCIDs; no spine/off-topic figures. If results are empty or noisy, tune `MIN_SCORE` in `caseprep/retrievers/image_bank.py` and re-run (document the chosen value).

- [ ] **Step 3: Decide index distribution**

The `image_index.json` is a build artifact over gitignored data. Confirm it is covered by `.gitignore` (the bank and images already are). Add `caseprep/image_bank/image_index.json` to `.gitignore` if not already matched. Commit only the `.gitignore` change if one is needed.

```bash
git add .gitignore && git commit -m "chore: ignore generated image_index.json" || echo "no gitignore change needed"
```

---

## Self-Review

**Spec coverage:**
- Goal 1 (bind images to specs) → Tasks 3–5. ✓
- Goal 2 (traceability/provenance) → Task 4 (`generated` + PMCID/PMID + token notes). ✓
- Goal 3 (inline render MD+HTML) → Tasks 6–7. ✓
- Goal 4 (graceful degradation) → Task 3 (`index=None`→`[]`), Task 5 (`_bind_image_bank` try/except + missing-index path). ✓
- D1 sidecar offline → Task 1 + Task 8. ✓
- D2 deterministic lexical, no embeddings → Tasks 2–3. ✓
- D3 precision over recall → `MIN_SCORE` threshold (Tasks 2–3), tuned in Task 8. ✓
- D4 `generated→verified` flow → Task 4 uses `value_status="generated"`. ✓
- Index hygiene (drop 0-byte/1×1) → Task 1 `MIN_FILE_BYTES`. ✓

**Type consistency:** `ImageMatch` fields (Task 2) match `.to_dict()` keys consumed by binding (Task 4) and renderers (Tasks 6–7). `bound_images` dict shape is identical across producer (Task 4) and consumers (Tasks 6–7). `_bind_image_bank` signature (Task 5) matches its tests.

**Placeholder scan:** none — every code step is complete. Task 7 Step 1 is a genuine inspection step (HTML renderer shape is unknown until read), with a defined fallback (`render_bound_images_html`) so the task is unambiguous either way.
