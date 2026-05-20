"""Initial transport-agnostic CasePrep core builder.

This slice keeps the core path transport-agnostic while incrementally adding
classification, retrieval, synthesis, provenance validation, rendering, and
persistence seams.
"""

from __future__ import annotations

import inspect
import re
from collections.abc import Iterable
from dataclasses import dataclass, replace
from typing import Any, Protocol

from caseprep.profile_classifier import build_keywords, classify_profile
from caseprep.persistence import CasePrepRunStore, resolve_caseprep_store
from caseprep.provenance import build_core_provenance, enforce_provenance
from caseprep.schema import AXIS_RELEVANCE, build_caseprep_schema, render_caseprep_files
from caseprep.scoring import grade_evidence
from caseprep.retrievers.corpus import CorpusRetriever
from caseprep.retrievers.pubmed import PubMedRetriever
from caseprep.retrievers.radiology import RadiologyRetriever
from caseprep.synthesis.section_synthesis import SectionDraft, synthesize_sections

from .contracts import (
    ArtifactRef,
    BuildCasePlanRequest,
    BuildCasePlanResult,
    EvidenceRecord,
)
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


CORPUS_SUBDOMAIN_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "intracranial_hemorrhage",
        (
            "subdural",
            "chronic subdural",
            "csdh",
            "middle meningeal",
            "mma embolization",
            "intracerebral hemorrhage",
            "intracranial hemorrhage",
            "hematoma",
        ),
    ),
    (
        "aneurysm_sah",
        (
            "aneurysm",
            "subarachnoid",
            "sah",
            "coiling",
            "clipping",
            "vasospasm",
        ),
    ),
    (
        "stroke_thrombectomy",
        (
            "thrombectomy",
            "large vessel occlusion",
            "lvo",
            "ischemic stroke",
            "thrombolysis",
        ),
    ),
    (
        "avm_vascular_malformation",
        (
            "arteriovenous malformation",
            "avm",
            "dural arteriovenous fistula",
            "davf",
            "cavernous malformation",
        ),
    ),
    (
        "carotid_cervical_vascular",
        (
            "carotid",
            "vertebral artery",
            "cervical vascular",
        ),
    ),
    (
        "flow_diversion",
        (
            "flow diversion",
            "flow diverter",
            "pipeline",
            "fred",
            "surpass",
            "web device",
        ),
    ),
    (
        "venous_interventional",
        (
            "venous sinus",
            "iih",
            "cerebral venous thrombosis",
        ),
    ),
    (
        "moyamoya",
        (
            "moyamoya",
            "ec-ic bypass",
            "cerebral revascularization",
        ),
    ),
)

CORPUS_PROFILE_FALLBACKS = {
    "functional": "functional_epilepsy",
    "pediatric": "pediatric_neurointerventional",
    "spine": "spine_interventional",
    "skull_base": "tumor_skull_base",
    "supratentorial_tumor": "tumor_skull_base",
}


def resolve_corpus_subdomain(topic: str, profile: str) -> str | None:
    """Map CasePrep profiles/topics onto local corpus subdomain IDs."""
    normalized_topic = topic.lower()
    for subdomain, keywords in CORPUS_SUBDOMAIN_KEYWORDS:
        if any(keyword in normalized_topic for keyword in keywords):
            return subdomain
    return CORPUS_PROFILE_FALLBACKS.get(profile)


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


def _evidence_year(record: EvidenceRecord) -> str:
    for key in ("pubdate", "year"):
        match = re.search(r"\b\d{4}\b", str(record.metadata.get(key, "")))
        if match:
            return match.group(0)
    return ""


def _evidence_level(record: EvidenceRecord) -> str:
    pub_types = record.metadata.get("pub_types")
    if isinstance(pub_types, list):
        return grade_evidence([str(pub_type) for pub_type in pub_types]).label
    evidence_tier = record.metadata.get("evidence_tier")
    if evidence_tier:
        return str(evidence_tier)
    return ""


