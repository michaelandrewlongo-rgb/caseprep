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


def test_parse_modality_hint_first_match_wins():
    # "cta" precedes "perfusion", so CT_angiography wins over CT
    assert parse_modality_hint("CTA source images and perfusion maps.") == "CT_angiography"


def test_image_match_to_dict_rounds_score():
    m = ImageMatch("f", "/p.jpg", "cap", "PMC1", "1", 0.123456, "spec", ["a"])
    assert m.to_dict()["score"] == 0.1235


from caseprep.retrievers.image_bank import ImageBankRetriever


def _index():
    return [
        {"fig_id": "PMC1_F1", "local_path": "/a.jpg", "pmcid": "PMC1", "pmid": "1",
         "cluster": "stroke_thrombectomy", "modality": "DSA/angiogram",
         "caption": "Final DSA showing TICI 3", "surgical_usefulness": 5,
         "tokens": ["dsa", "tici", "recanalization", "thrombectomy"]},
        {"fig_id": "PMC2_F1", "local_path": "/b.jpg", "pmcid": "PMC2", "pmid": "2",
         "cluster": "stroke_thrombectomy", "modality": "CT",
         "caption": "NCCT ASPECTS", "surgical_usefulness": 4,
         "tokens": ["ncct", "aspects", "hemorrhage", "exclusion"]},
        {"fig_id": "PMC9_F1", "local_path": "/z.jpg", "pmcid": "PMC9", "pmid": "9",
         "cluster": "spine_trauma", "modality": "CT",
         "caption": "Off-topic", "surgical_usefulness": 5,
         "tokens": ["odontoid", "fracture"]},
    ]


def test_retrieve_binds_aspects_to_ct_image():
    r = ImageBankRetriever(index=_index())
    matches = r.retrieve("NCCT axial ASPECTS/hemorrhage-exclusion images.", top_k=2)
    assert matches and matches[0].fig_id == "PMC2_F1"
    assert matches[0].pmcid == "PMC2"
    assert "aspects" in matches[0].matched_tokens


def test_retrieve_excludes_off_cluster_images():
    r = ImageBankRetriever(index=_index())
    matches = r.retrieve("NCCT axial ASPECTS images.", top_k=5)
    assert all(m.fig_id != "PMC9_F1" for m in matches)


def test_retrieve_below_threshold_returns_empty():
    r = ImageBankRetriever(index=_index())
    assert r.retrieve("unrelated thoracic deformity correction.", top_k=2) == []


def test_retrieve_none_index_returns_empty():
    assert ImageBankRetriever(index=None).retrieve("NCCT ASPECTS images.") == []
