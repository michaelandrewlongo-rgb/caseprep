"""Tests for procedure-aware retrieval query planning."""

from __future__ import annotations

import pytest

from caseprep.case_parser import parse_case_input, select_procedure_family
from caseprep.core import BuildCasePlanRequest, EvidenceRecord
from caseprep.core.builder import CoreRetrieverSet, build_core_case_plan
from caseprep.retrieval_planning import build_case_queries


CANONICAL_CASES = {
    "spine_acdf": (
        "C5-6 anterior cervical discectomy and fusion for right C6 "
        "radiculopathy from foraminal disc osteophyte complex"
    ),
    "tumor_convexity_meningioma": (
        "right frontal convexity meningioma resection near the superior sagittal sinus"
    ),
    "posterior_fossa_chiari": (
        "suboccipital craniectomy and C1 laminectomy for Chiari I malformation "
        "with syringomyelia"
    ),
    "endovascular_thrombectomy": (
        "mechanical thrombectomy for acute ischemic stroke from M1 occlusion using "
        "balloon guide aspiration and stent retriever"
    ),
}


@pytest.mark.parametrize(
    ("family_id", "expected_terms"),
    [
        (
            "spine_acdf",
            ["ACDF", "anterior cervical", "uncinate", "RLN"],
        ),
        (
            "tumor_convexity_meningioma",
            ["superior sagittal sinus", "bridging veins", "Simpson"],
        ),
        (
            "posterior_fossa_chiari",
            ["foramen magnum", "C1", "duraplasty", "syringomyelia"],
        ),
        (
            "endovascular_thrombectomy",
            ["M1", "M2", "balloon guide", "aspiration", "stent retriever", "TICI"],
        ),
    ],
)
def test_build_case_queries_uses_family_templates_for_canonical_cases(
    family_id: str,
    expected_terms: list[str],
):
    case = parse_case_input(CANONICAL_CASES[family_id])
    family = select_procedure_family(case)

    axes = build_case_queries(case, family)
    combined_queries = "\n".join(axis.query for axis in axes)

    assert family is not None
    assert family.id == family_id
    assert [axis.label for axis in axes] == [
        "Anatomy / Relevant Structures",
        "Outcomes / Evidence",
        "Surgical Technique",
        "Complications",
        "Reviews / Landmarks",
    ]
    assert [axis.filter_type for axis in axes] == [
        None,
        "therapy",
        None,
        "etiology",
        "systematic_review",
    ]
    for term in expected_terms:
        assert term.casefold() in combined_queries.casefold()
    assert "systematic review" in axes[-1].query


def test_build_case_queries_falls_back_to_legacy_topic_axes_without_family():
    case = parse_case_input("generic operative planning topic")

    axes = build_case_queries(case, None)

    assert axes[0].label == "Anatomy / Relevant Structures"
    assert "generic operative planning topic" in axes[0].query
    assert axes[1].query == "generic operative planning topic outcomes"
    assert axes[1].filter_type == "therapy"
    assert axes[2].query == "generic operative planning topic surgical technique approach"
    assert axes[3].query == "generic operative planning topic complications adverse"
    assert axes[3].filter_type == "etiology"
    assert axes[4].query == "generic operative planning topic"
    assert axes[4].filter_type == "systematic_review"


@pytest.mark.asyncio
async def test_core_builder_retrieves_with_family_template_queries_for_acdf():
    pubmed_calls = []

    class FakePubMedRetriever:
        async def retrieve(
            self,
            query,
            *,
            max_results=10,
            filter_type=None,
            include_abstracts=True,
        ):
            pubmed_calls.append((query, filter_type))
            return [
                EvidenceRecord(
                    id=f"pmid-{len(pubmed_calls)}",
                    source="pubmed",
                    title=query,
                )
            ]

    class EmptyRadiologyRetriever:
        async def retrieve(self, query, *, max_results=5, modality=None):
            return []

    class EmptyCorpusRetriever:
        def retrieve(self, fts_query, *, subdomain=None, top_n=8):
            return []

    result = await build_core_case_plan(
        BuildCasePlanRequest(
            case_input=CANONICAL_CASES["spine_acdf"],
            max_per_category=1,
        ),
        retrievers=CoreRetrieverSet(
            pubmed=FakePubMedRetriever(),
            radiology=EmptyRadiologyRetriever(),
            corpus=EmptyCorpusRetriever(),
        ),
    )

    queries = [query for query, _ in pubmed_calls]
    assert len(queries) == 5
    assert queries[0].startswith("ACDF anterior cervical exposure anatomy")
    assert queries[1].startswith("ACDF cervical radiculopathy outcomes")
    assert queries[1] != f"{CANONICAL_CASES['spine_acdf']} outcomes"
    assert queries[2].startswith("anterior cervical discectomy fusion technique")
    assert queries[3].startswith("ACDF complications")
    assert pubmed_calls[1][1] == "therapy"
    assert pubmed_calls[3][1] == "etiology"
    assert pubmed_calls[4][1] == "systematic_review"
    assert result.structured["retrieval"]["pubmed_queries"][0]["query"] == queries[0]
    assert all(
        record.metadata["procedure_family"] == "spine_acdf"
        for record in result.evidence
        if record.source == "pubmed"
    )
