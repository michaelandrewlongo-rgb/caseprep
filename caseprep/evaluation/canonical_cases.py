"""Canonical evaluation cases for deterministic CasePrep output checks."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CanonicalCase:
    """A fixed input case and the deterministic expectations for its dossier."""

    id: str
    input_text: str
    expected_family: str | None
    required_concepts: tuple[str, ...]
    degraded: bool = False


ACDF_C5_6 = CanonicalCase(
    id="spine_acdf_c5_6_right_c6_radiculopathy",
    input_text=(
        "C5-6 anterior cervical discectomy and fusion for right C6 radiculopathy "
        "from foraminal disc osteophyte complex"
    ),
    expected_family="spine_acdf",
    required_concepts=(
        "anterior cervical exposure",
        "localization",
        "discectomy/decompression",
        "foraminal/uncinate",
        "graft/cage/plate",
        "recurrent laryngeal nerve",
        "esophagus",
        "vertebral artery",
        "dysphagia",
        "posterior cervical foraminotomy",
    ),
)

CONVEXITY_MENINGIOMA = CanonicalCase(
    id="right_frontal_convexity_meningioma_near_sss",
    input_text="right frontal convexity meningioma resection near the superior sagittal sinus",
    expected_family="tumor_convexity_meningioma",
    required_concepts=(
        "edema",
        "sinus invasion/abutment",
        "arterial supply",
        "cortical/bridging veins",
        "craniotomy planning",
        "dural opening",
        "circumferential devascularization",
        "debulking vs extracapsular dissection",
        "venous preservation",
        "Simpson grade",
        "venous infarct",
        "seizures",
        "hemorrhage",
        "neurologic deficit",
        "observation/SRS",
    ),
)

CHIARI_DECOMPRESSION = CanonicalCase(
    id="suboccipital_c1_chiari_syringomyelia",
    input_text="suboccipital craniectomy and C1 laminectomy for Chiari I malformation with syringomyelia",
    expected_family="posterior_fossa_chiari",
    required_concepts=(
        "foramen magnum",
        "tonsils",
        "obex",
        "PICA",
        "brainstem",
        "upper cervical cord",
        "decompression extent",
        "C1 laminectomy",
        "bone-only vs duraplasty",
        "arachnoid opening",
        "selective tonsillar reduction",
        "syrinx",
        "CSF leak",
        "pseudomeningocele",
        "aseptic meningitis",
        "craniocervical instability",
    ),
)

THROMBECTOMY_M1 = CanonicalCase(
    id="right_m1_stroke_thrombectomy",
    input_text="mechanical thrombectomy for acute ischemic stroke due to right M1 MCA occlusion",
    expected_family="endovascular_thrombectomy",
    required_concepts=(
        "M1/M2 anatomy",
        "lenticulostriate/perforator",
        "femoral/radial access",
        "guide catheter/balloon guide/distal access catheter",
        "aspiration vs stent retriever vs combined technique",
        "first-pass effect",
        "TICI/mTICI",
        "time window/imaging selection",
        "vessel perforation",
        "dissection",
        "distal emboli",
        "symptomatic ICH",
        "vasospasm",
        "access complications",
        "IV thrombolysis",
        "medical management",
        "rescue angioplasty/stenting",
    ),
)

DEGRADED_VESTIBULAR_SCHWANNOMA = CanonicalCase(
    id="degraded_vestibular_schwannoma",
    input_text="vestibular schwannoma",
    expected_family=None,
    required_concepts=(),
    degraded=True,
)

DEGRADED_MCA_ANEURYSM = CanonicalCase(
    id="degraded_mca_aneurysm",
    input_text="MCA aneurysm",
    expected_family=None,
    required_concepts=(),
    degraded=True,
)

DEGRADED_CERVICAL_RADICULOPATHY = CanonicalCase(
    id="degraded_cervical_radiculopathy",
    input_text="cervical radiculopathy",
    expected_family=None,
    required_concepts=(),
    degraded=True,
)

DEGRADED_CHIARI = CanonicalCase(
    id="degraded_chiari",
    input_text="Chiari",
    expected_family=None,
    required_concepts=(),
    degraded=True,
)

DEGRADED_STROKE_THROMBECTOMY = CanonicalCase(
    id="degraded_stroke_thrombectomy",
    input_text="stroke thrombectomy",
    expected_family=None,
    required_concepts=(),
    degraded=True,
)

FULL_CANONICAL_CASES: tuple[CanonicalCase, ...] = (
    ACDF_C5_6,
    CONVEXITY_MENINGIOMA,
    CHIARI_DECOMPRESSION,
    THROMBECTOMY_M1,
)

DEGRADED_CASES: tuple[CanonicalCase, ...] = (
    DEGRADED_VESTIBULAR_SCHWANNOMA,
    DEGRADED_MCA_ANEURYSM,
    DEGRADED_CERVICAL_RADICULOPATHY,
    DEGRADED_CHIARI,
    DEGRADED_STROKE_THROMBECTOMY,
)


def full_canonical_cases() -> tuple[CanonicalCase, ...]:
    """Return supported full canonical cases."""

    return FULL_CANONICAL_CASES


def degraded_cases() -> tuple[CanonicalCase, ...]:
    """Return deliberately underspecified parser/degradation cases."""

    return DEGRADED_CASES


def all_canonical_cases() -> tuple[CanonicalCase, ...]:
    """Return all canonical cases, full and degraded."""

    return FULL_CANONICAL_CASES + DEGRADED_CASES
