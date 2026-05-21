"""Deterministic parsing of free-text neurosurgical case descriptions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from caseprep.procedure_taxonomy import ProcedureFamily, iter_procedure_families


@dataclass(frozen=True)
class CaseField:
    value: str | None
    confidence: float
    source: str  # extracted | synonym | inferred | llm | missing
    span: str | None = None
    notes: str | None = None

    def to_dict(self) -> dict[str, str | float | None]:
        return {
            "value": self.value,
            "confidence": self.confidence,
            "source": self.source,
            "span": self.span,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class CaseSpec:
    raw_input: str
    pathology: CaseField
    procedure: CaseField
    approach: CaseField
    procedure_family: CaseField
    broad_profile: CaseField
    laterality: CaseField
    level_or_segment: CaseField
    size: CaseField
    anatomic_location: CaseField
    patient_modifiers: tuple[CaseField, ...]
    imaging_modifiers: tuple[CaseField, ...]
    missing_critical_facts: tuple[str, ...]
    degraded: bool
    degradation_reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "raw_input": self.raw_input,
            "pathology": self.pathology.to_dict(),
            "procedure": self.procedure.to_dict(),
            "approach": self.approach.to_dict(),
            "procedure_family": self.procedure_family.to_dict(),
            "broad_profile": self.broad_profile.to_dict(),
            "laterality": self.laterality.to_dict(),
            "level_or_segment": self.level_or_segment.to_dict(),
            "size": self.size.to_dict(),
            "anatomic_location": self.anatomic_location.to_dict(),
            "patient_modifiers": [field.to_dict() for field in self.patient_modifiers],
            "imaging_modifiers": [field.to_dict() for field in self.imaging_modifiers],
            "missing_critical_facts": list(self.missing_critical_facts),
            "degraded": self.degraded,
            "degradation_reason": self.degradation_reason,
        }


_MISSING = CaseField(None, 0.0, "missing")


_PROCEDURE_PATTERNS: tuple[tuple[str, str, str, float], ...] = (
    (r"\banterior cervical discectomy and fusion\b", "anterior cervical discectomy and fusion", "extracted", 0.99),
    (r"\bACDF\b", "ACDF", "synonym", 0.95),
    (r"\bsuboccipital craniectomy\s+and\s+C1\s+laminectomy\b", "suboccipital craniectomy and C1 laminectomy", "extracted", 0.99),
    (r"\bposterior fossa decompression\b", "posterior fossa decompression", "extracted", 0.95),
    (r"\bmechanical thrombectomy\b", "mechanical thrombectomy", "extracted", 0.99),
    (r"\bendovascular thrombectomy\b", "endovascular thrombectomy", "extracted", 0.97),
    (r"\bstroke thrombectomy\b", "stroke thrombectomy", "extracted", 0.9),
    (r"\b(?:frontal\s+)?convexity meningioma resection\b", "convexity meningioma resection", "extracted", 0.98),
    (r"\bmeningioma resection\b", "meningioma resection", "extracted", 0.95),
    (r"\bresection\b", "resection", "extracted", 0.8),
    (r"\bcraniotomy\b", "craniotomy", "extracted", 0.85),
)

_PATHOLOGY_PATTERNS: tuple[tuple[str, str, str, float], ...] = (
    (r"\bC\d+\s+radiculopathy\b", "cervical radiculopathy", "synonym", 0.95),
    (r"\bcervical radiculopathy\b", "cervical radiculopathy", "extracted", 0.98),
    (r"\bforaminal disc osteophyte complex\b", "foraminal disc osteophyte complex", "extracted", 0.98),
    (r"\bdisc osteophyte complex\b", "disc osteophyte complex", "extracted", 0.95),
    (r"\bfrontal convexity meningioma\b", "frontal convexity meningioma", "extracted", 0.99),
    (r"\bconvexity meningioma\b", "convexity meningioma", "extracted", 0.98),
    (r"\bmeningioma\b", "meningioma", "extracted", 0.75),
    (r"\bChiari\s*(?:I|1)?\s*malformation\b", "Chiari I malformation", "extracted", 0.99),
    (r"\bChiari\b", "Chiari", "extracted", 0.75),
    (r"\bsyringomyelia\b", "syringomyelia", "extracted", 0.9),
    (r"\bsyrinx\b", "syrinx", "extracted", 0.9),
    (r"\bacute ischemic stroke\b", "acute ischemic stroke", "extracted", 0.99),
    (r"\bM1\s+(?:middle cerebral artery\s+)?occlusion\b", "M1 occlusion", "extracted", 0.99),
    (r"\bmiddle cerebral artery occlusion\b", "middle cerebral artery occlusion", "extracted", 0.98),
    (r"\bMCA occlusion\b", "MCA occlusion", "extracted", 0.98),
    (r"\bvestibular schwannoma\b", "vestibular schwannoma", "extracted", 0.95),
    (r"\bMCA aneurysm\b", "MCA aneurysm", "extracted", 0.95),
)

_APPROACH_PATTERNS: tuple[tuple[str, str, str, float], ...] = (
    (r"\banterior cervical\b", "anterior cervical", "extracted", 0.95),
    (r"\bsuboccipital\b", "suboccipital", "extracted", 0.95),
    (r"\bfrontal craniotomy\b", "frontal craniotomy", "extracted", 0.95),
    (r"\bconvexity craniotomy\b", "convexity craniotomy", "extracted", 0.95),
    (r"\btransfemoral\b", "transfemoral access", "extracted", 0.9),
    (r"\bradial access\b", "radial access", "extracted", 0.9),
)

_LOCATION_PATTERNS: tuple[tuple[str, str, str, float], ...] = (
    (r"\bfrontal convexity\b", "frontal convexity", "extracted", 0.95),
    (r"\bsuperior sagittal sinus\b", "superior sagittal sinus", "extracted", 0.95),
    (r"\bmiddle cerebral artery\b", "middle cerebral artery", "extracted", 0.95),
    (r"\bMCA\b", "MCA", "synonym", 0.9),
    (r"\bforamen magnum\b", "foramen magnum", "extracted", 0.9),
)

_SIZE_RE = re.compile(r"\b\d+(?:\.\d+)?\s*(?:mm|cm)\b", re.IGNORECASE)
_LEVEL_RE = re.compile(
    r"\b(?:C\d+(?:\s*[-/]\s*\d+)?|M[1-4]|MCA|ACA|PCA|basilar)\b",
    re.IGNORECASE,
)
_LATERALITY_RE = re.compile(r"\b(right|left|bilateral)\b", re.IGNORECASE)


def parse_case_input(raw_input: str, *, use_llm: bool = False) -> CaseSpec:
    """Parse a free-text case; currently deterministic even when use_llm is true."""
    return deterministic_parse_case(raw_input)


def deterministic_parse_case(raw_input: str) -> CaseSpec:
    """Parse case text using only regexes and known aliases, without silent guessing."""
    text = raw_input.strip()

    pathology = _extract_combined(text, _PATHOLOGY_PATTERNS)
    procedure = _extract_procedure(text)
    approach = _extract_first(text, _APPROACH_PATTERNS)
    laterality = _extract_regex(text, _LATERALITY_RE, "extracted", 0.95)
    level_or_segment = _extract_regex(text, _LEVEL_RE, "extracted", 0.9)
    size = _extract_regex(text, _SIZE_RE, "extracted", 0.95)
    anatomic_location = _extract_combined(text, _LOCATION_PATTERNS)
    patient_modifiers = _extract_modifiers(text)
    imaging_modifiers = _extract_imaging_modifiers(text)

    family = _select_family_from_parts(text, pathology, procedure, approach)
    procedure_family = _family_field(family, pathology=pathology, procedure=procedure, approach=approach)
    broad_profile = (
        CaseField(
            family.broad_profile,
            procedure_family.confidence,
            procedure_family.source,
            notes=f"from {family.id}",
        )
        if family is not None
        else _MISSING
    )

    missing = _missing_critical_facts(
        text=text,
        family=family,
        procedure=procedure,
        approach=approach,
        pathology=pathology,
        laterality=laterality,
        level_or_segment=level_or_segment,
        anatomic_location=anatomic_location,
    )
    degraded = _is_degraded(family=family, procedure=procedure, approach=approach, missing=missing)
    degradation_reason = None
    if degraded:
        degradation_reason = "Missing critical facts: " + "; ".join(missing)
        if family is None:
            degradation_reason = "No supported procedure family identified"
            if missing:
                degradation_reason += "; missing critical facts: " + "; ".join(missing)

    return CaseSpec(
        raw_input=raw_input,
        pathology=pathology,
        procedure=procedure,
        approach=approach,
        procedure_family=procedure_family,
        broad_profile=broad_profile,
        laterality=laterality,
        level_or_segment=level_or_segment,
        size=size,
        anatomic_location=anatomic_location,
        patient_modifiers=patient_modifiers,
        imaging_modifiers=imaging_modifiers,
        missing_critical_facts=tuple(missing),
        degraded=degraded,
        degradation_reason=degradation_reason,
    )


def select_procedure_family(case: CaseSpec) -> ProcedureFamily | None:
    """Return the taxonomy family selected for a parsed case, if any."""
    if case.procedure_family.value:
        for family in iter_procedure_families():
            if family.id == case.procedure_family.value:
                return family
    return _select_family_from_parts(
        case.raw_input,
        case.pathology,
        case.procedure,
        case.approach,
    )


def _extract_first(text: str, patterns: Iterable[tuple[str, str, str, float]]) -> CaseField:
    matches = _pattern_matches(text, patterns)
    if not matches:
        return _MISSING
    return matches[0]


def _extract_combined(text: str, patterns: Iterable[tuple[str, str, str, float]]) -> CaseField:
    matches = _pattern_matches(text, patterns)
    if not matches:
        return _MISSING
    values: list[str] = []
    spans: list[str] = []
    confidence = 0.0
    source = "extracted"
    for match in matches:
        if match.value and match.value.casefold() not in {v.casefold() for v in values}:
            values.append(match.value)
            if match.span:
                spans.append(match.span)
            confidence = max(confidence, match.confidence)
            if match.source == "synonym" and source == "extracted":
                source = "synonym"
    return CaseField("; ".join(values), confidence, source, span="; ".join(spans) or None)


def _pattern_matches(text: str, patterns: Iterable[tuple[str, str, str, float]]) -> list[CaseField]:
    matches: list[tuple[int, int, CaseField]] = []
    for pattern, value, source, confidence in patterns:
        found = re.search(pattern, text, re.IGNORECASE)
        if found:
            span = found.group(0)
            matches.append((found.start(), -len(span), CaseField(value, confidence, source, span=span)))
    matches.sort(key=lambda item: (item[0], item[1]))
    return [item[2] for item in matches]


def _extract_regex(text: str, regex: re.Pattern[str], source: str, confidence: float) -> CaseField:
    found = regex.search(text)
    if not found:
        return _MISSING
    span = found.group(0)
    value = _normalize_level(span) if regex is _LEVEL_RE else span.lower() if regex is _LATERALITY_RE else span
    return CaseField(value, confidence, source, span=span)


def _extract_procedure(text: str) -> CaseField:
    # Bare topic words should not become a procedure. This intentionally does not
    # infer Chiari decompression from "Chiari" or ACDF from "cervical radiculopathy".
    procedure = _extract_first(text, _PROCEDURE_PATTERNS)
    if procedure.value == "resection" and "meningioma" in text.casefold():
        return CaseField("meningioma resection", 0.9, "inferred", span=procedure.span)
    return procedure


def _normalize_level(level: str) -> str:
    normalized = re.sub(r"\s+", "", level.upper())
    if re.match(r"C\d+-\d+", normalized):
        return normalized
    return normalized


def _extract_modifiers(text: str) -> tuple[CaseField, ...]:
    modifiers: list[CaseField] = []
    for pattern, value in (
        (r"\bsyringomyelia\b", "syringomyelia"),
        (r"\bsyrinx\b", "syrinx"),
        (r"\bmyelopathy\b", "myelopathy"),
        (r"\bradiculopathy\b", "radiculopathy"),
    ):
        found = re.search(pattern, text, re.IGNORECASE)
        if found:
            modifiers.append(CaseField(value, 0.9, "extracted", span=found.group(0)))
    return tuple(modifiers)


def _extract_imaging_modifiers(text: str) -> tuple[CaseField, ...]:
    modifiers: list[CaseField] = []
    for pattern, value in (
        (r"\bASPECTS\b", "ASPECTS"),
        (r"\bperfusion\b", "perfusion imaging"),
        (r"\bCTA\b", "CTA"),
        (r"\bMRI\b", "MRI"),
    ):
        found = re.search(pattern, text, re.IGNORECASE)
        if found:
            modifiers.append(CaseField(value, 0.85, "extracted", span=found.group(0)))
    return tuple(modifiers)


def _family_field(
    family: ProcedureFamily | None,
    *,
    pathology: CaseField,
    procedure: CaseField,
    approach: CaseField,
) -> CaseField:
    if family is None:
        return _MISSING

    # Family selection is deterministic but not equally certain for all inputs.
    # A named operation is strong evidence; a bare disease topic is weaker and
    # should remain visibly provisional for downstream builders.
    if procedure.value is not None:
        if procedure.confidence >= 0.97:
            confidence = 0.95
        elif procedure.confidence >= 0.9:
            confidence = 0.88
        else:
            confidence = 0.82
        source = "inferred"
        notes = f"from procedure: {procedure.value}"
    elif approach.value is not None:
        confidence = min(0.86, max(0.72, approach.confidence - 0.08))
        source = "inferred"
        notes = f"from approach: {approach.value}"
    elif pathology.value is not None:
        confidence = min(0.78, max(0.62, pathology.confidence - 0.2))
        source = "synonym" if pathology.source == "synonym" else "inferred"
        notes = f"topic/pathology-only match: {pathology.value}"
    else:
        confidence = 0.6
        source = "inferred"
        notes = "weak alias match"

    return CaseField(family.id, confidence, source, notes=f"{family.display_name}; {notes}")


def _is_degraded(
    *,
    family: ProcedureFamily | None,
    procedure: CaseField,
    approach: CaseField,
    missing: Iterable[str],
) -> bool:
    if family is None:
        return True
    if procedure.value is None:
        return True
    if "pathology" in set(missing):
        return True
    if family.id in {"spine_acdf", "posterior_fossa_chiari"} and approach.value is None:
        return True
    # The thrombectomy and convexity tumor builders can still proceed from a
    # named procedure/pathology while surfacing family-specific prompts.
    return False


def _select_family_from_parts(
    text: str,
    pathology: CaseField,
    procedure: CaseField,
    approach: CaseField,
) -> ProcedureFamily | None:
    normalized = text.casefold()
    scored: list[tuple[int, ProcedureFamily]] = []
    for family in iter_procedure_families():
        score = 0
        score += _alias_score(normalized, family.procedure_aliases, 4)
        score += _alias_score(normalized, family.pathology_aliases, 3)
        score += _alias_score(normalized, family.approach_aliases, 2)
        combined_fields = " ".join(
            field.value or "" for field in (pathology, procedure, approach)
        ).casefold()
        score += _alias_score(combined_fields, family.procedure_aliases, 2)
        score += _alias_score(combined_fields, family.pathology_aliases, 2)
        if family.id == "posterior_fossa_chiari" and "chiari" in normalized:
            score += 3
        if family.id == "spine_acdf" and "cervical radiculopathy" in normalized:
            score += 3
        if family.id == "endovascular_thrombectomy" and "thrombectomy" in normalized:
            score += 4
        if score:
            scored.append((score, family))
    if not scored:
        return None
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1]


def _alias_score(text: str, aliases: Iterable[str], weight: int) -> int:
    return sum(weight for alias in aliases if alias.casefold() in text)


def _missing_critical_facts(
    *,
    text: str,
    family: ProcedureFamily | None,
    procedure: CaseField,
    approach: CaseField,
    pathology: CaseField,
    laterality: CaseField,
    level_or_segment: CaseField,
    anatomic_location: CaseField,
) -> list[str]:
    missing: list[str] = []
    normalized = text.casefold()
    if pathology.value is None:
        missing.append("pathology")
    if procedure.value is None:
        missing.append("procedure")

    if family is None:
        if procedure.value is None:
            missing.append("supported procedure family")
        else:
            missing.append("supported procedure family for procedure")
        if approach.value is None:
            missing.append("approach")
        return _unique(missing)

    if family.id in {"spine_acdf", "posterior_fossa_chiari"} and approach.value is None:
        missing.append("approach")
    if family.id == "spine_acdf":
        if level_or_segment.value is None:
            missing.append("cervical level")
        if laterality.value is None:
            missing.append("symptomatic laterality")
        if procedure.value is None:
            missing.append("fusion/decompression plan")
    elif family.id == "tumor_convexity_meningioma":
        if anatomic_location.value is None:
            missing.append("tumor location")
        if not _has_venous_or_sinus_relationship(normalized):
            missing.append("venous/sinus relationship")
        if procedure.value is None:
            missing.append("resection/craniotomy plan")
    elif family.id == "posterior_fossa_chiari":
        if procedure.value is None:
            missing.append("decompression plan")
    elif family.id == "endovascular_thrombectomy":
        if level_or_segment.value is None and "occlusion" not in (pathology.value or "").casefold():
            missing.append("occlusion location")
        if not _has_last_known_well(normalized):
            missing.append("last-known-well time")
        if not _has_nihss(normalized):
            missing.append("NIHSS")
        if not _has_thrombectomy_imaging_selection(normalized):
            missing.append("imaging selection")
        if not _has_thrombectomy_access_plan(normalized):
            missing.append("access plan")
    return _unique(missing)


def _has_venous_or_sinus_relationship(normalized_text: str) -> bool:
    return any(
        term in normalized_text
        for term in (
            "superior sagittal sinus",
            "sagittal sinus",
            "sinus",
            "bridging vein",
            "cortical vein",
            "venous",
        )
    )


def _has_last_known_well(normalized_text: str) -> bool:
    return any(
        term in normalized_text
        for term in ("last-known-well", "last known well", "lkw", "time from onset", "onset")
    )


def _has_nihss(normalized_text: str) -> bool:
    return "nihss" in normalized_text or "national institutes of health stroke scale" in normalized_text


def _has_thrombectomy_imaging_selection(normalized_text: str) -> bool:
    return any(
        term in normalized_text
        for term in ("aspects", "perfusion", "ctp", "cta", "ct angiography", "mri", "dwi")
    )


def _has_thrombectomy_access_plan(normalized_text: str) -> bool:
    return any(
        term in normalized_text
        for term in (
            "transfemoral",
            "femoral access",
            "radial access",
            "transradial",
            "balloon guide",
            "distal access",
            "aspiration",
            "stent retriever",
        )
    )


def _unique(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    unique_items: list[str] = []
    for item in items:
        if item not in seen:
            unique_items.append(item)
            seen.add(item)
    return unique_items
