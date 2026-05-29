"""Offline sidecar index over the curated image bank (images ⋈ labels).

Flattens the live bank into a small JSON file of per-image records used by
``ImageBankRetriever``. Excludes rows whose file is missing or too small to be
a real figure (catches the 0-byte / 1x1 px artifacts found in the bank).
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import tempfile
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
            if not path.is_absolute():
                path = self._db_path.parent / path
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

        tmp_dir = self._index_path.parent
        fd, tmp_name = tempfile.mkstemp(dir=tmp_dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(records, f)
            os.replace(tmp_name, self._index_path)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
        return records

    def load(self) -> list[dict[str, Any]] | None:
        if not self._index_path.is_file():
            return None
        return json.loads(self._index_path.read_text(encoding="utf-8"))


if __name__ == "__main__":  # manual rebuild: python -m caseprep.image_bank.image_index
    idx = ImageIndex()
    built = idx.build()
    print(f"Indexed {len(built)} images → {idx._index_path}")
