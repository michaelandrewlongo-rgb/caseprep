from caseprep.retrievers.image_bank import (
    ImageMatch, parse_modality_hint, spec_tokens,
)


def test_parse_modality_hint_ncct_is_ct():
    assert parse_modality_hint("NCCT axial ASPECTS/hemorrhage-exclusion images.") == "CT"


def test_parse_modality_hint_dsa():
    assert parse_modality_hint("Planned DSA working projections for access route.") == "DSA/angiogram"


def test_parse_modality_hint_none_when_unknown():
    assert parse_modality_hint("Anatomic relationships overview.") is None


def test_spec_tokens_drops_stopwords():
    toks = spec_tokens("NCCT axial ASPECTS/hemorrhage-exclusion images.")
    assert "axial" not in toks and "images" not in toks
    assert "ncct" in toks and "aspects" in toks


def test_image_match_to_dict_rounds_score():
    m = ImageMatch("f", "/p.jpg", "cap", "PMC1", "1", 0.123456, "spec", ["a"])
    assert m.to_dict()["score"] == 0.1235
