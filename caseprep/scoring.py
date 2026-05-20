"""Evidence grading and neurosurgical relevance scoring helpers."""

from __future__ import annotations

from dataclasses import dataclass
import re


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
    score = 0.0
    score += 20.0 * _count_matches(text, PROCEDURE_TERMS)
    score += 10.0 * _count_matches(text, OUTCOME_TERMS)

    neuroanatomy_matches = _count_matches(text, NEUROANATOMY_TERMS)
    score += 10.0 * neuroanatomy_matches

    if neuroanatomy_matches == 0:
        score -= 30.0 * _count_matches(text, NON_NEURO_TERMS)

    if score == 0:
        score -= 20.0 * _count_matches(text, DRUG_TERMS)

    return score


def _normalize_pub_types(pub_types: list[str]) -> set[str]:
    return {str(pub_type).strip().lower() for pub_type in pub_types if pub_type}


def _count_matches(text: str, terms: tuple[str, ...]) -> int:
    return sum(1 for term in terms if _has_term(text, term))


def _has_term(text: str, term: str) -> bool:
    escaped = re.escape(term.lower())
    pattern = escaped.replace(r"\ ", r"[\s-]+").replace(r"\-", r"[\s-]+")
    return bool(re.search(rf"(?<!\w){pattern}(?!\w)", text.lower()))
