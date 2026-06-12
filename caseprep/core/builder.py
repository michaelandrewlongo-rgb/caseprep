"""Initial transport-agnostic CasePrep core builder.

This slice keeps the core path transport-agnostic while incrementally adding
classification, retrieval, synthesis, provenance validation, rendering, and
persistence seams.
"""

from __future__ import annotations

import inspect
import re
from dataclasses import dataclass, replace
from typing import Any, Protocol

from caseprep.confidence.calibration import log_calibration_point
from caseprep.case_parser import CaseField, parse_case_input, select_procedure_family
from caseprep.evidence_packs.thrombectomy import (
    EvidencePack,
    EvidencePackItem,
    get_thrombectomy_pack,
)
from caseprep.fact_validation import validate_rendered_fact_consistency
from caseprep.prognostic_signs import prognostic_signs_for_family
from caseprep.profile_classifier import classify_profile
from caseprep.persistence import CasePrepRunStore, resolve_caseprep_store
from caseprep.provenance import build_core_provenance, enforce_provenance
from caseprep.retrieval_planning import (
    build_case_queries,
    build_corpus_query,
    resolve_case_evidence_pack,
)
from caseprep.schema import AXIS_RELEVANCE, build_caseprep_schema, render_caseprep_files
from caseprep.scoring import (
    classify_clinical_applicability,
    grade_evidence,
    surgical_usefulness_score,
)
from caseprep.retrievers.corpus import CorpusRetriever
from caseprep.retrievers.corpus_semantic import SemanticCorpusRetriever
from caseprep.retrievers.pubmed import PubMedRetriever
from caseprep.retrievers.radiology import RadiologyRetriever
from caseprep.retrievers.board_cards import BoardCardRecord, BoardCardRetriever
from caseprep.retrievers import resolve_textbook_enabled
from caseprep.retrievers.textbook import TextbookRetriever
from caseprep.synthesis.section_synthesis import SectionDraft, synthesize_sections

from .contracts import (
    ArtifactRef,
    BuildCasePlanRequest,
    BuildCasePlanResult,
    EvidenceRecord,
    OutputIntentPlan,
    ProvenanceRecord,
)
from caseprep.audit.card_auditor import audit_manifest
from caseprep.compile.case_compiler import compile_board
from caseprep.compile.literature_review_compiler import compile_literature_review
from caseprep.enrichment.corpus_enricher import enrich_manifest
from caseprep.explorer.question_manifest import (
    build_question_manifest,
    inject_manifest_into_schema,
)

from .errors import CasePrepError, CasePrepValidationError


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
    corpus_semantic: CorpusRetrieverProtocol | None = None
    board_cards: BoardCardRetriever | None = None
    textbook: CorpusRetrieverProtocol | None = None


MAX_RETRIEVAL_CAP = 10
DEFAULT_SEMANTIC_TOP_N = 5


def _coerce_retrieval_cap(value: Any, *, field_name: str) -> int:
    """Validate a user-tunable retrieval count and apply the hard safety cap."""
    if not isinstance(value, int) or isinstance(value, bool):
        raise CasePrepValidationError(
            f"{field_name} must be an integer",
            details={"field": field_name},
        )
    if value < 1:
        raise CasePrepValidationError(
            f"{field_name} must be at least 1",
            details={"field": field_name},
        )
    return min(value, MAX_RETRIEVAL_CAP)


def _semantic_top_n(request: BuildCasePlanRequest, *, max_per: int) -> int:
    """Return the semantic corpus cap.

    PubMed stays bounded at the legacy per-axis default of 3 so the dossier
    does not become a literature dump. Semantic corpus gets a small rescue
    floor because it is the fallback when exact FTS5/raw PubMed queries miss.
    """
    requested = request.options.get("semantic_top_n")
    if requested is not None:
        return _coerce_retrieval_cap(requested, field_name="options.semantic_top_n")
    return min(max(max_per, DEFAULT_SEMANTIC_TOP_N), MAX_RETRIEVAL_CAP)


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
        corpus_semantic=SemanticCorpusRetriever(),
        board_cards=BoardCardRetriever(top_n=5),
        textbook=TextbookRetriever() if resolve_textbook_enabled() else None,
    )


async def _maybe_await(value):
    if inspect.isawaitable(value):
        return await value
    return value


