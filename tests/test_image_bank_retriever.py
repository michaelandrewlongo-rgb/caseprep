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


def test_retrieve_modality_relax_when_no_modality_match():
    # Spec asks for MRI/DWI, but the only in-cluster image is CT → relax to
    # cluster pool rather than returning nothing.
    index = [
        {"fig_id": "PMC2_F1", "local_path": "/b.jpg", "pmcid": "PMC2", "pmid": "2",
         "cluster": "stroke_thrombectomy", "modality": "CT",
         "caption": "DWI infarct core", "surgical_usefulness": 4,
         "tokens": ["dwi", "infarct", "core"]},
    ]
    r = ImageBankRetriever(index=index)
    matches = r.retrieve("DWI infarct core images.", top_k=2)
    assert matches and matches[0].fig_id == "PMC2_F1"


def test_retrieve_tiebreak_prefers_higher_usefulness():
    # Two equal-scoring CT matches; higher surgical_usefulness must rank first.
    index = [
        {"fig_id": "PMC_low", "local_path": "/l.jpg", "pmcid": "PMCL", "pmid": "1",
         "cluster": "stroke_thrombectomy", "modality": "CT",
         "caption": "low", "surgical_usefulness": 3,
         "tokens": ["aspects", "hemorrhage"]},
        {"fig_id": "PMC_high", "local_path": "/h.jpg", "pmcid": "PMCH", "pmid": "2",
         "cluster": "stroke_thrombectomy", "modality": "CT",
         "caption": "high", "surgical_usefulness": 5,
         "tokens": ["aspects", "hemorrhage"]},
    ]
    r = ImageBankRetriever(index=index)
    matches = r.retrieve("NCCT ASPECTS hemorrhage images.", top_k=2)
    assert [m.fig_id for m in matches] == ["PMC_high", "PMC_low"]


def test_retrieve_admits_long_spec_with_two_token_overlap():
    # Verbose spec (~15 content tokens); a 2-token overlap must still bind,
    # where the old relative threshold (0.20) would have excluded it (2/15≈0.13).
    index = [
        {"fig_id": "PMC1_F1", "local_path": "/d.jpg", "pmcid": "PMC1", "pmid": "1",
         "cluster": "stroke_thrombectomy", "modality": "DSA/angiogram",
         "caption": "Final DSA TICI 3", "surgical_usefulness": 5,
         "tokens": ["dsa", "mtici", "recanalization", "thrombectomy"]},
    ]
    r = ImageBankRetriever(index=index)
    spec = ("Planned DSA working projections for access route, clot crossing, "
            "distal landing zone, branch anatomy, and final mTICI assessment.")
    matches = r.retrieve(spec, top_k=3)
    assert matches and matches[0].fig_id == "PMC1_F1"
    assert set(matches[0].matched_tokens) >= {"dsa", "mtici"}


def test_retrieve_rejects_single_token_overlap_noise():
    # 1-token overlap on a short spec (old score 1/4=0.25 passed 0.20) must now be rejected.
    index = [
        {"fig_id": "PMC_noise", "local_path": "/n.jpg", "pmcid": "PMCN", "pmid": "9",
         "cluster": "carotid_cervical_vascular", "modality": "CT",
         "caption": "Spine pedicle CT", "surgical_usefulness": 4,
         "tokens": ["hemorrhage", "pedicle", "screw"]},
    ]
    r = ImageBankRetriever(index=index)
    matches = r.retrieve("NCCT axial ASPECTS/hemorrhage-exclusion images.", top_k=3)
    assert matches == []   # only "hemorrhage" overlaps (1 token) → below MIN_OVERLAP
