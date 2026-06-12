"""Group figure-bearing textbook EvidenceRecords by their section for the PDF
exporter. Caption = book citation + the page's figure caption."""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable


def figures_for_sections(
    evidence: Iterable,
    *,
    max_per_section: int = 2,
) -> dict:
    out: dict[str, list] = defaultdict(list)
    for record in evidence:
        if getattr(record, "source", "") != "textbook":
            continue
        metadata = getattr(record, "metadata", {}) or {}
        path = metadata.get("figure_path")
        if not path:
            continue
        section = metadata.get("section") or "Evidence"
        if len(out[section]) >= max_per_section:
            continue
        caption = " — ".join(
            part
            for part in (metadata.get("citation"), metadata.get("caption"))
            if part
        )
        out[section].append((path, caption))
    return dict(out)
