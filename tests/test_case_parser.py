from caseprep.case_parser import (
    CaseField,
    CaseSpec,
    deterministic_parse_case,
    parse_case_input,
    select_procedure_family,
)


def assert_field_contains(field: CaseField, *needles: str) -> None:
    assert field.value is not None
    normalized = field.value.casefold()
    assert any(needle.casefold() in normalized for needle in needles)
    assert field.confidence > 0
    assert field.source != "missing"


def assert_missing(field: CaseField) -> None:
    assert field.value is None
    assert field.confidence == 0.0
    assert field.source == "missing"


def test_acdf_full_case_extracts_fields_and_family():
    case = deterministic_parse_case(
        "C5-6 anterior cervical discectomy and fusion for right C6 radiculopathy "
        "from foraminal disc osteophyte complex"
    )

    assert case.raw_input.startswith("C5-6")
    assert case.procedure_family.value == "spine_acdf"
    assert case.broad_profile.value == "spine"
    assert_field_contains(case.procedure, "anterior cervical discectomy and fusion", "ACDF")
    assert_field_contains(case.approach, "anterior cervical")
    assert_field_contains(case.laterality, "right")
    assert_field_contains(case.level_or_segment, "C5-6", "C6")
    assert_field_contains(case.pathology, "radiculopathy", "disc osteophyte")
    assert not case.degraded
    assert case.missing_critical_facts == ()
    assert select_procedure_family(case).id == "spine_acdf"


def test_convexity_meningioma_full_case_extracts_fields_and_family():
    case = parse_case_input(
        "right frontal convexity meningioma resection near the superior sagittal sinus"
    )

    assert case.procedure_family.value == "tumor_convexity_meningioma"
    assert case.broad_profile.value == "supratentorial_tumor"
    assert_field_contains(case.pathology, "convexity meningioma", "frontal meningioma")
    assert_field_contains(case.procedure, "resection", "craniotomy")
    assert_field_contains(case.laterality, "right")
    assert_field_contains(case.anatomic_location, "frontal convexity", "superior sagittal sinus")
    assert not case.degraded


def test_chiari_full_case_extracts_fields_and_family():
    case = deterministic_parse_case(
        "suboccipital craniectomy and C1 laminectomy for Chiari I malformation "
        "with syringomyelia"
    )

    assert case.procedure_family.value == "posterior_fossa_chiari"
    assert case.broad_profile.value == "posterior_fossa"
    assert_field_contains(case.procedure, "suboccipital craniectomy and C1 laminectomy", "Chiari decompression")
    assert_field_contains(case.approach, "suboccipital")
    assert_field_contains(case.level_or_segment, "C1")
    assert_field_contains(case.pathology, "Chiari I")
    assert any("syr" in modifier.value.casefold() for modifier in case.patient_modifiers if modifier.value)
    assert not case.degraded


def test_thrombectomy_full_case_extracts_fields_and_family():
    case = deterministic_parse_case(
        "mechanical thrombectomy for acute ischemic stroke due to right M1 "
        "middle cerebral artery occlusion"
    )

    assert case.procedure_family.value == "endovascular_thrombectomy"
    assert case.broad_profile.value == "vascular"
    assert_field_contains(case.procedure, "mechanical thrombectomy")
    assert_field_contains(case.laterality, "right")
    assert_field_contains(case.level_or_segment, "M1", "MCA")
    assert_field_contains(case.anatomic_location, "middle cerebral artery", "MCA")
    assert_field_contains(case.pathology, "acute ischemic stroke", "M1 occlusion")
    assert not case.degraded


def test_empty_input_is_degraded_with_major_missing_fields_and_no_family():
    case = deterministic_parse_case("   \n\t  ")

    assert case.degraded
    assert case.procedure_family.value is None
    assert case.broad_profile.value is None
    assert_missing(case.pathology)
    assert_missing(case.procedure)
    assert_missing(case.approach)
    missing = " ".join(case.missing_critical_facts).casefold()
    assert "pathology" in missing
    assert "procedure" in missing
    assert "supported procedure family" in missing


