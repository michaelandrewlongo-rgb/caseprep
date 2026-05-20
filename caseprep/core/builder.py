"""Initial transport-agnostic CasePrep core builder.

This slice intentionally stops at classification plus normalized retrieval.
Synthesis, provenance validation, pure rendering, and persistence land in later
refactor slices.
"""

from __future__ import annotations

import inspect
from collections.abc import Iterable
from dataclasses import dataclass, replace
from typing import Any, Protocol

from caseprep.profile_classifier import build_keywords, classify_profile
from caseprep.provenance import build_core_provenance, enforce_provenance
from caseprep.retrievers.corpus import CorpusRetriever
from caseprep.retrievers.pubmed import PubMedRetriever
from caseprep.retrievers.radiology import RadiologyRetriever
from caseprep.synthesis.section_synthesis import synthesize_sections

from .contracts import BuildCasePlanRequest, BuildCasePlanResult, EvidenceRecord
from .errors import CasePrepError


class PubMedRetrieverProtocol(Protocol):
    async def retrieve(
        self,
        query: str,
        *,
        max_results: int = 10,
        filter_type: str | None = None,
        include_abstracts: bool = True,
    ) -> list[EvidenceRecord]:
        ...


class RadiologyRetrieverProtocol(Protocol):
    async def retrieve(
        self,
        query: str,
        *,
        max_results: int = 5,
        modality: str | None = None,
    ) -> list[EvidenceRecord]:
        ...


class CorpusRetrieverProtocol(Protocol):
    def retrieve(
        self,
        fts_query: str,
        *,
        subdomain: str | None = None,
        top_n: int = 8,
    ) -> list[EvidenceRecord]:
        ...


@dataclass(frozen=True)
class CoreRetrieverSet:
    """Provider set used by the core builder."""

    pubmed: PubMedRetrieverProtocol
    radiology: RadiologyRetrieverProtocol
    corpus: CorpusRetrieverProtocol


def default_core_retrievers() -> CoreRetrieverSet:
    """Create the default provider-backed core retrievers."""
    return CoreRetrieverSet(
        pubmed=PubMedRetriever(),
        radiology=RadiologyRetriever(),
        corpus=CorpusRetriever(),
    )


async def _maybe_await(value):
    if inspect.isawaitable(value):
        return await value
    return value


def _build_enriched_query(topic: str, terms: Iterable[str]) -> str:
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


def _tag_evidence(
    records: list[EvidenceRecord],
    *,
    axis: str,
    query: str,
) -> list[EvidenceRecord]:
    tagged: list[EvidenceRecord] = []
    for record in records:
        metadata = dict(record.metadata)
        metadata["axis"] = axis
        metadata["query"] = query
        tagged.append(replace(record, metadata=metadata))
    return tagged


def _source_counts(records: list[EvidenceRecord]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        counts[record.source] = counts.get(record.source, 0) + 1
    return counts


async def build_core_case_plan(
    request: BuildCasePlanRequest,
    *,
    retrievers: CoreRetrieverSet | None = None,
) -> BuildCasePlanResult:
    """Build the first real core result for shadow-mode comparison."""
    provider_set = retrievers or default_core_retrievers()
    classification = classify_profile(
        request.topic,
        profile_hint=request.profile_hint,
    )
    profile_keywords = build_keywords(classification.profile)
    max_per = min(request.max_per_category, 10)

    anatomy_query = _build_enriched_query(
        request.topic,
        profile_keywords["anatomy"][:5],
    )
    pubmed_axes: list[tuple[str, str, str | None]] = [
        ("Anatomy / Relevant Structures", anatomy_query, None),
        ("Outcomes / Evidence", f"{request.topic} outcomes", "therapy"),
        (
            "Surgical Technique",
            f"{request.topic} surgical technique approach",
            None,
        ),
        ("Complications", f"{request.topic} complications adverse", "etiology"),
        ("Reviews / Landmarks", request.topic, "systematic_review"),
    ]

    evidence: list[EvidenceRecord] = []
    warnings: list[str] = []

    for label, query, filter_type in pubmed_axes:
        try:
            records = await provider_set.pubmed.retrieve(
                query,
                max_results=max_per,
                filter_type=filter_type,
                include_abstracts=True,
            )
        except CasePrepError as exc:
            warnings.append(f"{label}: {exc}")
            continue
        evidence.extend(_tag_evidence(records, axis=label, query=query))

    radiology_query = f"{request.topic} radiology imaging"
    try:
        radiology_records = await provider_set.radiology.retrieve(
            radiology_query,
            max_results=min(max_per, 5),
            modality=None,
        )
    except CasePrepError as exc:
        warnings.append(f"Radiology: {exc}")
    else:
        evidence.extend(
            _tag_evidence(
                radiology_records,
                axis="Radiology",
                query=radiology_query,
            )
        )

    try:
        corpus_records = await _maybe_await(
            provider_set.corpus.retrieve(
                request.topic,
                subdomain=classification.profile,
                top_n=max_per,
            )
        )
    except CasePrepError as exc:
        warnings.append(f"Corpus: {exc}")
    else:
        evidence.extend(
            _tag_evidence(
                corpus_records,
                axis="Corpus",
                query=request.topic,
            )
        )

    structured: dict[str, Any] = {
        "profile": {
            "name": classification.profile,
            "confidence": classification.confidence,
            "matched_term": classification.matched_term,
            "source": classification.source,
        },
        "retrieval": {
            "pubmed_axes": [label for label, _, _ in pubmed_axes],
            "evidence_count": len(evidence),
            "sources": _source_counts(evidence),
        },
    }
    sections = synthesize_sections(request.topic, evidence)
    structured["sections"] = [section.to_dict() for section in sections]
    provenance = build_core_provenance(
        structured=structured,
        evidence=evidence,
        sections=sections,
    )
    warnings.extend(
        enforce_provenance(
            structured=structured,
            provenance=provenance,
            evidence=evidence,
            required_fields=["profile", "retrieval", "sections"],
        )
    )

    lines = [
        f"# Core Case Plan - {request.topic}",
        "",
        "## Profile",
        f"- Profile: {classification.profile}",
        f"- Source: {classification.source}",
        "",
        "## Evidence Retrieved",
        f"- Total records: {len(evidence)}",
    ]
    for source, count in sorted(structured["retrieval"]["sources"].items()):
        lines.append(f"- {source}: {count}")
    if sections:
        lines.extend(["", "## Draft Sections"])
        for section in sections:
            lines.extend([f"### {section.title}", section.body])
    if warnings:
        lines.extend(["", "## Warnings"])
        lines.extend(f"- {warning}" for warning in warnings)

    return BuildCasePlanResult(
        topic=request.topic,
        markdown="\n".join(lines),
        output_dir=request.resolved_output_dir(),
        mode="core",
        evidence=evidence,
        provenance=provenance,
        structured=structured,
        warnings=warnings,
    )