def _key_source(record: EvidenceRecord) -> dict[str, str]:
    axis = str(record.metadata.get("axis") or "").strip()
    return {
        "id": record.id,
        "title": record.title,
        "year": _evidence_year(record),
        "evidence_level": _evidence_level(record),
        "relevance": AXIS_RELEVANCE.get(axis, axis.lower() or record.source),
        "verification": "cited",
    }


def _section_body(
    sections: list[SectionDraft],
    section_ids: set[str],
) -> str | None:
    bodies = [
        f"### {section.title}\n\n{section.body}"
        for section in sections
        if section.id in section_ids and section.body.strip()
    ]
    return "\n\n".join(bodies) or None


def _core_literature_summary(markdown: str) -> str:
    return f"## Core Search Appendix\n\n{markdown}"


def _write_core_artifacts(
    *,
    request: BuildCasePlanRequest,
    profile: str,
    evidence: list[EvidenceRecord],
    sections: list[SectionDraft],
    provenance: list[Any],
    markdown: str,
) -> list[ArtifactRef]:
    schema = build_caseprep_schema(request.topic, profile=profile)
    schema["case"]["evidence"]["key_sources"] = [
        _key_source(record) for record in evidence if record.id
    ]
    schema["case"]["evidence"]["clinical_questions"] = [
        f"What operative approach and setup best fit {request.topic}?",
        f"What anatomy and imaging findings should change the plan for {request.topic}?",
        f"What complications and rescue plans are most important for {request.topic}?",
    ]
    corpus_ids = {"corpus"}
    rendered_files = render_caseprep_files(
        schema,
        provenance=provenance,
        literature_summary=_core_literature_summary(markdown),
        anatomy_body=_section_body(
            sections,
            {"anatomy-relevant-structures"} | corpus_ids,
        ),
        operative_body=_section_body(
            sections,
            {"surgical-technique"} | corpus_ids,
        ),
        risk_body=_section_body(
            sections,
            {"complications"} | corpus_ids,
        ),
    )

    output_dir = request.resolved_output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts: list[ArtifactRef] = []
    for filename, content in rendered_files.items():
        path = output_dir / filename
        path.write_text(content, encoding="utf-8")
        artifacts.append(
            ArtifactRef(
                path=path,
                kind="markdown" if filename.endswith(".md") else "data",
                media_type=(
                    "text/markdown"
                    if filename.endswith(".md")
                    else "application/json"
                    if filename.endswith(".json")
                    else "text/yaml"
                    if filename.endswith(".yaml")
                    else None
                ),
                label=filename,
            )
        )
    return artifacts


async def build_core_case_plan(
    request: BuildCasePlanRequest,
    *,
    retrievers: CoreRetrieverSet | None = None,
    store: CasePrepRunStore | None = None,
    run_id: str | None = None,
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

    corpus_subdomain = resolve_corpus_subdomain(
        request.topic,
        classification.profile,
    )
    try:
        corpus_records = await _maybe_await(
            provider_set.corpus.retrieve(
                request.topic,
                subdomain=corpus_subdomain,
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
            "corpus_subdomain": corpus_subdomain,
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

    markdown = "\n".join(lines)
    artifacts: list[ArtifactRef] = []
    if request.output_dir is not None:
        try:
            artifacts = _write_core_artifacts(
                request=request,
                profile=classification.profile,
                evidence=evidence,
                sections=sections,
                provenance=provenance,
                markdown=markdown,
            )
        except CasePrepError as exc:
            warnings.append(f"Artifact rendering: {exc}")
        except Exception as exc:
            warnings.append(f"Artifact rendering: {exc}")

    result = BuildCasePlanResult(
        topic=request.topic,
        markdown=markdown,
        output_dir=request.resolved_output_dir(),
        mode="core",
        artifacts=artifacts,
        evidence=evidence,
        provenance=provenance,
        structured=structured,
        warnings=warnings,
    )

    selected_store = store or resolve_caseprep_store(request)
    if selected_store is not None:
        try:
            persisted = await _maybe_await(
                selected_store.save_run(result, run_id=run_id)
            )
        except CasePrepError as exc:
            warnings.append(f"Persistence: {exc}")
        except Exception as exc:
            warnings.append(f"Persistence: {exc}")
        else:
            structured["persistence"] = persisted.to_dict()

    return result
