"""Procedure-family taxonomy for V1 case preparation profiles."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType


@dataclass(frozen=True)
class ProcedureFamily:
    id: str
    display_name: str
    broad_profile: str
    procedure_aliases: tuple[str, ...]
    pathology_aliases: tuple[str, ...]
    approach_aliases: tuple[str, ...]
    required_fields: tuple[str, ...]
    missing_fact_prompts: tuple[str, ...]
    retrieval_templates: Mapping[str, str]
    section_headings: Mapping[str, tuple[str, ...]]
    eval_required_concepts: tuple[str, ...]


def _freeze_mapping(mapping: Mapping[str, str]) -> Mapping[str, str]:
    """Return a read-only shallow copy of a string mapping."""
    return MappingProxyType(dict(mapping))


def _freeze_heading_mapping(
    mapping: Mapping[str, tuple[str, ...]],
) -> Mapping[str, tuple[str, ...]]:
    """Return a read-only copy of section headings with tuple values."""
    return MappingProxyType({key: tuple(value) for key, value in mapping.items()})


_COMMON_SECTION_HEADINGS = _freeze_heading_mapping({
    "anatomy_at_risk": (
        "Key landmarks",
        "Neural structures",
        "Vascular structures",
        "No-fly zones",
    ),
    "operative_plan": (
        "Positioning and setup",
        "Exposure and localization",
        "Procedure steps",
        "Closure and reconstruction",
    ),
    "risk_and_rescue": (
        "Expected complications",
        "Prevention strategies",
        "Rescue maneuvers",
    ),
    "evidence": (
        "Indications and alternatives",
        "Outcomes",
        "Landmark or review evidence",
    ),
})


PROCEDURE_FAMILIES: Mapping[str, ProcedureFamily] = MappingProxyType({
    "spine_acdf": ProcedureFamily(
        id="spine_acdf",
        display_name="Anterior cervical discectomy and fusion (ACDF)",
        broad_profile="spine",
        procedure_aliases=(
            "acdf",
            "anterior cervical discectomy and fusion",
            "cervical discectomy and fusion",
            "c5-6 acdf",
        ),
        pathology_aliases=(
            "cervical radiculopathy",
            "c6 radiculopathy",
            "foraminal disc osteophyte complex",
            "cervical disc herniation",
            "cervical spondylosis",
        ),
        approach_aliases=(
            "anterior cervical approach",
            "smith-robinson approach",
            "right-sided anterior cervical exposure",
        ),
        required_fields=(
            "level",
            "laterality",
            "radiculopathy_or_myelopathy",
            "compressive_pathology",
            "fusion_construct",
        ),
        missing_fact_prompts=(
            "What cervical level(s) require decompression and fusion?",
            "What is the symptomatic side and root distribution?",
            "Is the main compression disc, osteophyte, uncovertebral, or foraminal?",
            "What graft/cage, plate, and neuromonitoring plan is intended?",
        ),
        retrieval_templates=_freeze_mapping({
            "anatomy": "ACDF anterior cervical exposure anatomy recurrent laryngeal nerve RLN esophagus vertebral artery uncinate foramen",
            "technique": "anterior cervical discectomy fusion technique localization decompression uncinate foraminotomy cage plate",
            "complications": "ACDF complications dysphagia recurrent laryngeal nerve esophageal injury vertebral artery pseudarthrosis",
            "outcomes": "ACDF cervical radiculopathy outcomes fusion dysphagia posterior foraminotomy alternative",
        }),
        section_headings=_COMMON_SECTION_HEADINGS,
        eval_required_concepts=(
            "anterior cervical exposure",
            "level localization",
            "decompression",
            "foraminal decompression and uncinate work",
            "graft, cage, and plate construct",
            "RLN, esophagus, vertebral artery, and dysphagia risks",
            "posterior foraminotomy alternative",
        ),
    ),
    "tumor_convexity_meningioma": ProcedureFamily(
        id="tumor_convexity_meningioma",
        display_name="Convexity meningioma resection",
        broad_profile="supratentorial_tumor",
        procedure_aliases=(
            "convexity meningioma resection",
            "meningioma craniotomy",
            "frontal convexity meningioma resection",
            "supratentorial meningioma resection",
        ),
        pathology_aliases=(
            "convexity meningioma",
            "frontal meningioma",
            "parasagittal meningioma",
            "dural based mass",
        ),
        approach_aliases=(
            "frontal craniotomy",
            "convexity craniotomy",
            "parasagittal craniotomy",
        ),
        required_fields=(
            "tumor_location",
            "sinus_or_venous_relationship",
            "edema_and_mass_effect",
            "extent_of_resection_goal",
            "adjuvant_option",
        ),
        missing_fact_prompts=(
            "How close is the tumor to the superior sagittal sinus or cortical draining veins?",
            "What is the planned craniotomy and dural opening?",
            "Is gross-total resection or planned subtotal resection safest?",
            "Are observation or stereotactic radiosurgery reasonable alternatives?",
        ),
        retrieval_templates=_freeze_mapping({
            "anatomy": "convexity meningioma superior sagittal sinus bridging veins venous anatomy surgical anatomy",
            "technique": "convexity meningioma resection craniotomy dural opening devascularization debulking extracapsular dissection Simpson grade",
            "complications": "convexity meningioma surgery complications venous infarct superior sagittal sinus bridging vein edema seizure",
            "outcomes": "convexity meningioma resection outcomes Simpson grade observation stereotactic radiosurgery alternative",
        }),
        section_headings=_COMMON_SECTION_HEADINGS,
        eval_required_concepts=(
            "superior sagittal sinus (SSS)",
            "bridging veins",
            "Simpson grade",
            "venous infarct risk",
            "craniotomy",
            "dural opening",
            "devascularization",
            "debulking and extracapsular dissection",
            "observation or SRS alternative",
        ),
    ),
    "posterior_fossa_chiari": ProcedureFamily(
        id="posterior_fossa_chiari",
        display_name="Chiari I posterior fossa decompression",
        broad_profile="posterior_fossa",
        procedure_aliases=(
            "chiari decompression",
            "chiari 1 decompression",
            "posterior fossa decompression",
            "suboccipital craniectomy and c1 laminectomy",
            "suboccipital decompression",
        ),
        pathology_aliases=(
            "chiari i malformation",
            "chiari malformation",
            "syringomyelia",
            "syrinx",
            "tonsillar ectopia",
        ),
        approach_aliases=(
            "midline suboccipital approach",
            "suboccipital craniectomy",
            "c1 laminectomy",
            "duraplasty",
        ),
        required_fields=(
            "symptoms",
            "tonsillar_descent",
            "syrinx_status",
            "bony_decompression_plan",
            "dural_or_arachnoid_plan",
        ),
        missing_fact_prompts=(
            "What symptoms and imaging findings support Chiari decompression?",
            "Is a syrinx present and what levels does it span?",
            "Will the plan include duraplasty, arachnoid opening, or tonsillar reduction?",
            "Are there craniocervical instability or basilar invagination concerns?",
        ),
        retrieval_templates=_freeze_mapping({
            "anatomy": "Chiari I foramen magnum tonsils obex PICA C1 posterior fossa anatomy",
            "technique": "Chiari decompression suboccipital craniectomy C1 laminectomy duraplasty arachnoid tonsillar reduction technique",
            "complications": "Chiari decompression complications CSF leak pseudomeningocele aseptic meningitis instability",
            "outcomes": "Chiari I malformation syringomyelia posterior fossa decompression outcomes duraplasty bone only",
        }),
        section_headings=_COMMON_SECTION_HEADINGS,
        eval_required_concepts=(
            "foramen magnum",
            "cerebellar tonsils",
            "obex",
            "PICA",
            "C1 posterior arch",
            "duraplasty",
            "arachnoid management",
            "tonsillar reduction",
            "syrinx response",
            "CSF leak",
            "pseudomeningocele",
            "aseptic meningitis",
            "craniocervical instability",
        ),
    ),
    "endovascular_thrombectomy": ProcedureFamily(
        id="endovascular_thrombectomy",
        display_name="Mechanical thrombectomy for large-vessel ischemic stroke",
        broad_profile="vascular",
        procedure_aliases=(
            "mechanical thrombectomy",
            "endovascular thrombectomy",
            "stroke thrombectomy",
            "m1 thrombectomy",
        ),
        pathology_aliases=(
            "acute ischemic stroke",
            "large vessel occlusion",
            "m1 occlusion",
            "middle cerebral artery occlusion",
            "mca occlusion",
        ),
        approach_aliases=(
            "transfemoral access",
            "radial access",
            "balloon guide catheter",
            "distal access catheter",
            "aspiration thrombectomy",
            "stent retriever thrombectomy",
        ),
        required_fields=(
            "last_known_well",
            "nihss",
            "occlusion_location",
            "imaging_selection",
            "access_plan",
        ),
        missing_fact_prompts=(
            "What is the last-known-well time and thrombolytic status?",
            "What is the NIHSS and baseline functional status?",
            "Where is the occlusion and what are ASPECTS/perfusion findings?",
            "What access, balloon-guide, aspiration, or stent-retriever strategy is planned?",
        ),
        retrieval_templates=_freeze_mapping({
            "anatomy": "M1 M2 middle cerebral artery thrombectomy anatomy lenticulostriate perforators access",
            "technique": "mechanical thrombectomy technique balloon guide distal access aspiration stent retriever first pass",
            "complications": "mechanical thrombectomy complications sICH distal emboli perforation vasospasm subarachnoid hemorrhage",
            "outcomes": "acute ischemic stroke thrombectomy outcomes TICI mTICI first pass reperfusion functional independence",
        }),
        section_headings=_COMMON_SECTION_HEADINGS,
        eval_required_concepts=(
            "M1 and M2 anatomy",
            "lenticulostriate perforator risk",
            "arterial access",
            "balloon guide catheter",
            "distal access catheter",
            "aspiration",
            "stent retriever",
            "TICI and mTICI reperfusion grading",
            "first pass effect",
            "sICH",
            "distal emboli",
            "perforation",
            "vasospasm",
        ),
    ),
})


def iter_procedure_families() -> tuple[ProcedureFamily, ...]:
    """Return all known V1 procedure families in canonical order."""
    return tuple(PROCEDURE_FAMILIES.values())


def get_procedure_family(family_id: str) -> ProcedureFamily | None:
    """Look up a procedure family by its canonical family ID."""
    return PROCEDURE_FAMILIES.get(family_id)


def match_procedure_family(text: str) -> ProcedureFamily | None:
    """Match free text to a procedure family using family IDs and aliases."""
    normalized = text.casefold()
    if not normalized.strip():
        return None

    for family in iter_procedure_families():
        if family.id.casefold() in normalized:
            return family
        aliases = (
            family.procedure_aliases
            + family.pathology_aliases
            + family.approach_aliases
        )
        if any(alias.casefold() in normalized for alias in aliases):
            return family
    return None
