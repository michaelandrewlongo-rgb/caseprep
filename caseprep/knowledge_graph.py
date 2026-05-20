"""Small neuroanatomy and outcomes gazetteers for query expansion."""

from __future__ import annotations

import re


ANATOMY_GAZETTEER: dict[str, tuple[str, ...]] = {
    "middle cerebral artery": ("MCA", "middle cerebral artery", "M1", "M2"),
    "internal carotid artery": (
        "ICA",
        "internal carotid artery",
        "carotid siphon",
        "cavernous ICA",
        "supraclinoid ICA",
    ),
    "anterior cerebral artery": ("ACA", "anterior cerebral artery", "A1", "A2"),
    "posterior cerebral artery": ("PCA", "posterior cerebral artery", "P1", "P2"),
    "vertebral artery": ("VA", "vertebral artery", "V4"),
    "basilar artery": ("BA", "basilar artery", "basilar trunk"),
    "anterior communicating artery": (
        "ACom",
        "AComm",
        "ACoA",
        "anterior communicating artery",
    ),
    "posterior communicating artery": (
        "PCom",
        "PComm",
        "PCoA",
        "posterior communicating artery",
    ),
    "superior cerebellar artery": ("SCA", "superior cerebellar artery"),
    "anterior inferior cerebellar artery": (
        "AICA",
        "anterior inferior cerebellar artery",
    ),
    "posterior inferior cerebellar artery": (
        "PICA",
        "posterior inferior cerebellar artery",
    ),
    "superior sagittal sinus": ("SSS", "superior sagittal sinus"),
    "transverse sinus": ("transverse sinus", "TS"),
    "sigmoid sinus": ("sigmoid sinus",),
    "cavernous sinus": ("cavernous sinus",),
    "sella": ("sella", "sellar", "pituitary fossa"),
    "cerebellopontine angle": ("CPA", "cerebellopontine angle"),
    "petrous apex": ("petrous apex", "petroclival"),
    "clivus": ("clivus", "clival"),
    "foramen magnum": ("foramen magnum",),
    "optic apparatus": ("optic nerve", "optic chiasm", "optic apparatus"),
    "trigeminal nerve": ("CN V", "trigeminal nerve", "fifth cranial nerve"),
    "facial nerve": ("CN VII", "facial nerve", "seventh cranial nerve"),
    "vestibulocochlear nerve": (
        "CN VIII",
        "vestibulocochlear nerve",
        "eighth cranial nerve",
    ),
    "vagus nerve": ("CN X", "vagus nerve", "tenth cranial nerve"),
    "brainstem": ("brainstem", "midbrain", "pons", "medulla"),
    "cerebellum": ("cerebellum", "cerebellar"),
    "thalamus": ("thalamus", "thalamic"),
    "corticospinal tract": ("corticospinal tract", "pyramidal tract"),
    "lateral ventricle": ("lateral ventricle", "frontal horn", "temporal horn"),
    "third ventricle": ("third ventricle",),
    "fourth ventricle": ("fourth ventricle",),
    "foramen of Monro": ("foramen of Monro", "Monro"),
    "Meckel cave": ("Meckel cave", "Meckel's cave"),
    "cervical spine": ("cervical spine", "C-spine", "subaxial cervical"),
    "thoracic spine": ("thoracic spine", "T-spine", "thoracic"),
    "lumbar spine": ("lumbar spine", "L-spine", "lumbar"),
    "spinal cord": ("spinal cord", "cord", "myelopathy"),
    "cauda equina": ("cauda equina",),
    # Skull base (expanded)
    "vestibular schwannoma": ("acoustic neuroma", "vestibular schwannoma", "VS", "schwannoma"),
    "internal acoustic meatus": ("IAC", "internal auditory canal", "internal acoustic meatus"),
    "petrous bone": ("petrous", "petrous bone", "petrous temporal"),
    "jugular foramen": ("jugular foramen", "jugular bulb"),
    "hypoglossal canal": ("hypoglossal canal",),
    "foramen ovale": ("foramen ovale",),
    "foramen rotundum": ("foramen rotundum",),
    "optic canal": ("optic canal", "optic foramen"),
    "sphenoid sinus": ("sphenoid", "sphenoid sinus"),
    "ethmoid sinus": ("ethmoid", "ethmoid sinus", "ethmoid air cells"),
    "pituitary gland": ("pituitary", "pituitary gland", "hypophysis", "sella turcica"),
    # Spine (expanded)
    "intervertebral disc": ("disc", "disk", "intervertebral disc", "nucleus pulposus"),
    "spinal canal": ("spinal canal", "thecal sac"),
    "nerve root": ("nerve root", "nerve roots", "rootlets"),
    "facet joint": ("facet", "facet joint", "zygapophyseal"),
    "pedicle of vertebra": ("pedicle", "pars"),
    "odontoid": ("odontoid", "dens"),
    # Tumor (supratentorial)
    "glioblastoma": ("GBM", "glioblastoma", "glioblastoma multiforme"),
    "low-grade glioma": ("LGG", "low-grade glioma", "astrocytoma", "oligodendroglioma"),
    "brain metastasis": ("brain metastases", "intracranial metastasis", "cerebral metastasis"),
    # Functional
    "subthalamic nucleus": ("STN", "subthalamic nucleus", "subthalamic"),
    "globus pallidus interna": ("GPi", "globus pallidus"),
    "ventral intermediate nucleus": ("VIM", "Vim", "ventral intermediate"),
    "motor cortex": ("motor strip", "precentral gyrus"),
    "supplementary motor area": ("SMA", "supplementary motor area"),
    "Parkinson disease": ("Parkinson", "Parkinson disease", "Parkinson's"),
}

