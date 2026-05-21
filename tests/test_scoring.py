"""Tests for surgical usefulness scoring heuristics."""

from __future__ import annotations

from caseprep.case_parser import parse_case_input, select_procedure_family
from caseprep.core import EvidenceRecord
from caseprep.scoring import neurosurg_relevance_score, surgical_usefulness_score


def _acdf_case():
    case = parse_case_input(
        "C5-6 anterior cervical discectomy and fusion for right C6 "
        "radiculopathy from foraminal disc osteophyte complex"
    )
    return case, select_procedure_family(case)


def test_exact_procedure_title_outranks_generic_disease_title():
    case, family = _acdf_case()
    exact = EvidenceRecord(
        id="exact",
        source="pubmed",
        title="Anterior cervical discectomy and fusion: operative technique and outcomes",
        text="Technical note describing decompression, cage placement, plate fixation, and fusion.",
    )
    generic = EvidenceRecord(
        id="generic",
        source="pubmed",
        title="Cervical radiculopathy outcomes: a review",
        text="Background and nonoperative management options for cervical radiculopathy.",
    )

    exact_score, exact_reasons = surgical_usefulness_score(
        exact,
        case,
        family,
        "Surgical Technique",
    )
    generic_score, generic_reasons = surgical_usefulness_score(
        generic,
        case,
        family,
        "Surgical Technique",
    )

    assert exact_score > generic_score
    assert any("exact procedure" in reason for reason in exact_reasons)
    assert any("pathology" in reason for reason in generic_reasons)


def test_off_domain_drug_basic_science_content_gets_penalty():
    case, family = _acdf_case()
    record = EvidenceRecord(
        id="drug",
        source="pubmed",
        title="Drug pharmacokinetic changes in breast cancer cell cultures",
        text="Basic-science assay of placebo-controlled medication exposure in vitro.",
    )

    score, reasons = surgical_usefulness_score(record, case, family, "Outcomes / Evidence")

    assert score < 0
    assert any("off-domain" in reason for reason in reasons)
    assert any("non-neurosurgical" in reason for reason in reasons)


def test_complications_axis_recognizes_complication_terms():
    case, family = _acdf_case()
    record = EvidenceRecord(
        id="complications",
        source="pubmed",
        title="ACDF complications: dysphagia and recurrent laryngeal nerve injury",
        text="Operative series reporting postoperative dysphagia, hoarseness, and pseudarthrosis rescue strategies.",
    )

    score, reasons = surgical_usefulness_score(record, case, family, "Complications")

    assert score >= 60
    assert any("complication/outcome" in reason for reason in reasons)
    assert any("exact procedure" in reason for reason in reasons)


def test_uterine_fibroid_embolization_is_penalized_for_thrombectomy_case():
    case = parse_case_input("mechanical thrombectomy for acute ischemic stroke M1 occlusion")
    family = select_procedure_family(case)
    off_domain = EvidenceRecord(
        id="fibroid",
        source="pubmed",
        title="Uterine fibroid embolization outcomes",
        text="A gynecologic cohort reporting safety and complications after embolization.",
    )
    on_domain = EvidenceRecord(
        id="thrombectomy",
        source="pubmed",
        title="Mechanical thrombectomy outcomes for acute ischemic stroke",
        text="Endovascular stroke thrombectomy series reporting reperfusion and complications.",
    )

    off_score, off_reasons = surgical_usefulness_score(
        off_domain,
        case,
        family,
        "Outcomes / Evidence",
    )
    on_score, _ = surgical_usefulness_score(on_domain, case, family, "Outcomes / Evidence")

    assert off_score < on_score
    assert off_score < 20
    assert any("non-neurosurgical" in reason for reason in off_reasons)
    assert any("off-domain" in reason for reason in off_reasons)


def test_breast_tumor_resection_review_is_penalized_for_convexity_meningioma():
    case = parse_case_input(
        "right frontal convexity meningioma resection near the superior sagittal sinus"
    )
    family = select_procedure_family(case)
    record = EvidenceRecord(
        id="breast",
        source="pubmed",
        title="Breast tumor resection complications review",
        text="Review of non-neurosurgical breast oncology resection outcomes and morbidity.",
    )

    score, reasons = surgical_usefulness_score(record, case, family, "Complications")

    assert score <= 0
    assert any("non-neurosurgical" in reason for reason in reasons)
    assert any("off-domain" in reason for reason in reasons)


def test_legacy_neurosurg_relevance_penalizes_off_domain_procedural_papers():
    breast_score = neurosurg_relevance_score(
        "Breast tumor resection complications review",
        "Review of breast oncology resection outcomes and morbidity.",
    )
    fibroid_score = neurosurg_relevance_score(
        "Uterine fibroid embolization outcomes",
        "A gynecologic cohort reporting safety and complications after embolization.",
    )
    neuro_score = neurosurg_relevance_score(
        "Meningioma resection complications after frontal craniotomy",
        "Intracranial brain tumor operative outcomes and morbidity review.",
    )

    assert breast_score <= 0
    assert fibroid_score <= 0
    assert neuro_score > breast_score
    assert neuro_score > fibroid_score