def test_full_thrombectomy_still_surfaces_missing_selection_and_access_facts():
    case = deterministic_parse_case(
        "mechanical thrombectomy for acute ischemic stroke due to right M1 "
        "middle cerebral artery occlusion"
    )

    assert case.procedure_family.value == "endovascular_thrombectomy"
    assert not case.degraded
    missing = " ".join(case.missing_critical_facts).casefold()
    assert "last-known-well" in missing
    assert "nihss" in missing
    assert "imaging selection" in missing
    assert "access plan" in missing


def test_convexity_meningioma_surfaces_missing_venous_relationship():
    case = deterministic_parse_case("right frontal convexity meningioma resection")

    assert case.procedure_family.value == "tumor_convexity_meningioma"
    assert "venous/sinus relationship" in case.missing_critical_facts


def test_topic_only_family_match_has_lower_confidence_than_full_canonical_case():
    full = deterministic_parse_case(
        "suboccipital craniectomy and C1 laminectomy for Chiari I malformation"
    )
    topic_only = deterministic_parse_case("Chiari")

    assert full.procedure_family.value == topic_only.procedure_family.value
    assert topic_only.procedure_family.confidence < full.procedure_family.confidence
    assert topic_only.broad_profile.confidence == topic_only.procedure_family.confidence


TOPIC_ONLY_CASES = [
    "vestibular schwannoma",
    "MCA aneurysm",
    "cervical radiculopathy",
    "Chiari",
    "stroke thrombectomy",
]


def test_topic_only_cases_are_degraded_and_do_not_guess_approach_or_procedure():
    for raw in TOPIC_ONLY_CASES:
        case = deterministic_parse_case(raw)
        assert case.degraded, raw
        assert case.degradation_reason, raw
        assert case.missing_critical_facts, raw
        assert case.raw_input == raw
        assert case.approach.source == "missing", raw
        if raw != "stroke thrombectomy":
            assert_missing(case.procedure)
        else:
            assert_field_contains(case.procedure, "stroke thrombectomy", "thrombectomy")
            assert "occlusion location" in " ".join(case.missing_critical_facts).casefold()


def test_topic_only_inputs_extract_known_pathology_or_family_without_silent_guessing():
    cervical = deterministic_parse_case("cervical radiculopathy")
    assert cervical.procedure_family.value == "spine_acdf"
    assert_field_contains(cervical.pathology, "cervical radiculopathy")
    assert_missing(cervical.procedure)
    assert "procedure" in " ".join(cervical.missing_critical_facts).casefold()

    chiari = deterministic_parse_case("Chiari")
    assert chiari.procedure_family.value == "posterior_fossa_chiari"
    assert_field_contains(chiari.pathology, "Chiari")
    assert_missing(chiari.procedure)
    assert_missing(chiari.approach)

    vestibular = deterministic_parse_case("vestibular schwannoma")
    assert vestibular.procedure_family.value is None
    assert_field_contains(vestibular.pathology, "vestibular schwannoma")
    assert_missing(vestibular.procedure)
    assert_missing(vestibular.approach)

    aneurysm = deterministic_parse_case("MCA aneurysm")
    assert aneurysm.procedure_family.value is None
    assert_field_contains(aneurysm.pathology, "MCA aneurysm")
    assert_missing(aneurysm.procedure)
    assert_missing(aneurysm.approach)


def test_case_fields_can_be_serialized_to_dicts():
    case = deterministic_parse_case("stroke thrombectomy")
    data = case.to_dict()

    assert data["raw_input"] == "stroke thrombectomy"
    assert data["procedure"]["value"] == case.procedure.value
    assert isinstance(data["patient_modifiers"], list)
    assert isinstance(data["missing_critical_facts"], list)