OUTCOME_FACET_GAZETTEER: dict[str, tuple[str, ...]] = {
    "modified Rankin Scale": ("mRS", "modified Rankin Scale"),
    "NIH Stroke Scale": ("NIHSS", "NIH Stroke Scale"),
    "mortality": ("mortality", "death"),
    "morbidity": ("morbidity",),
    "complications": ("complication", "complications", "adverse event"),
    "reperfusion": ("reperfusion", "TICI", "mTICI"),
    "recurrence": ("recurrence", "recurrent"),
    "survival": ("survival", "overall survival"),
    "progression-free survival": ("PFS", "progression-free survival"),
    "gross total resection": ("GTR", "gross total resection"),
    "extent of resection": ("EOR", "extent of resection"),
    "seizure freedom": ("Engel", "seizure freedom"),
    "obliteration": ("obliteration", "complete occlusion"),
    "quality of life": ("QOL", "quality of life"),
}


def expand_concepts(topic: str) -> dict[str, list[str]]:
    """Return matching anatomy and outcome aliases grouped by category."""
    concepts: dict[str, list[str]] = {}
    anatomy_aliases = _matched_aliases(topic, ANATOMY_GAZETTEER)
    if anatomy_aliases:
        concepts["anatomy"] = anatomy_aliases

    outcome_aliases = _matched_aliases(topic, OUTCOME_FACET_GAZETTEER)
    if outcome_aliases:
        concepts["outcomes"] = outcome_aliases

    return concepts


def build_enriched_query(topic: str, base_terms: list[str]) -> str:
    """Build a PubMed query with anatomy alias expansion when available."""
    base_query = " ".join(part for part in [topic.strip(), *base_terms] if part)
    concepts = expand_concepts(topic)
    anatomy_aliases = concepts.get("anatomy", [])
    if not anatomy_aliases:
        return base_query
    return f"{base_query} ({' OR '.join(anatomy_aliases)})"


def _matched_aliases(topic: str, gazetteer: dict[str, tuple[str, ...]]) -> list[str]:
    aliases: list[str] = []
    seen: set[str] = set()
    for canonical, concept_aliases in gazetteer.items():
        terms = (canonical, *concept_aliases)
        if not any(_has_alias(topic, term) for term in terms):
            continue
        for alias in concept_aliases:
            key = alias.lower()
            if key not in seen:
                aliases.append(alias)
                seen.add(key)
    return aliases


def _has_alias(text: str, alias: str) -> bool:
    escaped = re.escape(alias.lower())
    pattern = escaped.replace(r"\ ", r"[\s-]+").replace(r"\-", r"[\s-]+")
    return bool(re.search(rf"(?<!\w){pattern}(?!\w)", text.lower()))
