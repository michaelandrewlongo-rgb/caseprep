from caseprep.image_binding import bind_images_to_schema
from caseprep.retrievers.image_bank import ImageBankRetriever


def _retriever():
    index = [
        {"fig_id": "PMC2_F1", "local_path": "/b.jpg", "pmcid": "PMC2", "pmid": "2",
         "cluster": "stroke_thrombectomy", "modality": "CT",
         "caption": "NCCT ASPECTS", "surgical_usefulness": 4,
         "tokens": ["ncct", "aspects", "hemorrhage", "exclusion"]},
    ]
    return ImageBankRetriever(index=index)


def test_bind_attaches_matches_and_provenance():
    schema = {"imaging_review": {"images_to_display_in_or": [
        "NCCT axial ASPECTS/hemorrhage-exclusion images.",
        "Unrelated thoracic deformity correction.",
    ]}}
    records = bind_images_to_schema(schema, _retriever())

    bound = schema["imaging_review"]["bound_images"]
    assert len(bound) == 1
    assert bound[0]["pmcid"] == "PMC2"
    assert bound[0]["matched_spec"].startswith("NCCT")

    assert len(records) == 1
    rec = records[0]
    assert rec.field_path == "imaging_review.bound_images[0]"
    assert rec.value_status == "generated"
    assert "PMC2" in rec.source_ids and "pmid-2" in rec.source_ids
    assert "aspects" in rec.notes


def test_bind_no_section_is_noop():
    schema = {"topic": "x"}
    assert bind_images_to_schema(schema, _retriever()) == []


def test_bind_empty_retriever_attaches_nothing():
    schema = {"imaging_review": {"images_to_display_in_or": ["NCCT ASPECTS images."]}}
    records = bind_images_to_schema(schema, ImageBankRetriever(index=None))
    assert records == []
    assert schema["imaging_review"].get("bound_images", []) == []
