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


def test_build_excludes_non_neurosurgical(tmp_path):
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
    good.write_bytes(b"\xff\xd8\xff" + b"x" * 5000)
    conn.execute(
        "INSERT INTO images VALUES (?,?,?,?,?,?)",
        ("NSG_Fig1", "spine", "PMC10", "10", "Valid neurosurgical figure", str(good)),
    )
    conn.execute(
        "INSERT INTO labels VALUES (?,?,?,?,?,?,?,?,?)",
        ("NSG_Fig1", "MRI", 5, "lumbar", "HNP", "discectomy", "summary", "mri,spine", 1),
    )
    # Non-neurosurgical row — same good file, is_neurosurgical=0
    conn.execute(
        "INSERT INTO images VALUES (?,?,?,?,?,?)",
        ("GEN_Fig1", "general", "PMC11", "11", "General surgery figure", str(good)),
    )
    conn.execute(
        "INSERT INTO labels VALUES (?,?,?,?,?,?,?,?,?)",
        ("GEN_Fig1", "CT", 3, "abdomen", "appendicitis", "appendectomy", "summary", "ct", 0),
    )
    conn.commit()
    conn.close()

    out = tmp_path / "image_index.json"
    records = ImageIndex(db_path=db, index_path=out).build()
    fig_ids = [r["fig_id"] for r in records]
    assert "NSG_Fig1" in fig_ids
    assert "GEN_Fig1" not in fig_ids
