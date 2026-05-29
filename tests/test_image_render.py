from caseprep.schema import _render_bound_images
from caseprep.renderers.html import render_bound_images_html


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


def test_render_bound_images_html_has_figure_and_link():
    schema = {"imaging_review": {"bound_images": [
        {"local_path": "/img/a.jpg", "caption": "Final DSA", "pmcid": "PMC2",
         "pmid": "2", "score": 0.5, "matched_spec": "Final DSA projections."},
    ]}}
    html = render_bound_images_html(schema)
    assert "<figure" in html
    assert 'src="/img/a.jpg"' in html
    assert "PMC2" in html


def test_render_bound_images_html_empty_when_none():
    assert render_bound_images_html({"imaging_review": {}}) == ""


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
    html = render_bound_images_html(schema)
    assert "Final DSA TICI 3" in html and "PMC1" in html and "<figure" in html