def _tag_evidence(
    records: list[EvidenceRecord],
    *,
    axis: str,
    query: str,
    case_spec=None,
    family=None,
    procedure_family: str | None = None,
    broad_profile: str | None = None,
    sort_by_score: bool = False,
    retrieval_source: str | None = None,
) -> list[EvidenceRecord]:
    tagged: list[EvidenceRecord] = []
    for record in records:
        metadata = dict(record.metadata)
        metadata["axis"] = axis
        metadata["query"] = query
        if procedure_family is not None:
            metadata["procedure_family"] = procedure_family
        if broad_profile is not None:
            metadata["broad_profile"] = broad_profile
        if retrieval_source is not None:
            metadata.setdefault("retrieval_source", retrieval_source)
        provisional = replace(record, metadata=metadata)
        if case_spec is not None:
            include, applicability_reason = classify_clinical_applicability(
                provisional,
                case_spec,
                family,
            )
            metadata["clinical_include"] = include
            metadata["applicability_classification"] = applicability_reason
            if include:
                metadata.pop("quarantine_reason", None)
            else:
                metadata["quarantine_reason"] = applicability_reason
            provisional = replace(record, metadata=metadata)
            score, reasons = surgical_usefulness_score(
                provisional,
                case_spec,
                family,
                axis,
            )
            metadata["surgical_usefulness_score"] = score
            metadata["score_reasons"] = reasons
        tagged.append(replace(record, metadata=metadata))
    if sort_by_score:
        tagged.sort(
            key=lambda record: int(record.metadata.get("surgical_usefulness_score", 0)),
            reverse=True,
        )
    return tagged


