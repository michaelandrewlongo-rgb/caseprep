from caseprep.procedure_taxonomy import (
    PROCEDURE_FAMILIES,
    ProcedureFamily,
    get_procedure_family,
    iter_procedure_families,
    match_procedure_family,
)


EXPECTED_FAMILIES = {
    "spine_acdf": "spine",
    "tumor_convexity_meningioma": "supratentorial_tumor",
    "posterior_fossa_chiari": "posterior_fossa",
    "endovascular_thrombectomy": "vascular",
}


def test_v1_family_ids_exist_with_expected_profiles():
    assert set(PROCEDURE_FAMILIES) == set(EXPECTED_FAMILIES)
    for family_id, broad_profile in EXPECTED_FAMILIES.items():
        family = get_procedure_family(family_id)
        assert isinstance(family, ProcedureFamily)
        assert family.id == family_id
        assert family.broad_profile == broad_profile


def test_each_family_has_required_taxonomy_content():
    for family in iter_procedure_families():
        assert family.display_name
        assert family.procedure_aliases
        assert family.pathology_aliases
        assert family.approach_aliases
        assert family.required_fields
        assert family.missing_fact_prompts
        assert family.retrieval_templates
        assert family.section_headings
        assert family.eval_required_concepts

        assert set(family.retrieval_templates) >= {
            "anatomy",
            "technique",
            "complications",
            "outcomes",
        }
        assert set(family.section_headings) >= {
            "anatomy_at_risk",
            "operative_plan",
            "risk_and_rescue",
            "evidence",
        }
        assert all(template.strip() for template in family.retrieval_templates.values())
        assert all(headings for headings in family.section_headings.values())


def test_lookup_helpers_by_family_id_and_iteration():
    families = iter_procedure_families()
    assert isinstance(families, tuple)
    assert [family.id for family in families] == list(PROCEDURE_FAMILIES)
    assert get_procedure_family("spine_acdf") is PROCEDURE_FAMILIES["spine_acdf"]
    assert get_procedure_family("unknown") is None


def test_taxonomy_mappings_are_effectively_immutable():
    try:
        PROCEDURE_FAMILIES["new_family"] = PROCEDURE_FAMILIES["spine_acdf"]  # type: ignore[index]
    except TypeError:
        pass
    else:
        raise AssertionError("PROCEDURE_FAMILIES should be read-only")

    acdf = PROCEDURE_FAMILIES["spine_acdf"]
    chiari = PROCEDURE_FAMILIES["posterior_fossa_chiari"]

    try:
        acdf.retrieval_templates["new"] = "mutated"  # type: ignore[index]
    except TypeError:
        pass
    else:
        raise AssertionError("retrieval_templates should be read-only")

    try:
        acdf.section_headings["anatomy_at_risk"] = ("mutated",)  # type: ignore[index]
    except TypeError:
        pass
    else:
        raise AssertionError("section_headings should be read-only")

    assert "new" not in acdf.retrieval_templates
    assert chiari.section_headings["anatomy_at_risk"] == acdf.section_headings[
        "anatomy_at_risk"
    ]


def test_match_procedure_family_returns_none_for_blank_or_unknown_text():
    assert match_procedure_family("") is None
    assert match_procedure_family("   \n\t  ") is None
    assert match_procedure_family("appendectomy for acute appendicitis") is None


def test_match_procedure_family_by_canonical_family_id():
    assert match_procedure_family("Please prep spine_acdf") == PROCEDURE_FAMILIES[
        "spine_acdf"
    ]


def test_match_procedure_family_by_uppercase_and_mixed_case_aliases():
    assert match_procedure_family("ACDF") == PROCEDURE_FAMILIES["spine_acdf"]
    assert match_procedure_family("MeChAnIcAl ThRoMbEcToMy") == PROCEDURE_FAMILIES[
        "endovascular_thrombectomy"
    ]


def test_match_procedure_family_by_common_chiari_variant():
    assert match_procedure_family("Chiari 1 decompression") == PROCEDURE_FAMILIES[
        "posterior_fossa_chiari"
    ]


def test_match_procedure_family_by_aliases_and_canonical_cases():
    examples = {
        "C5-6 anterior cervical discectomy and fusion for right C6 radiculopathy": "spine_acdf",
        "right frontal convexity meningioma resection near the superior sagittal sinus": "tumor_convexity_meningioma",
        "suboccipital craniectomy and C1 laminectomy for Chiari I malformation with syringomyelia": "posterior_fossa_chiari",
        "mechanical thrombectomy for acute ischemic stroke due to right M1 MCA occlusion": "endovascular_thrombectomy",
    }
    for text, family_id in examples.items():
        assert match_procedure_family(text) == PROCEDURE_FAMILIES[family_id]


def test_family_eval_concepts_include_expected_terms():
    expected_terms = {
        "spine_acdf": ("anterior cervical exposure", "uncinate", "RLN", "posterior foraminotomy"),
        "tumor_convexity_meningioma": ("SSS", "Simpson grade", "bridging veins", "SRS"),
        "posterior_fossa_chiari": ("foramen magnum", "PICA", "syrinx", "pseudomeningocele"),
        "endovascular_thrombectomy": ("M1", "lenticulostriate", "mTICI", "sICH"),
    }
    for family_id, terms in expected_terms.items():
        concepts = " ".join(PROCEDURE_FAMILIES[family_id].eval_required_concepts).lower()
        for term in terms:
            assert term.lower() in concepts
