from caseprep.schema import _render_bound_images


def test_render_bound_images_groups_by_spec_with_source_link():
    schema = {"imaging_review": {"bound_images": [
        {"local_path": "/img/a.jpg", "caption": "NCCT ASPECTS", "pmcid": "PMC2",
         "pmid": "2", "score": 0.5, "matched_spec": "NCCT axial ASPECTS images."},
    ]}}
    out = _render_bound_images(schema)
    assert "NCCT ASPECTS" in out
    assert "/img/a.jpg" in out
    assert "PMC2" in out                      # source attribution present
    assert "ncbi.nlm.nih.gov" in out          # clickable PMC link


def test_render_bound_images_empty_when_none():
    assert _render_bound_images({"imaging_review": {}}) == ""


def test_render_bound_images_no_pmcid_no_link():
    schema = {"imaging_review": {"bound_images": [
        {"local_path": "/img/b.jpg", "caption": "Axial NCCT", "matched_spec": "NCCT."},
    ]}}
    out = _render_bound_images(schema)
    assert "ncbi" not in out
    assert "source:" not in out


from caseprep.image_binding import bind_images_to_schema
from caseprep.retrievers.image_bank import ImageBankRetriever


def test_binding_then_render_round_trip():
    schema = {"imaging_review": {"images_to_display_in_or": [
        "Planned DSA working projections for final mTICI assessment.",
    ]}}
    retriever = ImageBankRetriever(index=[
        {"fig_id": "PMC1_F1", "local_path": "/d.jpg", "pmcid": "PMC1", "pmid": "1",
         "cluster": "stroke_thrombectomy", "modality": "DSA/angiogram",
         "caption": "Final DSA TICI 3", "surgical_usefulness": 5,
         "tokens": ["dsa", "projections", "mtici", "final"]},
    ])
    bind_images_to_schema(schema, retriever)
    out = _render_bound_images(schema)
    assert "Final DSA TICI 3" in out and "PMC1" in out