def _source_counts(records: list[EvidenceRecord]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        counts[record.source] = counts.get(record.source, 0) + 1
    return counts


def _retrieval_source_counts(records: list[EvidenceRecord]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        tag = str(record.metadata.get("retrieval_source") or "unknown")
        counts[tag] = counts.get(tag, 0) + 1
        for extra in record.metadata.get("also_retrieved_by") or []:
            key = f"{extra}_also"
            counts[key] = counts.get(key, 0) + 1
    return counts


def _normalized_identifier(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "").strip().casefold())


def _normalized_title(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _evidence_identity_keys(record: EvidenceRecord) -> list[str]:
    metadata = record.metadata or {}
    keys: list[str] = []
    pmid = _normalized_identifier(metadata.get("pmid"))
    if not pmid:
        record_id = _normalized_identifier(record.id)
        if record_id.startswith("pmid-"):
            pmid = record_id.removeprefix("pmid-")
    if pmid:
        keys.append(f"pmid:{pmid}")
    doi = _normalized_identifier(metadata.get("doi"))
    if doi:
        keys.append(f"doi:{doi}")
    title = _normalized_title(record.title)
    if title:
        keys.append(f"title:{title}")
    return keys


def _prefer_record(new: EvidenceRecord, old: EvidenceRecord) -> bool:
    new_pack = bool(new.metadata.get("evidence_pack_id"))
    old_pack = bool(old.metadata.get("evidence_pack_id"))
    if new_pack != old_pack:
        return new_pack
    new_fts5 = new.metadata.get("retrieval_source") == "corpus_fts5"
    old_fts5 = old.metadata.get("retrieval_source") == "corpus_fts5"
    new_sem = new.metadata.get("retrieval_source") == "corpus_semantic"
    old_sem = old.metadata.get("retrieval_source") == "corpus_semantic"
    if new_fts5 and old_sem:
        return True
    if old_fts5 and new_sem:
        return False
    new_score = int(new.metadata.get("surgical_usefulness_score", 0) or 0)
    old_score = int(old.metadata.get("surgical_usefulness_score", 0) or 0)
    if new_score != old_score:
        return new_score > old_score
    new_has_text = bool(new.text.strip())
    old_has_text = bool(old.text.strip())
    if new_has_text != old_has_text:
        return new_has_text
    return False


def _merge_also_retrieved(kept: EvidenceRecord, dropped: EvidenceRecord) -> EvidenceRecord:
    kept_source = kept.metadata.get("retrieval_source")
    dropped_source = dropped.metadata.get("retrieval_source")
    if not dropped_source or dropped_source == kept_source:
        return kept
    metadata = dict(kept.metadata)
    also = list(metadata.get("also_retrieved_by") or [])
    if dropped_source not in also:
        also.append(dropped_source)
    metadata["also_retrieved_by"] = also
    # Surface the semantic confidence even when FTS5 wins the dedup, so the
    # clinician-facing audit trail can see the cross-retrieval signal.
    if dropped_source == "corpus_semantic":
        for key in ("semantic_cluster_cosine", "semantic_confidence", "semantic_cluster_name"):
            if key in dropped.metadata and key not in metadata:
                metadata[key] = dropped.metadata[key]
    return replace(kept, metadata=metadata)


def dedupe_evidence(records: list[EvidenceRecord]) -> list[EvidenceRecord]:
    """Deduplicate records by PMID, DOI, or normalized title, preferring pack hits."""
    deduped: list[EvidenceRecord] = []
    key_to_index: dict[str, int] = {}
    for record in records:
        keys = _evidence_identity_keys(record)
        existing_index = next((key_to_index[key] for key in keys if key in key_to_index), None)
        if existing_index is None:
            key_to_index.update({key: len(deduped) for key in keys})
            deduped.append(record)
            continue
        existing = deduped[existing_index]
        if _prefer_record(record, existing):
            deduped[existing_index] = _merge_also_retrieved(record, existing)
        else:
            deduped[existing_index] = _merge_also_retrieved(existing, record)
        for key in keys:
            key_to_index[key] = existing_index
    return deduped


def _pack_item_queries(item: EvidencePackItem) -> list[str]:
    queries: list[str] = []
    if item.pmid:
        queries.append(f"{item.pmid}[PMID]")
    if item.doi:
        queries.append(f"{item.doi}[doi]")
    if item.query_fallback:
        queries.append(item.query_fallback)
    unique: list[str] = []
    seen: set[str] = set()
    for query in queries:
        key = query.casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(query)
    return unique


def _pack_item_match_verification(record: EvidenceRecord, item: EvidencePackItem) -> str | None:
    metadata = record.metadata or {}
    record_id = _normalized_identifier(record.id)
    if item.pmid and (
        _normalized_identifier(metadata.get("pmid")) == item.pmid.casefold()
        or record_id == f"pmid-{item.pmid.casefold()}"
    ):
        return "retrieved"
    if item.doi and _normalized_identifier(metadata.get("doi")) == _normalized_identifier(item.doi):
        return "retrieved"
    title = _normalized_title(record.title)
    hint = _normalized_title(item.title_hint)
    if not title or not hint:
        return None
    if hint in title or title in hint:
        return "partial"
    hint_tokens = {token for token in hint.split() if len(token) >= 4}
    title_tokens = {token for token in title.split() if len(token) >= 4}
    if not hint_tokens:
        return None
    overlap = hint_tokens & title_tokens
    if len(overlap) >= max(3, int(len(hint_tokens) * 0.6)):
        return "partial"
    return None


def _record_matches_pack_item(record: EvidenceRecord, item: EvidencePackItem) -> bool:
    return _pack_item_match_verification(record, item) is not None


def _pack_item_payload(
    item: EvidencePackItem,
    *,
    record: EvidenceRecord | None = None,
    verification: str,
    attempted_queries: list[str] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "pack_item_id": item.id,
        "title": record.title if record is not None and record.title else item.title_hint,
        "pmid": (record.metadata.get("pmid") if record is not None else None) or item.pmid,
        "doi": (record.metadata.get("doi") if record is not None else None) or item.doi,
        "tier": item.tier,
        "source_tier": item.tier,
        "applicability": item.applicability_summary,
        "required_for": list(item.required_for),
        "conditional": item.conditional,
        "verification": verification,
    }
    if record is not None:
        payload["id"] = record.id
    if attempted_queries:
        payload["attempted_queries"] = attempted_queries
    return payload


async def _retrieve_evidence_pack(
    *,
    pack: EvidencePack,
    provider_set: CoreRetrieverSet,
    case_spec,
    family,
    procedure_family: str | None,
    broad_profile: str | None,
    warnings: list[str],
) -> tuple[list[EvidenceRecord], dict[str, Any]]:
    """Force retrieval attempts for an evidence pack without fabricating records."""
    evidence: list[EvidenceRecord] = []
    coverage: dict[str, Any] = {
        "id": pack.id,
        "display_name": pack.display_name,
        "applicability_summary": pack.applicability_summary,
        "retrieved": [],
        "missing": [],
        "partial": [],
    }
    for item in pack.items:
        attempted_queries = _pack_item_queries(item)
        matched_record: EvidenceRecord | None = None
        matched_verification: str | None = None
        for query in attempted_queries:
            try:
                records = await provider_set.pubmed.retrieve(
                    query,
                    max_results=1,
                    filter_type=None,
                    include_abstracts=True,
                )
            except CasePrepError as exc:
                warnings.append(f"Evidence pack {pack.id}/{item.id}: {exc}")
                continue
            for candidate in records:
                match_verification = _pack_item_match_verification(candidate, item)
                if match_verification is not None:
                    matched_record = candidate
                    matched_verification = match_verification
                    break
            if matched_record is not None:
                break
        if matched_record is None:
            coverage["missing"].append(
                _pack_item_payload(
                    item,
                    verification="missing",
                    attempted_queries=attempted_queries,
                )
            )
            continue
        verification = matched_verification or "partial"
        metadata = dict(matched_record.metadata)
        if verification == "retrieved":
            if item.pmid:
                metadata.setdefault("pmid", item.pmid)
            if item.doi:
                metadata.setdefault("doi", item.doi)
        else:
            if item.pmid:
                metadata.setdefault("target_pmid", item.pmid)
            if item.doi:
                metadata.setdefault("target_doi", item.doi)
        metadata.update({
            "evidence_pack_id": pack.id,
            "pack_item_id": item.id,
            "source_tier": item.tier,
            "tier": item.tier,
            "evidence_role": ", ".join(item.required_for),
            "applicability": item.applicability_summary,
            "required_for": list(item.required_for),
            "conditional": item.conditional,
            "verification": verification,
        })
        tagged = _tag_evidence(
            [replace(matched_record, metadata=metadata)],
            axis="Evidence Pack",
            query="; ".join(attempted_queries),
            case_spec=case_spec,
            family=family,
            procedure_family=procedure_family,
            broad_profile=broad_profile,
            sort_by_score=False,
        )[0]
        evidence.append(tagged)
        coverage_bucket = "retrieved" if verification == "retrieved" else "partial"
        coverage[coverage_bucket].append(
            _pack_item_payload(
                item,
                record=tagged,
                verification=verification,
                attempted_queries=attempted_queries,
            )
        )
    return evidence, coverage


def _quarantined_sources(records: list[EvidenceRecord]) -> list[dict[str, Any]]:
    return [
        _key_source(record)
        for record in records
        if record.metadata.get("clinical_include") is False
    ]


def _procedure_family_dict(case_spec) -> dict[str, Any] | None:
    family = select_procedure_family(case_spec)
    if family is None:
        return None
    return {
        "id": family.id,
        "display_name": family.display_name,
        "broad_profile": family.broad_profile,
        "required_fields": list(family.required_fields),
        "missing_fact_prompts": list(family.missing_fact_prompts),
    }


def _should_apply_parser_profile(case_spec, classification) -> bool:
    """Return whether parser-derived family/profile should drive classification.

    Parser profiles are trusted for high-confidence procedure/approach-derived
    families, or complete canonical cases. Degraded topic/pathology-only matches
    (for example bare "Chiari" or "cervical radiculopathy") stay with the older
    topic classifier. An explicit user profile_hint is represented by the
    classifier as source="hint" and is never overridden here.
    """
    if classification.source == "hint":
        return False
    if not (case_spec.procedure_family.value and case_spec.broad_profile.value):
        return False
    return case_spec.procedure_family.confidence >= 0.8 or not case_spec.degraded


def _should_apply_procedure_family_retrieval(case_spec, classification) -> bool:
    """Return whether procedure-family retrieval templates are safe to use.

    Retrieval trust is independent of profile classification ownership: an
    explicit profile_hint should control structured["profile"], but it should
    not suppress high-confidence/non-degraded procedure-family query templates.
    Degraded topic/pathology-only matches still fall back to generic queries.
    """
    if not case_spec.procedure_family.value:
        return False
    if case_spec.procedure_family.confidence >= 0.8:
        return True
    return not case_spec.degraded


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


def _key_source(record: EvidenceRecord) -> dict[str, Any]:
    axis = str(record.metadata.get("axis") or "").strip()
    metadata = record.metadata or {}
    evidence_level = _evidence_level(record)
    source_tier = str(metadata.get("source_tier") or metadata.get("tier") or evidence_level)
    source = {
        "id": record.id,
        "title": record.title,
        "year": _evidence_year(record),
        "evidence_level": evidence_level,
        "tier": source_tier,
        "source_tier": source_tier,
        "relevance": AXIS_RELEVANCE.get(axis, axis.lower() or record.source),
        "verification": str(metadata.get("verification") or "cited"),
    }
    for key in (
        "pmid",
        "doi",
        "evidence_pack_id",
        "pack_item_id",
        "evidence_role",
        "applicability",
        "clinical_include",
        "quarantine_reason",
        "applicability_classification",
        "retrieval_source",
        "also_retrieved_by",
        "semantic_cluster_cosine",
        "semantic_confidence",
        "semantic_cluster_name",
    ):
        if key in metadata:
            source[key] = metadata[key]
    if "score_reasons" in metadata:
        source["score_reasons"] = metadata["score_reasons"]
    return source


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


def _bind_prognostic_signs(schema: dict[str, Any], provenance: list[ProvenanceRecord]) -> None:
    """Attach the authored prognostic-signs block + provenance for supported families."""
    family_id = ""
    fam = schema.get("procedure_family")
    if isinstance(fam, dict):
        family_id = str(fam.get("id") or "")
    block = prognostic_signs_for_family(family_id)
    if not block:
        return
    schema.setdefault("case", {})["prognostic_signs"] = block
    source_ids: list[str] = []
    for group in ("favorable", "unfavorable"):
        for entry in block.get(group, []):
            for sid in entry.get("source_ids", []):
                if sid not in source_ids:
                    source_ids.append(sid)
    provenance.append(ProvenanceRecord(
        field_path="case.prognostic_signs",
        source_ids=source_ids,
        value_status="generated",
        generated_by="caseprep.prognostic_signs",
        notes="Authored favorable/unfavorable outcome indicators cited to thrombectomy evidence-pack items.",
    ))


def _write_core_artifacts(
    *,
    request: BuildCasePlanRequest,
    topic: str,
    profile: str,
    evidence: list[EvidenceRecord],
    sections: list[SectionDraft],
    provenance: list[Any],
    markdown: str,
    structured_case: dict[str, Any] | None = None,
    procedure_family: dict[str, Any] | None = None,
    evidence_pack: dict[str, Any] | None = None,
    quarantined_sources: list[dict[str, Any]] | None = None,
    warnings: list[str] | None = None,
    provider_set: CoreRetrieverSet | None = None,
    intent_plan: OutputIntentPlan | None = None,
) -> list[ArtifactRef]:
    schema = build_caseprep_schema(
        topic,
        profile=profile,
        structured_case=structured_case,
        procedure_family=procedure_family,
    )

    # ── Explorer question-manifest injection ────────────────────────────
    family_id = (
        procedure_family.get("id", "")
        if isinstance(procedure_family, dict)
        else ""
    )
    manifest = build_question_manifest(
        family_id,
        topic,
        profile=profile,
    )
    manifest_json: str | None = None
    enriched_json: str | None = None
    if manifest is not None:
        # Only inject Explorer cards into schema sections that do NOT
        # already have family-default content.  Families like thrombectomy
        # and ACDF have comprehensive context-aware defaults that should
        # not be replaced.
        family_has_defaults = family_id in (
            "endovascular_thrombectomy",
            "spine_acdf",
        )
        if not family_has_defaults:
            inject_manifest_into_schema(schema, manifest)
        import json
        manifest_json = json.dumps(manifest.to_dict(), indent=2) + "\n"

        # ── Enrichment: attach corpus evidence to each question card ───
        if provider_set is not None and not family_has_defaults:
            # Answer each high-yield card from every available grounded lane:
            # the semantic corpus AND the user's textbook library. The textbook
            # lane carries page-grounded passages and figure paths, so a card
            # gets answered (and illustrated) even when the corpus backend is
            # offline.
            from caseprep.retrievers.composite import CompositeRetriever

            card_retriever = CompositeRetriever(
                [provider_set.corpus_semantic, provider_set.textbook]
            )
            if card_retriever.any_lanes():
                try:
                    enriched = enrich_manifest(
                        manifest,
                        topic=topic,
                        retriever=card_retriever,
                        top_n=3,
                    )
                    enriched_json = json.dumps(enriched.to_dict(), indent=2) + "\n"
                    # ── Confidence: attach confidence scores to each slot ─────
                    from caseprep.core.contracts import SlotConfidence
                    if enriched is not None:
                        for card in enriched.cards:
                            if card.papers:
                                num_papers = len(card.papers)
                                confidence = SlotConfidence(
                                    logprob=-0.5 * num_papers,
                                    entropy=1.0 / max(num_papers, 1),
                                )
                                card.confidence = confidence
                except Exception as exc:
                    if warnings is not None:
                        warnings.append(f"Enrichment: {exc}")
                    enriched = None
            else:
                enriched = None
        else:
            enriched = None

        # ── Auditor: validate enriched claims against evidence ───────
        audited = None
        if enriched is not None:
            try:
                audited = audit_manifest(enriched, topic=topic)
                import json as _json2
                _json2  # already imported above
            except Exception as exc:
                if warnings is not None:
                    warnings.append(f"Auditor: {exc}")

        # ── Compiler: assemble audited claims into case board ────────
        board_pearls = None
        if audited is not None and provider_set is not None and provider_set.board_cards is not None:
            try:
                board_pearls = provider_set.board_cards.retrieve(topic)
            except Exception as exc:
                if warnings is not None:
                    warnings.append(f"Board pearls: {exc}")

        if audited is not None:
            try:
                board = compile_board(audited, topic=topic, board_pearls=board_pearls)
                board_json = json.dumps(board.to_dict(), indent=2) + "\n"
            except Exception as exc:
                if warnings is not None:
                    warnings.append(f"Compiler: {exc}")
                board = None
        else:
            board = None
        # ───────────────────────────────────────────────────────────────

    schema["case"]["evidence"]["key_sources"] = [
        _key_source(record) for record in evidence if record.id
    ]
    if evidence_pack is not None:
        schema["case"]["evidence"]["evidence_pack"] = evidence_pack
    if quarantined_sources is not None:
        schema["case"]["evidence"]["quarantined_sources"] = quarantined_sources
    schema["case"]["evidence"]["clinical_questions"] = [
        f"What operative approach and setup best fit {topic}?",
        f"What anatomy and imaging findings should change the plan for {topic}?",
        f"What complications and rescue plans are most important for {topic}?",
    ]
    try:
        _bind_prognostic_signs(schema, provenance)
    except Exception as exc:  # never block the briefing on prognostic binding
        if warnings is not None:
            warnings.append(f"Prognostic signs: {exc}")

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
    if warnings is not None:
        rendered_markdown = "\n".join(
            content for filename, content in rendered_files.items() if filename.endswith(".md")
        )
        warnings.extend(validate_rendered_fact_consistency(schema, rendered_markdown))

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

    if intent_plan is not None and intent_plan.intent_type == "literature_review":
        literature_markdown = compile_literature_review(
            topic=topic,
            intent_plan=intent_plan,
            evidence=evidence,
            sections=sections,
        )
        literature_path = output_dir / "literature_review.md"
        literature_path.write_text(literature_markdown, encoding="utf-8")
        artifacts.append(
            ArtifactRef(
                path=literature_path,
                kind="markdown",
                media_type="text/markdown",
                label="literature_review.md",
                metadata={"primary": True, "intent_type": "literature_review"},
            )
        )

    if manifest_json is not None:
        manifest_path = output_dir / "case_question_manifest.json"
        manifest_path.write_text(manifest_json, encoding="utf-8")
        artifacts.append(
            ArtifactRef(
                path=manifest_path,
                kind="data",
                media_type="application/json",
                label="case_question_manifest.json",
            )
        )

    if enriched_json is not None:
        enriched_path = output_dir / "case_enriched_manifest.json"
        enriched_path.write_text(enriched_json, encoding="utf-8")
        artifacts.append(
            ArtifactRef(
                path=enriched_path,
                kind="data",
                media_type="application/json",
                label="case_enriched_manifest.json",
            )
        )

    if board is not None and board_json is not None:
        board_md_path = output_dir / "case_board.md"
        board_md_path.write_text(board.render(), encoding="utf-8")
        artifacts.append(
            ArtifactRef(
                path=board_md_path,
                kind="markdown",
                media_type="text/markdown",
                label="case_board.md",
                metadata={"primary": True, "intent_type": "operative_briefing"},
            )
        )
        board_json_path = output_dir / "case_board.json"
        board_json_path.write_text(board_json, encoding="utf-8")
        artifacts.append(
            ArtifactRef(
                path=board_json_path,
                kind="data",
                media_type="application/json",
                label="case_board.json",
            )
        )
        if request.options.get("pdf"):
            try:
                from caseprep.export.pdf import export_board_pdf

                artifacts.append(export_board_pdf(board, evidence, output_dir))
            except Exception as exc:
                if warnings is not None:
                    warnings.append(f"PDF export: {exc}")

    return artifacts


async def build_core_case_plan(
    request: BuildCasePlanRequest,
    *,
    retrievers: CoreRetrieverSet | None = None,
    store: CasePrepRunStore | None = None,
    run_id: str | None = None,
) -> BuildCasePlanResult:
    """Build a procedure-first core CasePrep dossier."""
    topic = request.resolved_case_input()
    case_spec = parse_case_input(topic)
    procedure_family = select_procedure_family(case_spec)
    provider_set = retrievers or default_core_retrievers()
    classification = classify_profile(
        topic,
        profile_hint=request.profile_hint,
    )
    if _should_apply_parser_profile(case_spec, classification):
        classification = replace(
            classification,
            profile=case_spec.broad_profile.value,
            confidence=case_spec.broad_profile.confidence,
            matched_term=case_spec.procedure_family.value,
            source="case_parser",
        )
    max_per = min(request.max_per_category, MAX_RETRIEVAL_CAP)
    semantic_top_n = _semantic_top_n(request, max_per=max_per)
    radiology_max_results = min(max_per, 5)
    corpus_top_n = max_per

    query_case_spec = case_spec
    if procedure_family is None and not case_spec.broad_profile.value:
        query_case_spec = replace(
            case_spec,
            broad_profile=CaseField(
                classification.profile,
                classification.confidence,
                classification.source,
                span=classification.matched_term,
            ),
        )
    retrieval_family = (
        procedure_family
        if _should_apply_procedure_family_retrieval(case_spec, classification)
        else None
    )
    pubmed_axes = build_case_queries(
        query_case_spec,
        retrieval_family,
        intent_plan=request.intent_plan,
    )

    evidence: list[EvidenceRecord] = []
    warnings: list[str] = list(request.intent_plan.warnings if request.intent_plan else [])
    evidence_pack_coverage: dict[str, Any] | None = None
    evidence_pack_id = resolve_case_evidence_pack(query_case_spec, retrieval_family)
    if evidence_pack_id:
        evidence_pack = get_thrombectomy_pack(evidence_pack_id)
        if evidence_pack is not None:
            pack_records, evidence_pack_coverage = await _retrieve_evidence_pack(
                pack=evidence_pack,
                provider_set=provider_set,
                case_spec=query_case_spec,
                family=retrieval_family,
                procedure_family=retrieval_family.id if retrieval_family else None,
                broad_profile=(
                    retrieval_family.broad_profile
                    if retrieval_family
                    else query_case_spec.broad_profile.value
                ),
                warnings=warnings,
            )
            evidence.extend(pack_records)

    for axis in pubmed_axes:
        try:
            records = await provider_set.pubmed.retrieve(
                axis.query,
                max_results=max_per,
                filter_type=axis.filter_type,
                include_abstracts=True,
            )
        except CasePrepError as exc:
            warnings.append(f"{axis.label}: {exc}")
            continue
        records = list(records)[:max_per]
        evidence.extend(
            _tag_evidence(
                records,
                axis=axis.label,
                query=axis.query,
                case_spec=query_case_spec,
                family=retrieval_family,
                procedure_family=retrieval_family.id if retrieval_family else None,
                broad_profile=(
                    retrieval_family.broad_profile
                    if retrieval_family
                    else query_case_spec.broad_profile.value
                ),
                sort_by_score=True,
                retrieval_source="pubmed",
            )
        )

    radiology_query = f"{topic} radiology imaging"
    try:
        radiology_records = await provider_set.radiology.retrieve(
            radiology_query,
            max_results=radiology_max_results,
            modality=None,
        )
    except CasePrepError as exc:
        warnings.append(f"Radiology: {exc}")
    else:
        radiology_records = list(radiology_records)[:radiology_max_results]
        evidence.extend(
            _tag_evidence(
                radiology_records,
                axis="Radiology",
                query=radiology_query,
                case_spec=query_case_spec,
                family=retrieval_family,
                procedure_family=retrieval_family.id if retrieval_family else None,
                broad_profile=(
                    retrieval_family.broad_profile
                    if retrieval_family
                    else query_case_spec.broad_profile.value
                ),
                retrieval_source="radiology",
            )
        )

    corpus_subdomain = resolve_corpus_subdomain(
        topic,
        classification.profile,
    )
    corpus_query = build_corpus_query(query_case_spec, retrieval_family)
    try:
        corpus_records = await _maybe_await(
            provider_set.corpus.retrieve(
                corpus_query,
                subdomain=corpus_subdomain,
                top_n=corpus_top_n,
            )
        )
    except CasePrepError as exc:
        warnings.append(f"Corpus: {exc}")
    else:
        corpus_records = list(corpus_records)[:corpus_top_n]
        evidence.extend(
            _tag_evidence(
                corpus_records,
                axis="Corpus",
                query=corpus_query,
                case_spec=query_case_spec,
                family=retrieval_family,
                procedure_family=retrieval_family.id if retrieval_family else None,
                broad_profile=(
                    retrieval_family.broad_profile
                    if retrieval_family
                    else query_case_spec.broad_profile.value
                ),
                retrieval_source="corpus_fts5",
            )
        )

    if provider_set.textbook is not None:
        try:
            textbook_records = await _maybe_await(
                provider_set.textbook.retrieve(
                    corpus_query,
                    subdomain=corpus_subdomain,
                    top_n=corpus_top_n,
                )
            )
        except CasePrepError as exc:
            warnings.append(f"Textbook: {exc}")
        else:
            textbook_records = list(textbook_records)[:corpus_top_n]
            evidence.extend(
                _tag_evidence(
                    textbook_records,
                    axis="Textbook",
                    query=corpus_query,
                    case_spec=query_case_spec,
                    family=retrieval_family,
                    procedure_family=retrieval_family.id if retrieval_family else None,
                    broad_profile=(
                        retrieval_family.broad_profile
                        if retrieval_family
                        else query_case_spec.broad_profile.value
                    ),
                    retrieval_source="textbook_rag",
                )
            )

    semantic_query = topic
    semantic_used = False
    if provider_set.corpus_semantic is not None:
        semantic_used = True
        try:
            semantic_records = await _maybe_await(
                provider_set.corpus_semantic.retrieve(
                    semantic_query,
                    subdomain=corpus_subdomain,
                    top_n=semantic_top_n,
                )
            )
        except CasePrepError as exc:
            warnings.append(f"Corpus (semantic): {exc}")
        else:
            semantic_records = list(semantic_records)[:semantic_top_n]
            evidence.extend(
                _tag_evidence(
                    semantic_records,
                    axis="Corpus (semantic)",
                    query=semantic_query,
                    case_spec=query_case_spec,
                    family=retrieval_family,
                    procedure_family=retrieval_family.id if retrieval_family else None,
                    broad_profile=(
                        retrieval_family.broad_profile
                        if retrieval_family
                        else query_case_spec.broad_profile.value
                    ),
                    retrieval_source="corpus_semantic",
                )
            )

    evidence = dedupe_evidence(evidence)
    quarantined_sources = _quarantined_sources(evidence)

    structured: dict[str, Any] = {
        "case": case_spec.to_dict(),
        "intent_plan": request.intent_plan.to_dict() if request.intent_plan else None,
        "procedure_family": _procedure_family_dict(case_spec),
        "profile": {
            "name": classification.profile,
            "confidence": classification.confidence,
            "matched_term": classification.matched_term,
            "source": classification.source,
        },
        "retrieval": {
            "pubmed_axes": [axis.label for axis in pubmed_axes],
            "pubmed_queries": [
                {
                    "id": axis.id,
                    "label": axis.label,
                    "query": axis.query,
                    "filter_type": axis.filter_type,
                }
                for axis in pubmed_axes
            ],
            "corpus_subdomain": corpus_subdomain,
            "corpus_query": corpus_query,
            "semantic_query": semantic_query if semantic_used else None,
            "semantic_enabled": semantic_used,
            "caps": {
                "pubmed_per_axis": max_per,
                "radiology": radiology_max_results,
                "corpus_fts5": corpus_top_n,
                "corpus_semantic": semantic_top_n if semantic_used else None,
            },
            "evidence_count": len(evidence),
            "sources": _source_counts(evidence),
            "retrieval_sources": _retrieval_source_counts(evidence),
            "evidence_pack": evidence_pack_coverage,
            "quarantined_sources": quarantined_sources,
        },
    }
    sections = synthesize_sections(topic, evidence)
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
        f"# Core Case Plan - {topic}",
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
    retrieval_sources = structured["retrieval"].get("retrieval_sources") or {}
    if retrieval_sources:
        lines.extend(["", "## Retrieval Path"])
        for tag, count in sorted(retrieval_sources.items()):
            lines.append(f"- {tag}: {count}")
    caps = structured["retrieval"].get("caps") or {}
    if caps:
        lines.extend(["", "## Retrieval Caps"])
        for tag, count in sorted(caps.items()):
            if count is not None:
                lines.append(f"- {tag}: {count}")
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
                topic=topic,
                profile=classification.profile,
                evidence=evidence,
                sections=sections,
                provenance=provenance,
                markdown=markdown,
                structured_case=structured["case"],
                procedure_family=structured["procedure_family"],
                evidence_pack=evidence_pack_coverage,
                quarantined_sources=quarantined_sources,
                warnings=warnings,
                provider_set=provider_set,
                intent_plan=request.intent_plan,
            )
        except CasePrepError as exc:
            warnings.append(f"Artifact rendering: {exc}")
        except Exception as exc:
            warnings.append(f"Artifact rendering: {exc}")

    result = BuildCasePlanResult(
        topic=topic,
        markdown=markdown,
        output_dir=request.resolved_output_dir(),
        mode="core",
        artifacts=artifacts,
        evidence=evidence,
        provenance=provenance,
        structured=structured,
        warnings=warnings,
        intent_plan=request.intent_plan,
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
