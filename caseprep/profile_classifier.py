"""Pure deterministic profile classification for CasePrep topics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


ProfileName = Literal[
    "skull_base",
    "supratentorial_tumor",
    "vascular",
    "spine",
    "posterior_fossa",
    "functional",
    "pediatric",
]


@dataclass(frozen=True)
class ProfileClassification:
    """Result of deterministic topic-to-profile classification."""

    profile: ProfileName
    confidence: float
    matched_term: str | None
    source: Literal["hint", "substring", "word", "fallback", "case_parser"]


BASE_ANATOMY_KEYWORDS = [
    "anatomy", "anatomic", "structure", "nerve", "artery", "vein",
    "nucleus", "tract", "cortex", "lobe", "foramen", "fissure",
    "sulcus", "gyrus", "ventricle", "cistern",
]
BASE_APPROACH_KEYWORDS = [
    "approach", "technique", "positioning", "craniotomy", "incision",
    "resection", "dissection", "exposure", "retraction",
    "microsurgical", "endoscopic", "minimally invasive",
    "monitoring", "neuromonitoring", "intraoperative",
    "neuronavigation", "bone flap", "dura", "closure", "hemostasis",
]
BASE_COMPLICATION_KEYWORDS = [
    "complication", "risk", "mortality", "morbidity", "deficit",
    "infection", "meningitis", "hematoma", "hemorrhage", "ischemia",
    "infarction", "edema", "seizure", "hydrocephalus",
    "thromboembolism", "rate", "%", "percent", "incidence", "n=",
]

DOMAIN_PROFILE_KEYWORDS: dict[ProfileName, dict[str, list[str]]] = {
    "skull_base": {
        "anatomy": [
            "cranial nerve", "cn vii", "cn viii", "cn v", "cn ix", "cn x",
            "brainstem", "cerebell", "temporal bone", "sigmoid", "petrous",
            "cavernous", "sella", "clivus", "jugular", "meckel", "cpa",
            "cerebellopontine", "internal acoustic", "geniculate",
            "sphenoid", "petroclival", "tentorium",
        ],
        "approach": [
            "retrosigmoid", "translabyrinthine", "middle fossa",
            "transpetrosal", "presigmoid", "drilling",
            "ssep", "mep", "emg", "baer", "facial nerve monitor",
            "keyhole", "endonasal", "transsphenoidal",
        ],
        "complications": [
            "cerebrospinal fluid leak", "csf leak", "facial nerve",
            "hearing loss", "anosmia", "diplopia", "dysphagia",
            "aspiration", "hoarseness", "dvt", "pe",
        ],
    },
    "supratentorial_tumor": {
        "anatomy": [
            "eloquent", "frontal", "temporal", "parietal", "occipital",
            "broca", "wernicke", "supplementary motor", "sma", "insula",
            "corpus callosum", "basal ganglia", "thalamus",
            "white matter", "corticospinal", "arcuate", "precentral",
            "postcentral", "language", "motor cortex", "sensory",
            "visual cortex", "optic radiation", "internal capsule",
        ],
        "approach": [
            "awake craniotomy", "asleep", "frameless", "stereotactic",
            "neuronavigation", "intraoperative mri", "fluorescence",
            "5-ala", "aminolevulinic", "mapping", "cortical mapping",
            "subcortical", "des", "direct electrical stimulation",
            "keyhole", "tubular", "ssep", "mep", "emg",
        ],
        "complications": [
            "aphasia", "dysphasia", "hemiparesis", "visual field",
            "neglect", "cognitive", "personality", "mood",
            "wound", "dehiscence", "pseudomeningocele",
        ],
    },
    "vascular": {
        "anatomy": [
            "aca", "mca", "ica", "pcom", "anterior choroidal",
            "vertebral", "basilar", "pca", "pica", "aica", "sca",
            "acom", "perforators", "dural sinuses", "aneurysm",
            "avm", "arteriovenous malformation", "davf", "ccf",
            "intracranial stenosis", "icad", "vasospasm",
            "cavernous malformation", "hemorrhage", "sah", "ich",
            "subarachnoid", "flow-related", "ruptured vs unruptured",
        ],
        "approach": [
            "primary coiling", "coiling", "balloon-assisted coiling",
            "stent-assisted coiling", "flow diversion",
            "mechanical thrombectomy", "stent retriever alone",
            "avm embolization", "davf embolization", "transarterial",
            "transvenous", "carotid revascularization", "angioplasty",
            "transfemoral", "transradial", "venous sinus stenting",
            "diagnostic angiography", "clipping", "bypass", "ec-ic",
            "temporary clip", "icg", "microdoppler",
        ],
        "complications": [
            "sich", "parenchymal hematoma", "sah", "hemorrhage",
            "rebleed", "territorial infarct", "perforator infarct",
            "distal emboli", "vasospasm", "delayed cerebral ischemia",
            "dci", "thrombosis", "in-stent stenosis", "pseudoaneurysm",
            "dissection", "contrast-induced nephropathy", "infection",
            "cranial neuropathy", "seizure", "mortality",
            "aneurysm occlusion", "recanalization", "retreatment rate",
            "stroke", "infarct", "nimodipine",
        ],
    },
    "spine": {
        "anatomy": [
            "cervical", "thoracic", "lumbar", "sacral", "vertebra",
            "disc", "pedicle", "lamina", "facet", "foramen",
            "spinal cord", "nerve root", "cauda equina", "conus",
            "thecal sac", "ligamentum", "odontoid", "atlantoaxial",
            "spinous", "transverse process", "pars",
        ],
        "approach": [
            "laminectomy", "laminoplasty", "discectomy", "microdiscectomy",
            "fusion", "instrumentation", "pedicle screw", "cage",
            "corpectomy", "foraminotomy", "tlif", "plif", "alif",
            "xlif", "oblique", "lateral", "minimally invasive spine",
            "tubular", "endoscopic spine", "neuronavigation spine",
            "o-arm", "navigation", "robotic",
        ],
        "complications": [
            "dural tear", "nerve root injury", "pseudarthrosis",
            "adjacent segment", "instrumentation failure", "screw",
            "misplacement", "dysphagia", "hoarseness", "c5 palsy",
            "kyphosis", "sagittal", "flat back", "proximal junctional",
        ],
    },
    "posterior_fossa": {
        "anatomy": [
            "posterior fossa", "foramen magnum", "craniocervical junction",
            "cerebellar tonsils", "cerebell", "vermis", "brainstem",
            "medulla", "fourth ventricle", "cisterna magna", "obex",
            "c1", "atlas", "occipital bone", "pica", "vertebral artery",
            "syrinx", "syringomyelia",
        ],
        "approach": [
            "suboccipital craniectomy", "posterior fossa decompression",
            "foramen magnum decompression", "c1 laminectomy", "duraplasty",
            "tonsillar reduction", "arachnoid dissection", "prone positioning",
            "mayfield", "intraoperative ultrasound",
        ],
        "complications": [
            "pseudomeningocele", "csf leak", "cerebrospinal fluid leak",
            "aseptic meningitis", "chemical meningitis", "hydrocephalus",
            "vertebral artery injury", "pica injury", "brainstem injury",
            "cerebellar slump", "wound infection", "reoperation",
        ],
    },
    "functional": {
        "anatomy": [
            "basal ganglia", "thalamus", "subthalamic", "stn", "gpi",
            "vop", "vim", "striatum", "globus pallidus", "substantia nigra",
            "motor cortex", "premotor", "sma", "cingulate", "insula",
            "hippocampus", "amygdala", "anterior nucleus", "centromedian",
        ],
        "approach": [
            "deep brain stimulation", "dbs", "stereotactic", "frame",
            "frameless", "microelectrode", "mer", "macroelectrode",
            "impedance", "electrode", "lead", "pulse generator",
            "programming", "theta", "beta", "gamma",
            "radiofrequency", "rft", "rhizotomy", "thermocoagulation",
            "laser ablation", "litt", "focused ultrasound", "mrgfus",
        ],
        "complications": [
            "hemorrhage dbs", "infection dbs", "lead migration",
            "lead fracture", "erosion", "ipg", "stimulation side effects",
            "dysarthria", "gait", "cognitive dbs", "mood dbs",
            "suicide", "impulse control", "status dystonicus",
        ],
    },
    "pediatric": {
        "anatomy": [
            "fontanelle", "suture", "craniosynostosis", "hydrocephalus",
            "ventricle", "choroid plexus", "myelination", "germinal matrix",
            "posterior fossa", "fourth ventricle", "brainstem",
            "cerebell", "vermis", "tectal", "pineal",
        ],
        "approach": [
            "endoscopic third ventriculostomy", "etv", "shunt",
            "vps", "vetriculoperitoneal", "programmable",
            "posterior fossa craniotomy", "telovelar",
            "endoscopic biopsy", "navigated biopsy",
            "intraoperative ultrasound", "vagal nerve stimulator", "vns",
            "corpus callosotomy", "hemispherectomy", "lobar",
            "grid", "depth electrode", "seeg", "ecog",
        ],
        "complications": [
            "shunt infection", "shunt malfunction", "overdrainage",
            "slit ventricle", "cranial defect", "infection pediatric",
            "mutism", "cerebellar mutism", "posterior fossa syndrome",
            "endocrine", "growth", "developmental", "cognitive pediatric",
            "seizure pediatric", "hydrocephalus acquired",
        ],
    },
}

TOPIC_TO_PROFILE: dict[str, ProfileName] = {
    "vestibular schwannoma": "skull_base",
    "acoustic neuroma": "skull_base",
    "meningioma": "skull_base",
    "chordoma": "skull_base",
    "chondrosarcoma": "skull_base",
    "craniopharyngioma": "skull_base",
    "pituitary": "skull_base",
    "epidermoid": "skull_base",
    "petroclival": "skull_base",
    "cerebellopontine": "skull_base",
    "cpa": "skull_base",
    "jugular": "skull_base",
    "glomus": "skull_base",
    "glioblastoma": "supratentorial_tumor",
    "gbm": "supratentorial_tumor",
    "glioma": "supratentorial_tumor",
    "astrocytoma": "supratentorial_tumor",
    "oligodendroglioma": "supratentorial_tumor",
    "oligoastrocytoma": "supratentorial_tumor",
    "metastasis": "supratentorial_tumor",
    "brain metastasis": "supratentorial_tumor",
    "lymphoma": "supratentorial_tumor",
    "aneurysm": "vascular",
    "clipping": "vascular",
    "coiling": "vascular",
    "anterior communicating": "vascular",
    "posterior communicating": "vascular",
    "anterior choroidal": "vascular",
    "basilar": "vascular",
    "avm": "vascular",
    "arteriovenous malformation": "vascular",
    "cavernous malformation": "vascular",
    "cavernoma": "vascular",
    "moyamoya": "vascular",
    "bypass": "vascular",
    "ec-ic": "vascular",
    "subarachnoid": "vascular",
    "sah": "vascular",
    "intracerebral hemorrhage": "vascular",
    "ich": "vascular",
    "hemorrhagic stroke": "vascular",
    "embolization": "vascular",
    "flow diversion": "vascular",
    "stent retriever": "vascular",
    "thrombectomy": "vascular",
    "davf": "vascular",
    "dural arteriovenous fistula": "vascular",
    "ccf": "vascular",
    "carotid cavernous fistula": "vascular",
    "carotid stenosis": "vascular",
    "carotid stenting": "vascular",
    "carotid endarterectomy": "vascular",
    "vasospasm": "vascular",
    "mechanical thrombectomy": "vascular",
    "acute ischemic stroke": "vascular",
    "spine": "spine",
    "spinal": "spine",
    "discectomy": "spine",
    "laminectomy": "spine",
    "fusion": "spine",
    "cervical": "spine",
    "lumbar": "spine",
    "thoracic": "spine",
    "scoliosis": "spine",
    "spondylolisthesis": "spine",
    "stenosis": "spine",
    "myelopathy": "spine",
    "radiculopathy": "spine",
    "cord": "spine",
    "chiari malformation": "posterior_fossa",
    "chiari i malformation": "posterior_fossa",
    "chiari decompression": "posterior_fossa",
    "posterior fossa decompression": "posterior_fossa",
    "foramen magnum decompression": "posterior_fossa",
    "suboccipital craniectomy": "posterior_fossa",
    "syringomyelia": "posterior_fossa",
    "syrinx": "posterior_fossa",
    "deep brain": "functional",
    "dbs": "functional",
    "parkinson": "functional",
    "tremor": "functional",
    "dystonia": "functional",
    "epilepsy surgery": "functional",
    "seizure focus": "functional",
    "temporal lobectomy": "functional",
    "laser ablation": "functional",
    "litt": "functional",
    "focused ultrasound": "functional",
    "mrgfus": "functional",
    "pediatric": "pediatric",
    "paediatric": "pediatric",
    "child": "pediatric",
    "hydrocephalus": "pediatric",
    "shunt": "pediatric",
    "craniosynostosis": "pediatric",
    "myelomeningocele": "pediatric",
    "tethered cord": "pediatric",
    "medulloblastoma": "pediatric",
    "ependymoma": "pediatric",
}

VALID_PROFILES = frozenset(DOMAIN_PROFILE_KEYWORDS)


def classify_profile(
    topic: str,
    *,
    profile_hint: str | None = None,
) -> ProfileClassification:
    """Classify a topic into a deterministic neurosurgical profile."""
    hint = (profile_hint or "").strip().lower()
    if hint in VALID_PROFILES:
        return ProfileClassification(
            profile=hint,  # type: ignore[arg-type]
            confidence=1.0,
            matched_term=hint,
            source="hint",
        )

    topic_lower = topic.lower()
    best_term: str | None = None
    best_profile: ProfileName | None = None
    best_len = 0
    for term, profile in TOPIC_TO_PROFILE.items():
        if term in topic_lower and len(term) > best_len:
            best_term = term
            best_profile = profile
            best_len = len(term)

    if best_profile is not None:
        return ProfileClassification(
            profile=best_profile,
            confidence=min(1.0, best_len / max(len(topic_lower), 10)),
            matched_term=best_term,
            source="substring",
        )

    topic_words = set(topic_lower.replace("-", " ").replace("/", " ").split())
    word_hits: dict[ProfileName, int] = {}
    matched_terms: dict[ProfileName, str] = {}
    for term, profile in TOPIC_TO_PROFILE.items():
        key_words = set(term.split())
        overlap = topic_words & key_words
        if overlap:
            word_hits[profile] = word_hits.get(profile, 0) + len(overlap)
            matched_terms.setdefault(profile, term)

    if word_hits:
        best_word_profile = max(word_hits, key=lambda profile: word_hits[profile])
        return ProfileClassification(
            profile=best_word_profile,
            confidence=min(0.5, word_hits[best_word_profile] / max(len(topic_words), 5)),
            matched_term=matched_terms[best_word_profile],
            source="word",
        )

    return ProfileClassification(
        profile="skull_base",
        confidence=0.0,
        matched_term=None,
        source="fallback",
    )


def build_keywords(profile: str) -> dict[str, list[str]]:
    """Merge base keywords with profile-specific keywords."""
    profile_keywords = DOMAIN_PROFILE_KEYWORDS.get(profile, {})
    return {
        "anatomy": BASE_ANATOMY_KEYWORDS + profile_keywords.get("anatomy", []),
        "approach": BASE_APPROACH_KEYWORDS + profile_keywords.get("approach", []),
        "complications": (
            BASE_COMPLICATION_KEYWORDS + profile_keywords.get("complications", [])
        ),
    }
