"""Tests for deterministic evidence-pack registries."""

from __future__ import annotations

from caseprep.case_parser import parse_case_input
from caseprep.evidence_packs.thrombectomy import (
    EvidencePackItem,
    get_thrombectomy_pack,
    resolve_thrombectomy_pack,
)


def test_anterior_circulation_m1_thrombectomy_pack_contains_required_landmarks():
    pack = get_thrombectomy_pack("anterior_circulation_lvo_m1")

    assert pack is not None
    assert pack.id == "anterior_circulation_lvo_m1"

    items_by_id = {item.id: item for item in pack.items}
    expected_ids = {
        "mr_clean",
        "escape",
        "extend_ia",
        "swift_prime",
        "revascat",
        "hermes",
        "dawn",
        "defuse_3",
        "aha_asa_2019_update",
        "aha_asa_2018_guideline",
        "aha_asa_current_guideline",
        "eso_esmint_guideline_2019",
        "eso_esmint_recommendations",
        "eso_esmint_technical_guideline",
        "rescue_japan_limit",
        "select2",
        "angel_aspect",
        "tension",
        "laste",
    }
    assert expected_ids.issubset(items_by_id)

    assert items_by_id["mr_clean"].pmid == "25517348"
    assert items_by_id["mr_clean"].doi == "10.1056/NEJMoa1411587"
    assert items_by_id["escape"].pmid == "25671798"
    assert items_by_id["extend_ia"].doi == "10.1056/NEJMoa1414792"
    assert items_by_id["hermes"].pmid == "26898852"
    assert items_by_id["defuse_3"].doi == "10.1056/NEJMoa1713973"
    assert items_by_id["select2"].conditional is True
    assert items_by_id["angel_aspect"].conditional is True
    assert "guideline" in items_by_id["aha_asa_current_guideline"].tier.casefold()


def test_thrombectomy_pack_items_are_retrievable_and_self_describing():
    pack = get_thrombectomy_pack("anterior_circulation_lvo_m1")
    assert pack is not None

    for item in pack.items:
        assert isinstance(item, EvidencePackItem)
        assert item.id.strip()
        assert item.title_hint.strip()
        assert item.tier.strip()
        assert item.applicability_summary.strip()
        assert item.applicability == item.applicability_summary
        assert item.query_fallback.strip()
        assert item.required_for
        if item.must_retrieve:
            assert item.pmid or item.doi


def test_resolve_thrombectomy_pack_only_for_specific_anterior_m1_lvo_cases():
    right_m1 = parse_case_input(
        "mechanical thrombectomy for acute ischemic stroke due to right M1 MCA occlusion"
    )
    left_m1 = parse_case_input(
        "mechanical thrombectomy for acute ischemic stroke due to left M1 MCA occlusion"
    )
    bare_stroke = parse_case_input("stroke thrombectomy")
    generic_mca = parse_case_input(
        "mechanical thrombectomy for acute ischemic stroke due to left MCA occlusion"
    )
    m2_only = parse_case_input(
        "mechanical thrombectomy for acute ischemic stroke due to left M2 MCA occlusion"
    )
    basilar = parse_case_input(
        "mechanical thrombectomy for basilar artery occlusion acute ischemic stroke"
    )

    right_pack = resolve_thrombectomy_pack(right_m1)
    left_pack = resolve_thrombectomy_pack(left_m1)
    assert right_pack is not None
    assert left_pack is not None
    assert right_pack.id == "anterior_circulation_lvo_m1"
    assert left_pack.id == "anterior_circulation_lvo_m1"
    assert resolve_thrombectomy_pack(bare_stroke) is None
    assert resolve_thrombectomy_pack(generic_mca) is None
    assert resolve_thrombectomy_pack(m2_only) is None
    assert resolve_thrombectomy_pack(basilar) is None
