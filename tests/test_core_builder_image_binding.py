from caseprep.core.builder import _bind_image_bank
from caseprep.retrievers.image_bank import ImageBankRetriever


def test_bind_image_bank_extends_provenance_and_schema():
    schema = {"imaging_review": {"images_to_display_in_or": ["NCCT ASPECTS images."]}}
    provenance: list = []
    retriever = ImageBankRetriever(index=[
        {"fig_id": "PMC2_F1", "local_path": "/b.jpg", "pmcid": "PMC2", "pmid": "2",
         "cluster": "stroke_thrombectomy", "modality": "CT", "caption": "NCCT ASPECTS",
         "surgical_usefulness": 4, "tokens": ["ncct", "aspects"]},
    ])
    _bind_image_bank(schema, provenance, retriever=retriever, warnings=[])
    assert schema["imaging_review"]["bound_images"][0]["pmcid"] == "PMC2"
    assert any(p.field_path.startswith("imaging_review.bound_images") for p in provenance)


def test_bind_image_bank_handles_missing_index(tmp_path):
    schema = {"imaging_review": {"images_to_display_in_or": ["NCCT ASPECTS images."]}}
    provenance: list = []
    warnings: list = []
    # No retriever passed → builder constructs one from a non-existent index.
    _bind_image_bank(schema, provenance, retriever=None, warnings=warnings,
                     index_path=tmp_path / "absent.json")
    assert schema["imaging_review"].get("bound_images", []) == []
    assert provenance == []
