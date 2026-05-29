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
