"""Procedure-aware retrieval query planning."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from caseprep.case_parser import CaseSpec
from caseprep.evidence_packs.thrombectomy import resolve_thrombectomy_pack
from caseprep.procedure_taxonomy import ProcedureFamily
from caseprep.profile_classifier import build_keywords, classify_profile


@dataclass(frozen=True)
class RetrievalAxis:
    id: str
    label: str
    query: str
    filter_type: str | None = None


def resolve_case_evidence_pack(
    case: CaseSpec,
    family: ProcedureFamily | None,
) -> str | None:
    """Return a deterministic evidence-pack ID for specific structured cases."""
    if family is None or family.id != "endovascular_thrombectomy":
        return None
    pack = resolve_thrombectomy_pack(case)
    return pack.id if pack is not None else None


def build_case_queries(
    case: CaseSpec,
    family: ProcedureFamily | None,
) -> list[RetrievalAxis]:
    """Build PubMed/corpus query axes from structured case fields."""
    topic = case.raw_input.strip()
    if family is not None:
        templates = family.retrieval_templates
        review_subject = _review_subject(case, family)
        return [
            RetrievalAxis(
                id="anatomy",
                label="Anatomy / Relevant Structures",
                query=_template_query(templates, "anatomy", topic),
            ),
            RetrievalAxis(
                id="outcomes",
                label="Outcomes / Evidence",
                query=_template_query(templates, "outcomes", f"{topic} outcomes"),
                filter_type="therapy",
            ),
            RetrievalAxis(
                id="technique",
                label="Surgical Technique",
                query=_template_query(
                    templates,
                    "technique",
                    f"{topic} surgical technique approach",
                ),
            ),
            RetrievalAxis(
                id="complications",
                label="Complications",
                query=_template_query(
                    templates,
                    "complications",
                    f"{topic} complications adverse",
                ),
                filter_type="etiology",
            ),
            RetrievalAxis(
                id="reviews",
                label="Reviews / Landmarks",
                query=templates.get("reviews") or f"{review_subject} systematic review",
                filter_type="systematic_review",
            ),
        ]

    profile = case.broad_profile.value or classify_profile(topic).profile
    profile_keywords = build_keywords(profile)
    anatomy_query = _build_enriched_query(topic, profile_keywords["anatomy"][:5])
    return [
        RetrievalAxis(
            id="anatomy",
            label="Anatomy / Relevant Structures",
            query=anatomy_query,
        ),
        RetrievalAxis(
            id="outcomes",
            label="Outcomes / Evidence",
            query=f"{topic} outcomes",
            filter_type="therapy",
        ),
        RetrievalAxis(
            id="technique",
            label="Surgical Technique",
            query=f"{topic} surgical technique approach",
        ),
        RetrievalAxis(
            id="complications",
            label="Complications",
            query=f"{topic} complications adverse",
            filter_type="etiology",
        ),
        RetrievalAxis(
            id="reviews",
            label="Reviews / Landmarks",
            query=topic,
            filter_type="systematic_review",
        ),
    ]


def _template_query(
    templates: Mapping[str, str],
    key: str,
    fallback: str,
) -> str:
    value = templates.get(key)
    if value:
        return value
    return fallback


def _review_subject(case: CaseSpec, family: ProcedureFamily) -> str:
    parts: list[str] = []
    for field in (case.procedure, case.pathology):
        if field.value:
            parts.append(field.value)
    if not parts:
        parts.append(family.display_name)
    return " ".join(_unique(parts))


def _build_enriched_query(topic: str, terms: list[str]) -> str:
    parts = [topic]
    seen = {topic.lower()}
    for term in terms:
        normalized = term.strip()
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        parts.append(normalized)

    query = " ".join(parts)
    if len(query) > 200:
        query = query[:200].rsplit(" ", 1)[0]
    return query


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    unique_items: list[str] = []
    for item in items:
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        unique_items.append(item)
    return unique_items
