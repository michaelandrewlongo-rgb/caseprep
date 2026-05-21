"""Evidence grading and neurosurgical relevance scoring helpers."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from caseprep.case_parser import CaseSpec
    from caseprep.core.contracts import EvidenceRecord
    from caseprep.procedure_taxonomy import ProcedureFamily


@dataclass(frozen=True)
class EvidenceGrade:
    level: int
    label: str
    quality_label: str


EVIDENCE_RULES: tuple[tuple[tuple[str, ...], EvidenceGrade, str], ...] = (
    (
        ("randomized controlled trial",),
        EvidenceGrade(1, "Level 1 — RCT", "High"),
        "RCT",
    ),
    (
        ("meta-analysis", "meta analysis"),
        EvidenceGrade(1, "Level 1 — Meta-analysis", "High"),
        "Meta-analysis",
    ),
    (
        ("systematic review",),
        EvidenceGrade(1, "Level 1 — Systematic review", "High"),
        "Systematic review",
    ),
    (
        ("practice guideline", "guideline"),
        EvidenceGrade(1, "Level 1 — Guideline", "High"),
        "Guideline",
    ),
    (
        ("clinical trial",),
        EvidenceGrade(2, "Level 2 — Clinical trial", "Moderate"),
        "Clinical trial",
    ),
    (
        ("multicenter study", "multi-center study"),
        EvidenceGrade(2, "Level 2 — Multicenter study", "Moderate"),
        "Multicenter study",
    ),
    (
        ("comparative study",),
        EvidenceGrade(3, "Level 3 — Comparative study", "Low"),
        "Comparative study",
    ),
    (
        ("observational study",),
        EvidenceGrade(3, "Level 3 — Observational study", "Low"),
        "Observational study",
    ),
    (
        ("case reports", "case report"),
        EvidenceGrade(4, "Level 4 — Case report", "Low"),
        "Case report",
    ),
    (
        ("review",),
        EvidenceGrade(5, "Level 5 — Narrative review", "Low"),
        "Narrative review",
    ),
)

DEFAULT_EVIDENCE_GRADE = EvidenceGrade(
    5,
    "Level 5 — Unclassified study design",
    "Low",
)
DEFAULT_STUDY_TYPE = "Unclassified study design"

PROCEDURE_TERMS: tuple[str, ...] = (
    # Vascular / Endovascular
    "clipping",
    "coiling",
    "thrombectomy",
    "bypass",
    "flow diversion",
    "stent-assisted",
    "embolization",
    "endovascular",
    "stent retriever",
    "coil",
    "pipeline",
    "aneurysmectomy",
    # Open cranial / Skull base
    "craniotomy",
    "microsurgical",
    "microsurgery",
    "retrosigmoid",
    "translabyrinthine",
    "transsphenoidal",
    "endonasal",
    "pterional",
    "orbitozygomatic",
    "awake craniotomy",
    "decompression",
    "resection",
    "tumor resection",
    # Spine
    "laminectomy",
    "discectomy",
    "fusion",
    "corpectomy",
    "foraminotomy",
    "laminoplasty",
    "tlif",
    "plif",
    "alif",
    "microdiscectomy",
    # Functional / Radiosurgery
    "stereotactic",
    "deep brain stimulation",
    "radiosurgery",
    "gamma knife",
    "srs",
    "dbs",
    "lhbo",
)

OUTCOME_TERMS: tuple[str, ...] = (
    "outcome",
    "efficacy",
    "safety",
    "complication",
    "survival",
    "recurrence",
    "comparison",
    "versus",
    "randomized",
    "prospective",
    "retrospective",
    "cohort",
    "follow-up",
    "morbidity",
    "mortality",
)

NEUROANATOMY_TERMS: tuple[str, ...] = (
    # Vascular / endovascular
    "cerebral",
    "intracranial",
    "aneurysm",
    "stenosis",
    "cavernous",
    # General cranial
    "brain",
    "cranial",
    "skull base",
    "nerve",
    "cortex",
    "cerebellar",
    "brainstem",
    "ventricle",
    "foramen",
    "dural",
    "sella",
    "cerebellopontine",
    # Tumor / pathology
    "tumor",
    "tumour",
    "schwannoma",
    "meningioma",
    "glioma",
    "pituitary",
    "metastasis",
    "lesion",
    "mass",
    "malignancy",
    "neoplasm",
    # Spine
    "spine",
    "spinal",
    "pedicle",
    "cord",
    "disc",
    "disk",
    "vertebral",
    "foraminal",
    "myelopathy",
    # Functional
    "thalamus",
    "thalamic",
    "basal ganglia",
    "subthalamic",
)

# Terms that are useful when paired with true neurosurgical context, but are too
# generic to prove that an otherwise non-neurosurgical paper is on-domain.
GENERIC_CONTEXT_TERMS: tuple[str, ...] = (
    "tumor",
    "tumour",
    "lesion",
    "mass",
    "malignancy",
    "neoplasm",
    "resection",
    "tumor resection",
    "embolization",
    "endovascular",
    "fusion",
    "decompression",
)

STRICT_NEURO_CONTEXT_TERMS: tuple[str, ...] = tuple(
    term for term in NEUROANATOMY_TERMS if term not in GENERIC_CONTEXT_TERMS
)

NON_NEURO_TERMS: tuple[str, ...] = (
    "abdominal aortic",
    "uterine",
    "fibroid",
    "gynecologic",
    "gastric",
    "colon",
    "breast",
    "prostate",
    "bariatric",
    "hepatocellular",
    "microbiome",
    "pregnancy",
    "retinal",
    "orthopedic",
)

DRUG_TERMS: tuple[str, ...] = (
    "drug",
    "medication",
    "pharmaceutical",
    "pharmacokinetic",
    "placebo",
)

BASIC_SCIENCE_TERMS: tuple[str, ...] = (
    "cell culture",
    "in vitro",
    "murine",
    "mouse model",
    "rat model",
    "protein expression",
    "molecular pathway",
)

TECHNIQUE_TERMS: tuple[str, ...] = PROCEDURE_TERMS + (
    "approach",
    "technical",
    "technique",
    "operative",
    "operation",
    "positioning",
    "setup",
    "exposure",
    "localization",
    "devascularization",
    "debulking",
    "closure",
    "reconstruction",
    "rescue",
)

COMPLICATION_TERMS: tuple[str, ...] = OUTCOME_TERMS + (
    "adverse",
    "injury",
    "dysphagia",
    "recurrent laryngeal nerve",
    "csf leak",
    "pseudomeningocele",
    "infection",
    "hematoma",
    "hemorrhage",
    "infarct",
    "seizure",
    "pseudarthrosis",
    "perforation",
    "vasospasm",
)

ANATOMY_AXIS_TERMS: tuple[str, ...] = NEUROANATOMY_TERMS + (
    "anatomy",
    "anatomic",
    "landmark",
    "landmarks",
    "exposure corridor",
    "trajectory",
    "foramen magnum",
    "vertebral artery",
    "esophagus",
    "uncinate",
    "bridging vein",
    "sinus",
)

TECHNICAL_PUBLICATION_TERMS: tuple[str, ...] = (
    "technical note",
    "operative technique",
    "surgical technique",
    "operative series",
    "case series",
    "surgical anatomy",
)

REVIEW_PUBLICATION_TERMS: tuple[str, ...] = (
    "systematic review",
    "meta-analysis",
    "meta analysis",
    "review",
    "guideline",
    "landmark",
)


def grade_evidence(pub_types: list[str]) -> EvidenceGrade:
    """Return a CEBM-style evidence grade from PubMed publication types."""
    normalized = _normalize_pub_types(pub_types)
    for terms, grade, _study_type in EVIDENCE_RULES:
        if any(term in normalized for term in terms):
            return grade
    return DEFAULT_EVIDENCE_GRADE


def classify_study_type(pub_types: list[str]) -> str:
    """Return a human-readable study type label from PubMed publication types."""
    normalized = _normalize_pub_types(pub_types)
    for terms, _grade, study_type in EVIDENCE_RULES:
        if any(term in normalized for term in terms):
            return study_type
    return DEFAULT_STUDY_TYPE


def extract_n_value(abstract: str | None) -> str:
    """Extract a reported cohort size from common abstract phrasings."""
    if not abstract:
        return "NR"
    patterns = (
        r"\bn\s*=\s*([0-9][0-9,]*)\b",
        r"\bincluded\s+([0-9][0-9,]*)\s+(?:patients|subjects)\b",
        r"\benrolled\s+([0-9][0-9,]*)\s+(?:patients|subjects)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, abstract, flags=re.IGNORECASE)
        if match:
            return match.group(1).replace(",", "")
    return "NR"


def neurosurg_relevance_score(title: str, abstract: str | None) -> float:
    """Score neurosurgical relevance from title and abstract term matches."""
    text = f"{title or ''} {abstract or ''}"
    true_neuro_matches = _count_matches(text, STRICT_NEURO_CONTEXT_TERMS)
    non_neuro_matches = _count_matches(text, NON_NEURO_TERMS)
    has_true_neuro_context = true_neuro_matches > 0

    # Some terms are useful neurosurgical signals only when paired with true
    # neuroanatomic/procedure context.  Do not let generic procedural oncology
    # or endovascular language (e.g. breast tumor resection, uterine fibroid
    # embolization) suppress the non-neuro penalty or inflate legacy ranking.
    procedure_terms = PROCEDURE_TERMS
    neuroanatomy_terms = NEUROANATOMY_TERMS
    if non_neuro_matches and not has_true_neuro_context:
        procedure_terms = _strict_context_terms(PROCEDURE_TERMS)
        neuroanatomy_terms = STRICT_NEURO_CONTEXT_TERMS

    score = 0.0
    score += 20.0 * _count_matches(text, procedure_terms)
    score += 10.0 * _count_matches(text, OUTCOME_TERMS)

    neuroanatomy_matches = _count_matches(text, neuroanatomy_terms)
    score += 10.0 * neuroanatomy_matches

    if not has_true_neuro_context:
        score -= 30.0 * non_neuro_matches
        if non_neuro_matches:
            score -= 20.0

    if score == 0:
        score -= 20.0 * _count_matches(text, DRUG_TERMS)

    return score


def surgical_usefulness_score(
    record: "EvidenceRecord",
    case: "CaseSpec",
    family: "ProcedureFamily | None",
    axis: str,
) -> tuple[int, list[str]]:
    """Return transparent source-usefulness score and reasons."""
    title = getattr(record, "title", "") or ""
    abstract = getattr(record, "text", "") or ""
    metadata = getattr(record, "metadata", {}) or {}
    pub_types = " ".join(str(value) for value in metadata.get("pub_types", []) or [])
    title_text = title
    full_text = f"{title} {abstract} {pub_types}"
    axis_text = (axis or "").casefold()
    score = 0
    reasons: list[str] = []

    procedure_terms = _case_terms(case, "procedure", "approach")
    pathology_terms = _case_terms(case, "pathology")
    location_terms = _case_terms(case, "anatomic_location", "level_or_segment")
    if family is not None:
        procedure_terms.extend(getattr(family, "procedure_aliases", ()) or ())
        procedure_terms.extend(getattr(family, "approach_aliases", ()) or ())
        pathology_terms.extend(getattr(family, "pathology_aliases", ()) or ())
        location_terms.extend(getattr(family, "eval_required_concepts", ()) or ())
    procedure_terms = _usable_terms(procedure_terms)
    pathology_terms = _usable_terms(pathology_terms)
    location_terms = _usable_terms(location_terms)

    exact_procedure = _first_matching_term(title_text, procedure_terms)
    if exact_procedure:
        score += 30
        reasons.append(f"+30 exact procedure/approach phrase in title: {exact_procedure}")

    pathology_match = _first_matching_term(title_text, pathology_terms)
    if pathology_match:
        score += 20
        reasons.append(f"+20 pathology phrase in title: {pathology_match}")

    technique_match = _first_matching_term(full_text, TECHNIQUE_TERMS)
    if technique_match:
        score += 15
        reasons.append(f"+15 technique term in title/abstract: {technique_match}")

    if any(term in axis_text for term in ("complication", "outcome", "evidence")):
        outcome_match = _first_matching_term(full_text, COMPLICATION_TERMS)
        if outcome_match:
            score += 15
            reasons.append(
                f"+15 complication/outcome term for {axis or 'axis'} axis: {outcome_match}"
            )

    anatomy_terms = ANATOMY_AXIS_TERMS if "anatom" in axis_text else NEUROANATOMY_TERMS
    anatomy_match = _first_matching_term(full_text, tuple(location_terms) + anatomy_terms)
    if anatomy_match:
        score += 10
        reasons.append(f"+10 anatomy/location term: {anatomy_match}")

    publication_match = _axis_publication_match(full_text, axis_text)
    if publication_match:
        score += 10
        reasons.append(f"+10 axis-appropriate publication type: {publication_match}")

    source_tier = str(metadata.get("source_tier") or metadata.get("tier") or "").casefold()
    evidence_role = str(metadata.get("evidence_role") or "").casefold()
    if metadata.get("evidence_pack_id"):
        score += 15
        reasons.append("+15 procedure-specific evidence-pack source")
    if any(term in source_tier for term in ("practice-changing", "meta-analysis", "pooled")):
        score += 25
        reasons.append(f"+25 landmark evidence tier: {metadata.get('source_tier') or metadata.get('tier')}")
    elif "guideline" in source_tier or "consensus" in source_tier:
        score += 20
        reasons.append(f"+20 guideline/consensus evidence tier: {metadata.get('source_tier') or metadata.get('tier')}")
    elif "late-window" in source_tier or "large-core" in source_tier:
        score += 15
        reasons.append(f"+15 conditional EVT evidence tier: {metadata.get('source_tier') or metadata.get('tier')}")
    if any(term in evidence_role for term in ("early-window", "late-window", "guideline", "large-core", "pooled")):
        score += 10
        reasons.append(f"+10 EVT evidence role: {metadata.get('evidence_role')}")
    if metadata.get("clinical_include") is False:
        score -= 50
        reason = metadata.get("quarantine_reason") or "lower-applicability source"
        reasons.append(f"-50 quarantined from clinical synthesis: {reason}")

    family_context = tuple(procedure_terms + pathology_terms + location_terms)
    strict_family_context = _strict_context_terms(family_context)
    has_family_context = bool(_first_matching_term(full_text, strict_family_context))
    has_neuro_context = _count_matches(full_text, STRICT_NEURO_CONTEXT_TERMS) > 0
    drug_or_basic = _count_matches(full_text, DRUG_TERMS + BASIC_SCIENCE_TERMS) > 0
    non_neuro = _count_matches(full_text, NON_NEURO_TERMS) > 0
    if drug_or_basic and not (has_family_context or has_neuro_context):
        score -= 20
        reasons.append("-20 off-domain drug-only/basic-science content")
    if non_neuro and not (has_family_context or has_neuro_context):
        score -= 30
        reasons.append("-30 irrelevant non-neurosurgical context")
    if (drug_or_basic or non_neuro) and not (has_family_context or has_neuro_context):
        score -= 20
        reasons.append("-20 off-domain content lacks true neuro/family context")

    if not reasons:
        reasons.append("0 no surgical-usefulness heuristics matched")
    return score, reasons


def classify_clinical_applicability(
    record: "EvidenceRecord",
    case: "CaseSpec",
    family: "ProcedureFamily | None",
) -> tuple[bool, str]:
    """Return whether a retrieved source should feed case-specific synthesis.

    The evidence record remains preserved regardless of this classification; a
    False result only means it belongs in a lower-applicability/quarantine
    appendix rather than the operative bottom line.
    """
    text = f"{getattr(record, 'title', '') or ''} {getattr(record, 'text', '') or ''}"
    text_cf = text.casefold()
    case_text = _case_text(case)
    family_id = getattr(family, "id", "") if family is not None else ""
    is_thrombectomy = family_id == "endovascular_thrombectomy" or "thrombectomy" in case_text
    explicit_m1_case = bool(re.search(r"\bm1\b", case_text))
    explicit_m2_case = bool(re.search(r"\bm2\b", case_text))
    posterior_case = any(term in case_text for term in ("basilar", "posterior circulation"))
    primary_m1 = is_thrombectomy and explicit_m1_case and not explicit_m2_case and not posterior_case

    m2_specific = (
        bool(re.search(r"\bm2[-\s]?only\b", text_cf))
        or bool(re.search(r"\bisolated\s+m2\b", text_cf))
        or bool(re.search(r"\bm2\s+(?:segment\s+)?occlusions?\b", text_cf))
        or bool(re.search(r"\bm2\s+segment\b", text_cf))
        or "distal mca" in text_cf
        or "distal middle cerebral" in text_cf
    )
    m1_context = bool(re.search(r"\bm1\b", text_cf)) and not bool(
        re.search(r"\b(without|no|excluding|excluded|exclude)\s+m1\b", text_cf)
    )
    if primary_m1 and m2_specific and not m1_context:
        return False, "M2-only/distal-MCA source for primary M1 case"

    ai_terms = (
        "artificial intelligence",
        "deep learning",
        "machine learning",
        "ai workflow",
        "workflow triage",
        "detection software",
        "automated detection",
    )
    if is_thrombectomy and any(term in text_cf for term in ai_terms):
        return False, "AI/workflow-only source"

    if primary_m1 and any(
        term in text_cf
        for term in ("basilar", "vertebrobasilar", "posterior circulation", "posterior-circulation")
    ) and not any(term in text_cf for term in ("anterior circulation", "m1", "mca", "middle cerebral")):
        return False, "posterior-circulation-only source for anterior M1 case"

    if is_thrombectomy and any(
        term in text_cf
        for term in (
            "case report",
            "single case",
            "vignette",
            "rare anomaly",
            "aortic arch anomaly",
            "twig-like",
            "historical vignette",
            "historical review",
            "history of thrombectomy",
        )
    ):
        return False, "case report/rare anomaly or historical vignette source"

    stroke_neuro_terms = (
        "stroke",
        "cerebral",
        "brain",
        "intracranial",
        "neuro",
        "mca",
        "m1",
        "thrombectomy",
        "ischemic",
        "ischaemic",
    )
    if _count_matches(text, NON_NEURO_TERMS) > 0 and not any(term in text_cf for term in stroke_neuro_terms):
        return False, "non-stroke/non-neuro source"

    return True, "clinically applicable"


def _case_text(case: "CaseSpec") -> str:
    parts: list[str] = []
    for field_name in (
        "raw_input",
        "pathology",
        "procedure",
        "approach",
        "anatomic_location",
        "level_or_segment",
    ):
        field = getattr(case, field_name, None)
        value = getattr(field, "value", field)
        span = getattr(field, "span", None)
        if value:
            parts.append(str(value))
        if span:
            parts.append(str(span))
    return " ".join(parts).casefold()


def _normalize_pub_types(pub_types: list[str]) -> set[str]:
    return {str(pub_type).strip().lower() for pub_type in pub_types if pub_type}


def _case_terms(case: "CaseSpec", *field_names: str) -> list[str]:
    terms: list[str] = []
    for field_name in field_names:
        field = getattr(case, field_name, None)
        value = getattr(field, "value", None)
        span = getattr(field, "span", None)
        terms.extend(_split_term_values(value))
        terms.extend(_split_term_values(span))
    return terms


def _split_term_values(value: Any) -> list[str]:
    if value is None:
        return []
    return [part.strip() for part in str(value).split(";") if part.strip()]


def _usable_terms(terms: list[str] | tuple[str, ...]) -> list[str]:
    seen: set[str] = set()
    usable: list[str] = []
    for term in terms:
        normalized = str(term).strip().casefold()
        # Very short generic fragments create noisy matches; keep common acronyms.
        if len(normalized) < 4 and normalized not in {"acdf", "dbs", "mca", "m1", "m2", "c1"}:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        usable.append(str(term).strip())
    usable.sort(key=len, reverse=True)
    return usable


def _strict_context_terms(terms: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    """Return family/context terms that are not generic procedures/pathologies."""
    strict: list[str] = []
    for term in terms:
        normalized = str(term).strip().casefold()
        if not normalized or normalized in GENERIC_CONTEXT_TERMS:
            continue
        strict.append(str(term).strip())
    return tuple(strict)


def _first_matching_term(text: str, terms: tuple[str, ...] | list[str]) -> str | None:
    for term in terms:
        if _has_term(text, str(term)):
            return str(term)
    return None


def _axis_publication_match(full_text: str, axis_text: str) -> str | None:
    if "technique" in axis_text or "anatom" in axis_text:
        return _first_matching_term(full_text, TECHNICAL_PUBLICATION_TERMS)
    if "review" in axis_text or "landmark" in axis_text:
        return _first_matching_term(full_text, REVIEW_PUBLICATION_TERMS)
    if "outcome" in axis_text or "evidence" in axis_text:
        return _first_matching_term(full_text, REVIEW_PUBLICATION_TERMS + ("cohort", "series"))
    if "complication" in axis_text:
        return _first_matching_term(full_text, ("operative series", "case series", "cohort", "review"))
    return None


def _count_matches(text: str, terms: tuple[str, ...]) -> int:
    return sum(1 for term in terms if _has_term(text, term))


def _has_term(text: str, term: str) -> bool:
    escaped = re.escape(term.lower())
    pattern = escaped.replace(r"\ ", r"[\s-]+").replace(r"\-", r"[\s-]+")
    return bool(re.search(rf"(?<!\w){pattern}(?!\w)", text.lower()))
