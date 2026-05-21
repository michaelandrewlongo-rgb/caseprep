"""Evidence packs for acute ischemic stroke mechanical thrombectomy.

The registry is deliberately deterministic: it lists papers/guidelines that must
be attempted for a specific canonical case before generic search results are
allowed to dominate the dossier.  Missing items are tracked honestly by callers;
this module only declares what should be sought.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


@dataclass(frozen=True)
class EvidencePackItem:
    """A source target in a procedure-specific evidence pack."""

    id: str
    title_hint: str
    tier: str
    applicability_summary: str
    required_for: tuple[str, ...]
    pmid: str | None = None
    doi: str | None = None
    query_fallback: str = ""
    must_retrieve: bool = True
    conditional: bool = False

    @property
    def applicability(self) -> str:
        """Backward-compatible alias used by callers/renderers."""
        return self.applicability_summary

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title_hint": self.title_hint,
            "tier": self.tier,
            "applicability": self.applicability_summary,
            "applicability_summary": self.applicability_summary,
            "required_for": list(self.required_for),
            "pmid": self.pmid,
            "doi": self.doi,
            "query_fallback": self.query_fallback,
            "must_retrieve": self.must_retrieve,
            "conditional": self.conditional,
        }


@dataclass(frozen=True)
class EvidencePack:
    """A deterministic group of landmark sources for a clinical scenario."""

    id: str
    display_name: str
    procedure_family: str
    items: tuple[EvidencePackItem, ...]
    applicability_summary: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "display_name": self.display_name,
            "procedure_family": self.procedure_family,
            "applicability_summary": self.applicability_summary,
            "items": [item.to_dict() for item in self.items],
        }


def _item(
    id: str,
    title_hint: str,
    tier: str,
    applicability_summary: str,
    required_for: tuple[str, ...],
    *,
    pmid: str | None = None,
    doi: str | None = None,
    query_fallback: str | None = None,
    must_retrieve: bool = True,
    conditional: bool = False,
) -> EvidencePackItem:
    fallback = query_fallback or " ".join(
        part for part in (title_hint, pmid, doi) if part
    )
    return EvidencePackItem(
        id=id,
        title_hint=title_hint,
        tier=tier,
        applicability_summary=applicability_summary,
        required_for=required_for,
        pmid=pmid,
        doi=doi,
        query_fallback=fallback,
        must_retrieve=must_retrieve,
        conditional=conditional,
    )


ANTERIOR_CIRCULATION_LVO_M1 = EvidencePack(
    id="anterior_circulation_lvo_m1",
    display_name="Anterior-circulation M1 large-vessel occlusion EVT evidence pack",
    procedure_family="endovascular_thrombectomy",
    applicability_summary=(
        "Applies to mechanical thrombectomy for a proximal anterior-circulation "
        "large-vessel occlusion such as M1 MCA, subject to patient-specific "
        "time-window, imaging/core, disability, premorbid status, and protocol criteria."
    ),
    items=(
        _item(
            "mr_clean",
            "A Randomized Trial of Intraarterial Treatment for Acute Ischemic Stroke",
            "practice-changing RCT",
            "Directly applicable early-window anterior-circulation proximal LVO EVT trial.",
            ("early-window EVT trial", "landmark coverage"),
            pmid="25517348",
            doi="10.1056/NEJMoa1411587",
            query_fallback="MR CLEAN randomized trial intraarterial treatment acute ischemic stroke thrombectomy",
        ),
        _item(
            "escape",
            "Randomized Assessment of Rapid Endovascular Treatment of Ischemic Stroke",
            "practice-changing RCT",
            "Directly applicable early-window anterior-circulation LVO EVT trial emphasizing rapid workflow and imaging selection.",
            ("early-window EVT trial", "workflow evidence"),
            pmid="25671798",
            doi="10.1056/NEJMoa1414905",
            query_fallback="ESCAPE randomized rapid endovascular treatment ischemic stroke thrombectomy",
        ),
        _item(
            "extend_ia",
            "Endovascular Therapy for Ischemic Stroke with Perfusion-Imaging Selection",
            "practice-changing RCT",
            "Early-window anterior-circulation EVT trial with perfusion-mismatch selection relevance.",
            ("early-window EVT trial", "imaging selection"),
            pmid="25671797",
            doi="10.1056/NEJMoa1414792",
            query_fallback="EXTEND-IA endovascular therapy ischemic stroke perfusion imaging selection",
        ),
        _item(
            "swift_prime",
            "Stent-retriever thrombectomy after intravenous t-PA vs t-PA alone in stroke",
            "practice-changing RCT",
            "Directly applicable stent-retriever EVT trial for proximal anterior-circulation stroke.",
            ("early-window EVT trial", "device-class evidence"),
            pmid="25882376",
            doi="10.1056/NEJMoa1415061",
            query_fallback="SWIFT PRIME stent retriever thrombectomy intravenous tPA stroke randomized",
        ),
        _item(
            "revascat",
            "Thrombectomy within 8 hours after symptom onset in ischemic stroke",
            "practice-changing RCT",
            "Directly applicable anterior-circulation EVT trial extending early treatment window evidence.",
            ("early-window EVT trial", "landmark coverage"),
            pmid="25882510",
            doi="10.1056/NEJMoa1503780",
            query_fallback="REVASCAT thrombectomy 8 hours symptom onset ischemic stroke randomized",
        ),
        _item(
            "hermes",
            "Endovascular thrombectomy after large-vessel ischaemic stroke: pooled HERMES meta-analysis",
            "pooled patient-level meta-analysis",
            "High-level synthesis of the pivotal early-window EVT trials for anterior-circulation LVO.",
            ("pooled evidence", "landmark coverage", "subgroup expectations"),
            pmid="26898852",
            doi="10.1016/S0140-6736(16)00163-X",
            query_fallback="HERMES collaboration endovascular thrombectomy large vessel ischaemic stroke pooled analysis",
        ),
        _item(
            "dawn",
            "Thrombectomy 6 to 24 Hours after Stroke with a Mismatch between Deficit and Infarct",
            "late-window RCT",
            "Conditionally applicable only if DAWN clinical-core mismatch/time-window criteria are met.",
            ("late-window EVT evidence", "imaging selection"),
            pmid="29129157",
            doi="10.1056/NEJMoa1706442",
            query_fallback="DAWN thrombectomy 6 to 24 hours mismatch deficit infarct stroke",
        ),
        _item(
            "defuse_3",
            "Thrombectomy for Stroke at 6 to 16 Hours with Selection by Perfusion Imaging",
            "late-window RCT",
            "Conditionally applicable only if DEFUSE 3 perfusion mismatch/time-window criteria are met.",
            ("late-window EVT evidence", "perfusion selection"),
            pmid="29364767",
            doi="10.1056/NEJMoa1713973",
            query_fallback="DEFUSE 3 thrombectomy stroke 6 to 16 hours perfusion imaging",
        ),
        _item(
            "aha_asa_2019_update",
            "2019 Update to the 2018 AHA/ASA Guidelines for Early Management of Acute Ischemic Stroke",
            "guideline/consensus",
            "Use to verify current EVT eligibility and peri-procedural management standards, while checking for newer updates.",
            ("guideline", "eligibility standards", "peri-procedural management"),
            pmid="31662037",
            doi="10.1161/STR.0000000000000211",
            query_fallback="2019 AHA ASA guideline update early management acute ischemic stroke thrombectomy",
        ),
        _item(
            "aha_asa_2018_guideline",
            "2018 Guidelines for Early Management of Patients With Acute Ischemic Stroke",
            "guideline/consensus",
            "Foundational AHA/ASA acute ischemic stroke guideline; use with updates/current guidance.",
            ("guideline", "eligibility standards"),
            pmid="29367334",
            doi="10.1161/STR.0000000000000158",
            query_fallback="2018 AHA ASA guidelines early management acute ischemic stroke thrombectomy",
        ),
        _item(
            "aha_asa_current_guideline",
            "Current AHA/ASA guideline for acute ischemic stroke EVT",
            "guideline/consensus",
            "Current guideline target for eligibility, workflow, BP, thrombolytic, and post-EVT standards.",
            ("guideline", "current standards"),
            pmid="41582814",
            doi="10.1161/STR.0000000000000513",
            query_fallback="AHA ASA current guideline acute ischemic stroke endovascular thrombectomy",
        ),
        _item(
            "eso_esmint_guideline_2019",
            "ESO-ESMINT Guidelines on Mechanical Thrombectomy in Acute Ischaemic Stroke",
            "guideline/consensus",
            "European guideline/consensus target for EVT eligibility and workflow standards.",
            ("guideline", "international consensus"),
            pmid="31152058",
            query_fallback="ESO ESMINT guidelines mechanical thrombectomy acute ischaemic stroke 2019",
        ),
        _item(
            "eso_esmint_recommendations",
            "European recommendations on organisation of interventional care in acute stroke",
            "guideline/consensus",
            "International consensus source for systems, transfer, and treatment workflow context.",
            ("guideline", "workflow consensus"),
            pmid="31165090",
            query_fallback="ESO ESMINT recommendations organisation interventional care acute stroke thrombectomy",
        ),
        _item(
            "eso_esmint_technical_guideline",
            "ESO/ESMINT technical guidance for mechanical thrombectomy practice",
            "guideline/consensus",
            "Technical and peri-procedural consensus source; verify against local protocol.",
            ("guideline", "technical practice"),
            pmid="30808653",
            query_fallback="ESO ESMINT technical guidance mechanical thrombectomy practice acute stroke",
        ),
        _item(
            "rescue_japan_limit",
            "Endovascular Therapy for Acute Stroke with a Large Ischemic Region",
            "large-core conditional RCT",
            "Conditional large-core evidence; only applicable if ASPECTS/core and patient factors match trial criteria.",
            ("large-core conditional evidence",),
            pmid="35138767",
            doi="10.1056/NEJMoa2118191",
            query_fallback="RESCUE-Japan LIMIT endovascular therapy acute stroke large ischemic region",
            conditional=True,
        ),
        _item(
            "select2",
            "Trial of Endovascular Thrombectomy for Large Ischemic Strokes",
            "large-core conditional RCT",
            "Conditional large-core evidence; do not apply without core/ASPECTS, edema, hemorrhage-risk, and premorbid-status context.",
            ("large-core conditional evidence",),
            pmid="36762865",
            doi="10.1056/NEJMoa2214403",
            query_fallback="SELECT2 trial endovascular thrombectomy large ischemic strokes",
            conditional=True,
        ),
        _item(
            "angel_aspect",
            "Trial of Endovascular Therapy for Acute Ischemic Stroke with Large Infarct",
            "large-core conditional RCT",
            "Conditional large-core evidence; applicability depends on imaging and local stroke-team selection.",
            ("large-core conditional evidence",),
            pmid="36762852",
            doi="10.1056/NEJMoa2213379",
            query_fallback="ANGEL-ASPECT endovascular therapy acute ischemic stroke large infarct",
            conditional=True,
        ),
        _item(
            "tension",
            "Endovascular thrombectomy for acute ischaemic stroke with established large infarct",
            "large-core conditional RCT",
            "Conditional large-core evidence; only applicable to selected established large-infarct patients.",
            ("large-core conditional evidence",),
            pmid="37837989",
            doi="10.1016/S0140-6736(23)02032-9",
            query_fallback="TENSION trial endovascular thrombectomy established large infarct acute ischaemic stroke",
            conditional=True,
        ),
        _item(
            "laste",
            "Large Stroke Therapy Evaluation trial of thrombectomy for large infarct stroke",
            "large-core conditional RCT",
            "Conditional large-core evidence; verify inclusion criteria before applying to an individual M1 case.",
            ("large-core conditional evidence",),
            pmid="38718358",
            doi="10.1056/NEJMoa2314063",
            query_fallback="LASTE trial thrombectomy large infarct stroke",
            conditional=True,
        ),
    ),
)


THROMBECTOMY_PACKS: dict[str, EvidencePack] = {
    ANTERIOR_CIRCULATION_LVO_M1.id: ANTERIOR_CIRCULATION_LVO_M1,
}


def get_thrombectomy_pack(pack_id: str) -> EvidencePack | None:
    """Look up a thrombectomy evidence pack by ID."""
    return THROMBECTOMY_PACKS.get(pack_id)


def resolve_thrombectomy_pack(case_spec: Any) -> EvidencePack | None:
    """Resolve a thrombectomy evidence pack from a structured case.

    This intentionally requires a specific anterior-circulation/M1 target.  A
    vague "stroke thrombectomy" topic should keep using generic retrieval rather
    than silently inheriting the M1 landmark pack.
    """
    text = _case_haystack(case_spec)
    if not text.strip():
        return None
    if "thrombectomy" not in text:
        return None
    if any(term in text for term in ("basilar", "vertebrobasilar", "posterior circulation")):
        return None
    if re.search(r"\bm2\b", text) or "distal mca" in text:
        return None
    has_m1_target = bool(re.search(r"\bm1\b", text))
    has_stroke_context = any(
        term in text
        for term in (
            "acute ischemic stroke",
            "acute ischaemic stroke",
            "large vessel occlusion",
            "lvo",
            "m1 occlusion",
            "mca occlusion",
            "middle cerebral artery occlusion",
        )
    )
    if has_m1_target and has_stroke_context:
        return ANTERIOR_CIRCULATION_LVO_M1
    return None


def _case_haystack(case_spec: Any) -> str:
    parts: list[str] = []
    for attr in (
        "raw_input",
        "pathology",
        "procedure",
        "approach",
        "anatomic_location",
        "level_or_segment",
    ):
        value = getattr(case_spec, attr, None)
        if value is None:
            continue
        field_value = getattr(value, "value", value)
        field_span = getattr(value, "span", None)
        if field_value:
            parts.append(str(field_value))
        if field_span:
            parts.append(str(field_span))
    return " ".join(parts).casefold()
