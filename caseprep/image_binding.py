"""Bind curated image-bank figures to a case schema's image specs.

Reads ``imaging_review.images_to_display_in_or`` spec strings, asks the
ImageBankRetriever for matches, attaches them to
``imaging_review.bound_images``, and returns ProvenanceRecords marking each
bound image as ``generated`` with its source PMCID/PMID.

Contract: image-bank figures are a SEPARATE corpus from the literature
evidence set. The ProvenanceRecords returned here reference figure sources
(PMCID / pmid-N) and are an append-only audit trail for the generated→verified
review flow; they are NOT validated against the literature evidence IDs used by
enforce_provenance. Callers append these records after provenance enforcement.
"""
from __future__ import annotations

from typing import Any

from caseprep.core import ProvenanceRecord
from caseprep.retrievers.image_bank import ImageBankRetriever

SPEC_SECTION = "imaging_review"
SPEC_KEY = "images_to_display_in_or"
BOUND_KEY = "bound_images"


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
                field_path=f"{SPEC_SECTION}.{BOUND_KEY}[{idx}]",
                source_ids=source_ids,
                value_status="generated",
                generated_by="caseprep.image_binding",
                notes=(
                    f"matched spec '{match.matched_spec}' via tokens "
                    f"{match.matched_tokens} (score {match.score:.2f})"
                ),
            ))

    if bound:
        section[BOUND_KEY] = bound
    return records


__all__ = ["bind_images_to_schema", "SPEC_SECTION", "SPEC_KEY", "BOUND_KEY"]
