"""Tests for the initial transport-agnostic CasePrep core builder."""

from __future__ import annotations

import pytest

from caseprep.core import BuildCasePlanRequest, EvidenceRecord
from caseprep.core.builder import CoreRetrieverSet, build_core_case_plan, dedupe_evidence


@pytest.mark.asyncio
async def test_core_builder_classifies_profile_and_normalizes_retriever_evidence():
    calls = []

    class FakePubMedRetriever:
        async def retrieve(
            self,
            query,
            *,
            max_results=10,
            filter_type=None,
            include_abstracts=True,
        ):
            calls.append(
                ("pubmed", query, max_results, filter_type, include_abstracts)
            )
            axis = filter_type or "unfiltered"
            return [
                EvidenceRecord(
                    id=f"pmid-{len(calls)}",
                    source="pubmed",
                    title=query,
                    metadata={"axis": axis},
                )
            ]

    class FakeRadiologyRetriever:
        async def retrieve(self, query, *, max_results=5, modality=None):
            calls.append(("radiology", query, max_results, modality))
            return [
                EvidenceRecord(
                    id="openi-1",
                    source="openi",
                    title="Aneurysm angiogram",
                )
            ]

    class FakeCorpusRetriever:
        def retrieve(self, fts_query, *, subdomain=None, top_n=8):
            calls.append(("corpus", fts_query, subdomain, top_n))
            return [
                EvidenceRecord(
                    id="corpus-W1",
                    source="corpus",
                    title="Aneurysm corpus paper",
                )
            ]

    result = await build_core_case_plan(
        BuildCasePlanRequest(
            topic="anterior communicating artery aneurysm clipping",
            max_per_category=2,
        ),
        retrievers=CoreRetrieverSet(
            pubmed=FakePubMedRetriever(),
            radiology=FakeRadiologyRetriever(),
            corpus=FakeCorpusRetriever(),
        ),
    )

    assert result.mode == "core"
    assert result.topic == "anterior communicating artery aneurysm clipping"
    assert result.structured["profile"]["name"] == "vascular"
    assert result.structured["profile"]["source"] == "substring"
    assert result.structured["retrieval"]["evidence_count"] == 7
    assert result.structured["retrieval"]["pubmed_axes"] == [
        "Anatomy / Relevant Structures",
        "Outcomes / Evidence",
        "Surgical Technique",
        "Complications",
        "Reviews / Landmarks",
    ]
    assert result.structured["sections"][0]["id"] == "anatomy-relevant-structures"
    assert result.structured["sections"][0]["evidence_ids"] == ["pmid-1"]
    assert any(
        record.field_path == "sections.anatomy-relevant-structures"
        and record.source_ids == ["pmid-1"]
        for record in result.provenance
    )
    assert any(
        record.field_path == "profile"
        and record.value_status == "generated"
        for record in result.provenance
    )
    assert {record.source for record in result.evidence} == {
        "corpus",
        "openi",
        "pubmed",
    }
    assert calls[0][0] == "pubmed"
    assert "anterior communicating artery aneurysm clipping" in calls[0][1]
    assert calls[0][2] == 2
    assert calls[-2] == (
        "radiology",
        "anterior communicating artery aneurysm clipping radiology imaging",
        2,
        None,
    )
    assert calls[-1] == (
        "corpus",
        "anterior communicating artery aneurysm clipping",
        "aneurysm_sah",
        2,
    )


@pytest.mark.asyncio
async def test_core_builder_accepts_case_input_only_request():
    calls = []

    class EmptyPubMedRetriever:
        async def retrieve(
            self,
            query,
            *,
            max_results=10,
            filter_type=None,
            include_abstracts=True,
        ):
            calls.append(("pubmed", query, max_results, filter_type))
            return []

    class EmptyRadiologyRetriever:
        async def retrieve(self, query, *, max_results=5, modality=None):
            calls.append(("radiology", query, max_results, modality))
            return []

    class EmptyCorpusRetriever:
        def retrieve(self, fts_query, *, subdomain=None, top_n=8):
            calls.append(("corpus", fts_query, subdomain, top_n))
            return []

    result = await build_core_case_plan(
        BuildCasePlanRequest(
            case_input="  83F R ICA terminus aneurysm clipping  ",
            max_per_category=1,
        ),
        retrievers=CoreRetrieverSet(
            pubmed=EmptyPubMedRetriever(),
            radiology=EmptyRadiologyRetriever(),
            corpus=EmptyCorpusRetriever(),
        ),
    )

    assert result.topic == "83F R ICA terminus aneurysm clipping"
    assert isinstance(result.topic, str)
    assert "83F R ICA terminus aneurysm clipping" in result.markdown
    assert calls[-1][0] == "corpus"
    assert calls[-1][1] == "83F R ICA terminus aneurysm clipping"


@pytest.mark.asyncio
async def test_core_builder_maps_mma_csdh_to_hemorrhage_corpus_subdomain():
    calls = []

    class EmptyPubMedRetriever:
        async def retrieve(
            self,
            query,
            *,
            max_results=10,
            filter_type=None,
            include_abstracts=True,
        ):
            return []

    class EmptyRadiologyRetriever:
        async def retrieve(self, query, *, max_results=5, modality=None):
            return []

    class FakeCorpusRetriever:
        def retrieve(self, fts_query, *, subdomain=None, top_n=8):
            calls.append((fts_query, subdomain, top_n))
            return [
                EvidenceRecord(
                    id="corpus-csdh",
                    source="corpus",
                    title="MMA embolization for chronic subdural hematoma",
                    text="MMA embolization evidence.",
                )
            ]

    result = await build_core_case_plan(
        BuildCasePlanRequest(
            topic="middle meningeal artery embolization chronic subdural hematoma",
            max_per_category=1,
        ),
        retrievers=CoreRetrieverSet(
            pubmed=EmptyPubMedRetriever(),
            radiology=EmptyRadiologyRetriever(),
            corpus=FakeCorpusRetriever(),
        ),
    )

    assert calls == [
        (
            "middle meningeal artery embolization chronic subdural hematoma",
            "intracranial_hemorrhage",
            1,
        )
    ]
    assert result.structured["retrieval"]["sources"]["corpus"] == 1


@pytest.mark.asyncio
async def test_core_builder_writes_synthesized_sections_to_dossier_files(tmp_path):
    class FakePubMedRetriever:
        async def retrieve(
            self,
            query,
            *,
            max_results=10,
            filter_type=None,
            include_abstracts=True,
        ):
            if filter_type == "therapy":
                return []
            if "surgical technique" in query:
                return [
                    EvidenceRecord(
                        id="pmid-technique",
                        source="pubmed",
                        title="Technique Evidence",
                        text="Use bilateral distal middle meningeal artery access.",
                        metadata={"pubdate": "2024", "axis": "Surgical Technique"},
                    )
                ]
            if "complications" in query:
                return [
                    EvidenceRecord(
                        id="pmid-complication",
                        source="pubmed",
                        title="Complication Evidence",
                        text="Postprocedure seizure risk requires monitoring.",
                        metadata={"pubdate": "2025", "axis": "Complications"},
                    )
                ]
            return [
                EvidenceRecord(
                    id="pmid-anatomy",
                    source="pubmed",
                    title="Anatomy Evidence",
                    text="The middle meningeal artery supplies the dura.",
                    metadata={
                        "pubdate": "2023",
                        "axis": "Anatomy / Relevant Structures",
                    },
                )
            ]

    class EmptyRadiologyRetriever:
        async def retrieve(self, query, *, max_results=5, modality=None):
            return []

    class EmptyCorpusRetriever:
        def retrieve(self, fts_query, *, subdomain=None, top_n=8):
            return []

    output_dir = tmp_path / "mma-csdh-caseprep"

    result = await build_core_case_plan(
        BuildCasePlanRequest(
            topic="middle meningeal artery embolization chronic subdural hematoma",
            output_dir=output_dir,
            max_per_category=1,
        ),
        retrievers=CoreRetrieverSet(
            pubmed=FakePubMedRetriever(),
            radiology=EmptyRadiologyRetriever(),
            corpus=EmptyCorpusRetriever(),
        ),
    )

    anatomy = (output_dir / "03-anatomy-at-risk.md").read_text(encoding="utf-8")
    operative = (output_dir / "04-operative-plan.md").read_text(encoding="utf-8")
    risk = (output_dir / "05-risk-and-rescue.md").read_text(encoding="utf-8")
    evidence = (output_dir / "07-evidence.md").read_text(encoding="utf-8")

    assert "The middle meningeal artery supplies the dura. [pmid-anatomy]" in anatomy
    assert (
        "Use bilateral distal middle meningeal artery access. [pmid-technique]"
        in operative
    )
    assert (
        "Postprocedure seizure risk requires monitoring. [pmid-complication]"
        in risk
    )
    assert "pmid-anatomy" in evidence
    assert "03-anatomy-at-risk.md" in {artifact.path.name for artifact in result.artifacts}


@pytest.mark.asyncio
async def test_core_builder_writes_structured_case_to_yaml_and_summary(tmp_path):
    output_dir = tmp_path / "acdf-caseprep"

    result = await build_core_case_plan(
        BuildCasePlanRequest(
            case_input=(
                "C5-6 anterior cervical discectomy and fusion for right C6 "
                "radiculopathy from foraminal disc osteophyte complex"
            ),
            output_dir=output_dir,
            max_per_category=1,
        ),
        retrievers=EMPTY_RETRIEVERS,
    )

    yaml_text = (output_dir / "caseprep.yaml").read_text(encoding="utf-8")
    summary = (output_dir / "01-case-summary.md").read_text(encoding="utf-8")

    assert result.structured["case"]["raw_input"] in yaml_text
    assert "structured_case:" in yaml_text
    assert "raw_input: \"C5-6 anterior cervical discectomy" in yaml_text
    assert "procedure_family:" in yaml_text
    assert "value: \"spine_acdf\"" in yaml_text
    assert "missing_critical_facts:" in yaml_text
    assert "id: \"spine_acdf\"" in yaml_text

    assert "## Parsed Case Summary" in summary
    assert "Parsed procedure: anterior cervical discectomy and fusion" in summary
    assert "Parsed approach: anterior cervical" in summary
    assert "Procedure family: Anterior cervical discectomy and fusion (ACDF) (`spine_acdf`)" in summary
    assert "Broad profile: spine" in summary
    assert "Missing critical facts:" in summary


@pytest.mark.asyncio
async def test_core_builder_degraded_summary_does_not_claim_booked_approach(tmp_path):
    output_dir = tmp_path / "chiari-caseprep"

    await build_core_case_plan(
        BuildCasePlanRequest(
            case_input="Chiari",
            output_dir=output_dir,
            max_per_category=1,
        ),
        retrievers=EMPTY_RETRIEVERS,
    )

    summary = (output_dir / "01-case-summary.md").read_text(encoding="utf-8")

    assert "Degradation status: degraded/generic case summary" in summary
    assert "Parsed procedure: generic/degraded" in summary
    assert "Parsed approach: generic/degraded — no booked approach identified" in summary
    assert "do not treat as a confirmed booked approach" in summary
    assert "Approach: suboccipital" not in summary


@pytest.mark.asyncio
async def test_core_builder_strict_provenance_warn_mode_surfaces_warnings(monkeypatch):
    class EmptyPubMedRetriever:
        async def retrieve(
            self,
            query,
            *,
            max_results=10,
            filter_type=None,
            include_abstracts=True,
        ):
            return []

    class EmptyRadiologyRetriever:
        async def retrieve(self, query, *, max_results=5, modality=None):
            return []

    class EmptyCorpusRetriever:
        def retrieve(self, fts_query, *, subdomain=None, top_n=8):
            return []

    monkeypatch.setenv("CASEPREP_STRICT_PROVENANCE", "warn")

    result = await build_core_case_plan(
        BuildCasePlanRequest(topic="aneurysm", max_per_category=1),
        retrievers=CoreRetrieverSet(
            pubmed=EmptyPubMedRetriever(),
            radiology=EmptyRadiologyRetriever(),
            corpus=EmptyCorpusRetriever(),
        ),
    )

    assert any(
        warning
        == "Provenance warning: Required field sections has no provenance-backed value"
        for warning in result.warnings
    )


class EmptyCorePubMedRetriever:
    async def retrieve(
        self,
        query,
        *,
        max_results=10,
        filter_type=None,
        include_abstracts=True,
    ):
        return []


class EmptyCoreRadiologyRetriever:
    async def retrieve(self, query, *, max_results=5, modality=None):
        return []


class EmptyCoreCorpusRetriever:
    def retrieve(self, fts_query, *, subdomain=None, top_n=8):
        return []


EMPTY_RETRIEVERS = CoreRetrieverSet(
    pubmed=EmptyCorePubMedRetriever(),
    radiology=EmptyCoreRadiologyRetriever(),
    corpus=EmptyCoreCorpusRetriever(),
)


@pytest.mark.asyncio
async def test_core_builder_includes_parsed_case_and_family_profile_for_acdf():
    result = await build_core_case_plan(
        BuildCasePlanRequest(
            case_input=(
                "C5-6 anterior cervical discectomy and fusion for right C6 "
                "radiculopathy from foraminal disc osteophyte complex"
            ),
            max_per_category=1,
        ),
        retrievers=EMPTY_RETRIEVERS,
    )

    assert result.structured["case"]["procedure_family"]["value"] == "spine_acdf"
    assert result.structured["case"]["broad_profile"]["value"] == "spine"
    assert result.structured["procedure_family"]["id"] == "spine_acdf"
    assert result.structured["procedure_family"]["display_name"] == (
        "Anterior cervical discectomy and fusion (ACDF)"
    )
    assert result.structured["profile"]["name"] == "spine"
    assert result.structured["profile"]["matched_term"] == "spine_acdf"
    assert result.structured["profile"]["source"] == "case_parser"


@pytest.mark.asyncio
async def test_core_builder_tags_radiology_and_corpus_with_trusted_family_metadata():
    class FakeRadiologyRetriever:
        async def retrieve(self, query, *, max_results=5, modality=None):
            return [
                EvidenceRecord(
                    id="openi-acdf",
                    source="openi",
                    title="ACDF lateral radiograph",
                )
            ]

    class FakeCorpusRetriever:
        def retrieve(self, fts_query, *, subdomain=None, top_n=8):
            return [
                EvidenceRecord(
                    id="corpus-acdf",
                    source="corpus",
                    title="ACDF corpus paper",
                )
            ]

    result = await build_core_case_plan(
        BuildCasePlanRequest(
            case_input=(
                "C5-6 anterior cervical discectomy and fusion for right C6 "
                "radiculopathy from foraminal disc osteophyte complex"
            ),
            max_per_category=1,
        ),
        retrievers=CoreRetrieverSet(
            pubmed=EmptyCorePubMedRetriever(),
            radiology=FakeRadiologyRetriever(),
            corpus=FakeCorpusRetriever(),
        ),
    )

    tagged = {
        record.id: record.metadata
        for record in result.evidence
        if record.id in {"openi-acdf", "corpus-acdf"}
    }

    assert set(tagged) == {"openi-acdf", "corpus-acdf"}
    assert all(
        metadata["procedure_family"] == "spine_acdf"
        and metadata["broad_profile"] == "spine"
        for metadata in tagged.values()
    )


@pytest.mark.asyncio
async def test_core_builder_family_profile_overrides_topic_classifier_for_convexity_meningioma():
    result = await build_core_case_plan(
        BuildCasePlanRequest(
            case_input="right frontal convexity meningioma resection near the superior sagittal sinus",
            max_per_category=1,
        ),
        retrievers=EMPTY_RETRIEVERS,
    )

    assert result.structured["case"]["procedure_family"]["value"] == (
        "tumor_convexity_meningioma"
    )
    assert result.structured["procedure_family"]["id"] == "tumor_convexity_meningioma"
    assert result.structured["profile"]["name"] == "supratentorial_tumor"
    assert result.structured["profile"]["matched_term"] == "tumor_convexity_meningioma"
    assert result.structured["profile"]["source"] == "case_parser"


@pytest.mark.asyncio
async def test_core_builder_unknown_case_falls_back_to_topic_classifier_without_family():
    result = await build_core_case_plan(
        BuildCasePlanRequest(
            case_input="generic operative planning topic",
            max_per_category=1,
        ),
        retrievers=EMPTY_RETRIEVERS,
    )

    assert result.structured["case"]["procedure_family"]["value"] is None
    assert result.structured["procedure_family"] is None
    assert result.structured["profile"]["name"] == "skull_base"
    assert result.structured["profile"]["source"] == "fallback"


@pytest.mark.asyncio
async def test_core_builder_supports_posterior_fossa_chiari_profile_without_crash():
    result = await build_core_case_plan(
        BuildCasePlanRequest(
            case_input=(
                "suboccipital craniectomy and C1 laminectomy for Chiari I "
                "malformation with syringomyelia"
            ),
            max_per_category=1,
        ),
        retrievers=EMPTY_RETRIEVERS,
    )

    assert result.structured["case"]["procedure_family"]["value"] == (
        "posterior_fossa_chiari"
    )
    assert result.structured["case"]["broad_profile"]["value"] == "posterior_fossa"
    assert result.structured["profile"]["name"] == "posterior_fossa"
    assert result.structured["profile"]["matched_term"] == "posterior_fossa_chiari"
    assert result.structured["profile"]["source"] == "case_parser"
    assert result.structured["retrieval"]["corpus_subdomain"] is None


@pytest.mark.asyncio
async def test_core_builder_does_not_use_degraded_topic_only_parser_profile():
    pubmed_calls = []

    class CapturingPubMedRetriever:
        async def retrieve(
            self,
            query,
            *,
            max_results=10,
            filter_type=None,
            include_abstracts=True,
        ):
            pubmed_calls.append((query, filter_type))
            return []

    result = await build_core_case_plan(
        BuildCasePlanRequest(case_input="Chiari", max_per_category=1),
        retrievers=CoreRetrieverSet(
            pubmed=CapturingPubMedRetriever(),
            radiology=EmptyCoreRadiologyRetriever(),
            corpus=EmptyCoreCorpusRetriever(),
        ),
    )

    assert result.structured["case"]["procedure_family"]["value"] == (
        "posterior_fossa_chiari"
    )
    assert result.structured["case"]["degraded"] is True
    assert result.structured["profile"]["name"] == "posterior_fossa"
    assert result.structured["profile"]["matched_term"] == "chiari malformation"
    assert result.structured["profile"]["source"] == "word"

    queries = [query for query, _ in pubmed_calls]
    combined_queries = "\n".join(queries)
    assert queries == [
        result.structured["retrieval"]["pubmed_queries"][index]["query"]
        for index in range(5)
    ]
    assert queries[1] == "Chiari outcomes"
    assert queries[2] == "Chiari surgical technique approach"
    assert queries[3] == "Chiari complications adverse"
    assert queries[4] == "Chiari"
    assert "Chiari decompression suboccipital craniectomy C1 laminectomy" not in combined_queries
    assert "duraplasty arachnoid tonsillar reduction technique" not in combined_queries


@pytest.mark.asyncio
async def test_core_builder_respects_explicit_profile_hint_but_uses_family_queries():
    pubmed_calls = []

    class CapturingPubMedRetriever:
        async def retrieve(
            self,
            query,
            *,
            max_results=10,
            filter_type=None,
            include_abstracts=True,
        ):
            pubmed_calls.append((query, filter_type))
            return []

    result = await build_core_case_plan(
        BuildCasePlanRequest(
            case_input=(
                "suboccipital craniectomy and C1 laminectomy for Chiari I "
                "malformation with syringomyelia"
            ),
            profile_hint="vascular",
            max_per_category=1,
        ),
        retrievers=CoreRetrieverSet(
            pubmed=CapturingPubMedRetriever(),
            radiology=EmptyCoreRadiologyRetriever(),
            corpus=EmptyCoreCorpusRetriever(),
        ),
    )

    assert result.structured["case"]["procedure_family"]["value"] == (
        "posterior_fossa_chiari"
    )
    assert result.structured["profile"]["name"] == "vascular"
    assert result.structured["profile"]["source"] == "hint"

    queries = [query for query, _ in pubmed_calls]
    assert queries == [
        result.structured["retrieval"]["pubmed_queries"][index]["query"]
        for index in range(5)
    ]
    combined_queries = "\n".join(queries)
    assert "Chiari decompression suboccipital craniectomy C1 laminectomy" in combined_queries
    assert "duraplasty arachnoid tonsillar reduction technique" in combined_queries
    assert queries[1] == (
        "Chiari I malformation syringomyelia posterior fossa decompression "
        "outcomes duraplasty bone only"
    )
    assert queries[2] != (
        "suboccipital craniectomy and C1 laminectomy for Chiari I "
        "malformation with syringomyelia surgical technique approach"
    )


@pytest.mark.asyncio
async def test_core_builder_attaches_surgical_usefulness_score_and_sorts_pubmed_axis():
    pubmed_calls = 0

    class FakePubMedRetriever:
        async def retrieve(
            self,
            query,
            *,
            max_results=10,
            filter_type=None,
            include_abstracts=True,
        ):
            nonlocal pubmed_calls
            pubmed_calls += 1
            if pubmed_calls > 1:
                return []
            return [
                EvidenceRecord(
                    id="generic",
                    source="pubmed",
                    title="Cervical radiculopathy outcomes and background",
                    text="A generic review of symptoms and nonoperative treatment.",
                ),
                EvidenceRecord(
                    id="exact",
                    source="pubmed",
                    title="Anterior cervical discectomy and fusion surgical anatomy",
                    text=(
                        "Technical note on anterior cervical exposure, decompression, "
                        "cage, and plate placement."
                    ),
                ),
            ]

    result = await build_core_case_plan(
        BuildCasePlanRequest(
            case_input=(
                "C5-6 anterior cervical discectomy and fusion for right C6 "
                "radiculopathy from foraminal disc osteophyte complex"
            ),
            max_per_category=2,
        ),
        retrievers=CoreRetrieverSet(
            pubmed=FakePubMedRetriever(),
            radiology=EmptyCoreRadiologyRetriever(),
            corpus=EmptyCoreCorpusRetriever(),
        ),
    )

    assert [record.id for record in result.evidence[:2]] == ["exact", "generic"]
    assert all(
        "surgical_usefulness_score" in record.metadata
        and "score_reasons" in record.metadata
        for record in result.evidence[:2]
    )
    assert (
        result.evidence[0].metadata["surgical_usefulness_score"]
        > result.evidence[1].metadata["surgical_usefulness_score"]
    )


@pytest.mark.asyncio
async def test_core_builder_writes_thrombectomy_specific_dossier_without_open_surgery_scaffold(tmp_path):
    output_dir = tmp_path / "right-m1-thrombectomy"

    result = await build_core_case_plan(
        BuildCasePlanRequest(
            case_input="mechanical thrombectomy for acute ischemic stroke due to right M1 MCA occlusion",
            output_dir=output_dir,
            max_per_category=1,
        ),
        retrievers=EMPTY_RETRIEVERS,
    )

    assert result.structured["procedure_family"]["id"] == "endovascular_thrombectomy"
    caseprep_yaml = (output_dir / "caseprep.yaml").read_text(encoding="utf-8").casefold()
    assert "planned_procedure: \"mechanical thrombectomy\"" in caseprep_yaml
    assert "laterality: \"right\"" in caseprep_yaml
    assert "reperfuse right m1 mca occlusion" in caseprep_yaml
    assert (output_dir / "00-morning-of-case.md").exists()

    readme = (output_dir / "README.md").read_text(encoding="utf-8").casefold()
    for term in (
        "acute ischemic stroke",
        "right m1 mca occlusion",
        "mechanical thrombectomy",
        "00-morning-of-case.md",
    ):
        assert term in readme
    assert "planned procedure: `needs input`" not in readme
    assert "right right m1" not in readme

    morning = (output_dir / "00-morning-of-case.md").read_text(encoding="utf-8").casefold()
    for term in (
        "diagnosis / target / procedure",
        "acute ischemic stroke",
        "right m1 mca occlusion",
        "mechanical thrombectomy",
        "go / no-go missing facts",
        "lkw/time window",
        "nihss/disabling deficit",
        "aspects/core",
        "hemorrhage exclusion",
        "thrombolytic status",
        "baseline mrs/goals of care",
        "imaging checklist",
        "ncct",
        "cta head/neck",
        "ctp",
        "tandem cervical lesion",
        "access / device plan",
        "femoral or radial",
        "direct carotid",
        "guide catheter or bgc",
        "dac",
        "first-pass plan",
        "switch / stop criteria",
        "rescue plan",
        "perforation",
        "dissection",
        "vasospasm",
        "distal embolus",
        "icad/re-occlusion",
        "access bleed",
        "sich/malignant edema",
        "postop plan",
        "bp framework",
        "ct timing",
        "antithrombotics",
        "attending questions / preferences",
    ):
        assert term in morning
    assert "right right m1" not in morning

    rendered_markdown = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(output_dir.glob("*.md"))
    ).casefold()
    forbidden = (
        "incision",
        "levels",
        "subtotal resection",
        "antibiotic plan and redosing interval",
    )
    for term in forbidden:
        assert term not in rendered_markdown

    summary = (output_dir / "01-case-summary.md").read_text(encoding="utf-8").casefold()
    assert "planned procedure: mechanical thrombectomy" in summary
    assert "laterality: right" in summary
    assert "operative objective: reperfuse right m1 mca occlusion" in summary
    assert "planned procedure: `needs input`" not in summary
    assert "laterality: `needs input`" not in summary
    assert "right right m1" not in summary

    anatomy = (output_dir / "03-anatomy-at-risk.md").read_text(encoding="utf-8").casefold()
    for term in (
        "ica terminus",
        "m1",
        "lenticulostriate perforators",
        "early frontal",
        "temporal m1 branches",
        "m2 bifurcation/trifurcation",
        "tandem/cervical carotid",
        "arch/access anatomy",
    ):
        assert term in anatomy
    assert "deep perforator/internal capsule/brainstem risk" not in anatomy
    assert "left neglect/extinction" in anatomy
    assert "aphasia is not expected unless" in anatomy

    operative = (output_dir / "04-operative-plan.md").read_text(encoding="utf-8").casefold()
    for term in (
        "femoral vs radial access",
        "direct carotid access",
        "sheath",
        "balloon-guide catheter",
        "bgc",
        "dac",
        "distal access/aspiration catheter",
        "aspiration-first",
        "stent retriever",
        "combined/solumbra",
        "clot face",
        "avoid wedging",
        "roadmap",
        "cross clot",
        "microcatheter injection",
        "safe m2 segment",
        "flow arrest",
        "pass strategy",
        "after each pass",
        "stop/switch criteria",
        "mtici",
        "final run checklist",
        "structured thrombectomy decision tables",
        "eligibility / go-no-go",
        "access selection",
        "first-pass technique",
        "stop / switch / rescue",
        "post-reperfusion management",
    ):
        assert term in operative
    assert "right right m1" not in operative

    risk = (output_dir / "05-risk-and-rescue.md").read_text(encoding="utf-8").casefold()
    for term in (
        "perforation / sah / extravasation",
        "dissection",
        "vasospasm",
        "embolus to new territory",
        "distal emboli",
        "failed recanalization",
        "re-occlusion",
        "access-site hemorrhage",
        "symptomatic ich",
        "malignant edema",
    ):
        assert term in risk

    postop = (output_dir / "06-postop-plan.md").read_text(encoding="utf-8").casefold()
    for term in (
        "bp target",
        "avoid hypotension",
        "<=185/110",
        "<=220/120",
        "tighter sbp target",
        "incomplete/failed reperfusion",
        "reperfusion result",
        "hemorrhage",
        "extravasation",
        "tpa/tnk status",
        "neuro checks",
        "ct at protocol timing",
        "24 hours after iv tpa/tnk",
        "antiplatelet/anticoagulation timing",
        "access-site",
        "hemorrhagic transformation",
        "hemicraniectomy",
    ):
        assert term in postop

    evidence = (output_dir / "07-evidence.md").read_text(encoding="utf-8").casefold()
    for term in (
        "thrombectomy evidence bottom line",
        "standard-of-care",
        "mr clean",
        "escape",
        "extend-ia",
        "swift prime",
        "revascat",
        "hermes collaboration/meta-analysis",
        "dawn",
        "defuse 3",
        "select2",
        "angel-aspect",
        "rescue-japan limit",
        "tension/laste",
        "aha/asa or eso/esmint",
        "landmark/guideline targets to verify",
        "do not fake citations",
        "m2-only",
        "ai-detection",
        "rare-anomaly",
        "historical-vignette",
        "should not dominate routine m1 evt conclusions",
    ):
        assert term in evidence

    questions = (output_dir / "09-open-questions.md").read_text(encoding="utf-8").casefold()
    for term in (
        "lkw",
        "nihss",
        "aspects",
        "core volume",
        "right m1 occlusion vs ica terminus",
        "tandem/cervical carotid",
        "tpa/tnk status",
        "coagulopathy",
        "baseline mrs",
        "access concerns",
        "anesthesia plan and bp plan",
    ):
        assert term in questions


@pytest.mark.asyncio
async def test_thrombectomy_imaging_review_and_evt_eligibility_frame_are_specific(tmp_path):
    output_dir = tmp_path / "right-m1-thrombectomy-imaging"

    await build_core_case_plan(
        BuildCasePlanRequest(
            case_input="mechanical thrombectomy for acute ischemic stroke due to right M1 MCA occlusion",
            output_dir=output_dir,
            max_per_category=1,
        ),
        retrievers=EMPTY_RETRIEVERS,
    )

    imaging = (output_dir / "02-imaging-review.md").read_text(encoding="utf-8").casefold()
    assert "thrombectomy imaging review" in imaging
    for term in (
        "ncct hemorrhage exclusion",
        "aspects",
        "cta occlusion site",
        "right m1 vs ica terminus",
        "m2 extension",
        "tandem cervical ica lesion",
        "collateral status",
        "ctp/core-penumbra",
        "late/unknown window",
        "arch/cervical access anatomy",
        "suspected icad/dissection",
        "incomplete/needs input",
    ):
        assert term in imaging
    assert "review available studies" not in imaging

    summary = (output_dir / "01-case-summary.md").read_text(encoding="utf-8").casefold()
    for term in (
        "evt eligibility / decision-boundary frame",
        "last-known-well/time window",
        "nihss/disabling deficit",
        "baseline mrs",
        "iv tpa/tnk eligibility/status",
        "early vs late window",
        "large core considerations",
        "low-nihss lvo controversy",
        "medical-management/no-evt boundaries",
        "incomplete/need input",
        "do not invent values",
    ):
        assert term in summary


@pytest.mark.asyncio
async def test_thrombectomy_left_m1_defaults_do_not_claim_right_target(tmp_path):
    output_dir = tmp_path / "left-m1-thrombectomy"

    await build_core_case_plan(
        BuildCasePlanRequest(
            case_input="mechanical thrombectomy for acute ischemic stroke due to left M1 MCA occlusion",
            output_dir=output_dir,
            max_per_category=1,
        ),
        retrievers=EMPTY_RETRIEVERS,
    )

    rendered = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(output_dir.glob("*.md"))
    ).casefold()

    assert "left m1" in rendered
    assert "left mca territory" in rendered
    assert "right m1" not in rendered
    assert "right mca" not in rendered
    assert "right anterior circulation" not in rendered


@pytest.mark.asyncio
async def test_thrombectomy_basilar_defaults_do_not_use_m1_mca_or_right_anterior_scaffold(tmp_path):
    output_dir = tmp_path / "basilar-thrombectomy"

    await build_core_case_plan(
        BuildCasePlanRequest(
            case_input="mechanical thrombectomy for basilar artery occlusion acute ischemic stroke",
            output_dir=output_dir,
            max_per_category=1,
        ),
        retrievers=EMPTY_RETRIEVERS,
    )

    rendered = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(output_dir.glob("*.md"))
    ).casefold()

    assert "basilar artery occlusion" in rendered
    assert "posterior circulation" in rendered
    assert "vertebral-basilar" in rendered
    for unsafe in ("right m1", " m1 ", "m1/m2", "mca territory", "malignant mca", "right anterior circulation"):
        assert unsafe not in rendered


@pytest.mark.asyncio
async def test_thrombectomy_unspecified_defaults_use_neutral_target_vessel_language(tmp_path):
    output_dir = tmp_path / "unspecified-thrombectomy"

    await build_core_case_plan(
        BuildCasePlanRequest(
            case_input="mechanical thrombectomy for acute ischemic stroke",
            output_dir=output_dir,
            max_per_category=1,
        ),
        retrievers=EMPTY_RETRIEVERS,
    )

    rendered = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(output_dir.glob("*.md"))
    ).casefold()

    assert "target lvo" in rendered
    assert "target vessel" in rendered
    assert "affected territory" in rendered
    assert "access/occlusion anatomy needs input" in rendered
    assert "occlusion location" in rendered
    assert "right m1" not in rendered
    assert "right anterior circulation" not in rendered


class EvidencePackAwarePubMedRetriever:
    def __init__(self, *, missing_pmids: set[str] | None = None, generic_records=None):
        self.missing_pmids = missing_pmids or set()
        self.generic_records = generic_records or []
        self.calls: list[str] = []

    async def retrieve(
        self,
        query,
        *,
        max_results=10,
        filter_type=None,
        include_abstracts=True,
    ):
        self.calls.append(query)
        pack_records = {
            "25517348": EvidenceRecord(
                id="pmid-25517348",
                source="pubmed",
                title="A Randomized Trial of Intraarterial Treatment for Acute Ischemic Stroke",
                text="MR CLEAN thrombectomy trial.",
                metadata={"pmid": "25517348", "doi": "10.1056/NEJMoa1411587"},
            ),
            "25671798": EvidenceRecord(
                id="pmid-25671798",
                source="pubmed",
                title="Randomized assessment of rapid endovascular treatment of ischemic stroke",
                text="ESCAPE thrombectomy trial.",
                metadata={"pmid": "25671798", "doi": "10.1056/NEJMoa1414905"},
            ),
        }
        for pmid, record in pack_records.items():
            if pmid in query:
                return [] if pmid in self.missing_pmids else [record]
        if "10.1056/NEJMoa1414905" in query or "ESCAPE" in query:
            return []
        if query.startswith("10.") or "[doi]" in query or "[PMID]" in query:
            return []
        return list(self.generic_records)


@pytest.mark.asyncio
async def test_core_builder_evidence_pack_retrieved_before_generic_records_and_tracks_missing():
    generic = EvidenceRecord(
        id="pmid-generic",
        source="pubmed",
        title="Generic mechanical thrombectomy technique review",
        text="Technique overview for stroke thrombectomy.",
        metadata={"pmid": "999"},
    )
    pubmed = EvidencePackAwarePubMedRetriever(
        missing_pmids={"25671798"},
        generic_records=[generic],
    )

    result = await build_core_case_plan(
        BuildCasePlanRequest(
            case_input="mechanical thrombectomy for acute ischemic stroke due to right M1 MCA occlusion",
            max_per_category=1,
        ),
        retrievers=CoreRetrieverSet(
            pubmed=pubmed,
            radiology=EmptyCoreRadiologyRetriever(),
            corpus=EmptyCoreCorpusRetriever(),
        ),
    )

    assert result.evidence[0].id == "pmid-25517348"
    assert result.evidence[0].metadata["evidence_pack_id"] == "anterior_circulation_lvo_m1"
    assert result.evidence[0].metadata["pack_item_id"] == "mr_clean"
    assert result.evidence[0].metadata["source_tier"] == "practice-changing RCT"
    assert result.evidence[0].metadata["verification"] == "retrieved"
    assert any(record.id == "pmid-generic" for record in result.evidence[1:])

    coverage = result.structured["retrieval"]["evidence_pack"]
    assert coverage["id"] == "anterior_circulation_lvo_m1"
    assert any(item["pack_item_id"] == "mr_clean" for item in coverage["retrieved"])
    assert any(item["pack_item_id"] == "escape" for item in coverage["missing"])
    assert not any(
        record.id == "pmid-25671798" or record.metadata.get("pack_item_id") == "escape"
        for record in result.evidence
    )


@pytest.mark.asyncio
async def test_core_builder_marks_fallback_title_pack_hits_as_partial_not_exactly_retrieved():
    fallback_record = EvidenceRecord(
        id="title-only-mr-clean",
        source="pubmed",
        title="A Randomized Trial of Intraarterial Treatment for Acute Ischemic Stroke",
        text="Title-only MR CLEAN fallback result without PMID or DOI metadata.",
    )

    class FallbackOnlyPubMedRetriever:
        async def retrieve(
            self,
            query,
            *,
            max_results=10,
            filter_type=None,
            include_abstracts=True,
        ):
            if query == "MR CLEAN randomized trial intraarterial treatment acute ischemic stroke thrombectomy":
                return [fallback_record]
            return []

    result = await build_core_case_plan(
        BuildCasePlanRequest(
            case_input="mechanical thrombectomy for acute ischemic stroke due to right M1 MCA occlusion",
            max_per_category=1,
        ),
        retrievers=CoreRetrieverSet(
            pubmed=FallbackOnlyPubMedRetriever(),
            radiology=EmptyCoreRadiologyRetriever(),
            corpus=EmptyCoreCorpusRetriever(),
        ),
    )

    coverage = result.structured["retrieval"]["evidence_pack"]
    assert not any(item["pack_item_id"] == "mr_clean" for item in coverage["retrieved"])
    assert any(item["pack_item_id"] == "mr_clean" for item in coverage["partial"])

    tagged = next(record for record in result.evidence if record.id == "title-only-mr-clean")
    assert tagged.metadata["pack_item_id"] == "mr_clean"
    assert tagged.metadata["verification"] == "partial"


def test_dedupe_evidence_prefers_pack_tagged_records_by_pmid_doi_and_title():
    generic_by_pmid = EvidenceRecord(
        id="generic-pmid",
        source="pubmed",
        title="MR CLEAN duplicate",
        metadata={"pmid": "25517348"},
    )
    pack_by_pmid = EvidenceRecord(
        id="pmid-25517348",
        source="pubmed",
        title="MR CLEAN duplicate",
        metadata={"pmid": "25517348", "evidence_pack_id": "anterior_circulation_lvo_m1"},
    )
    by_doi = EvidenceRecord(
        id="generic-doi",
        source="pubmed",
        title="DAWN duplicate",
        metadata={"doi": "10.1056/NEJMoa1706442"},
    )
    pack_by_doi = EvidenceRecord(
        id="pmid-29129157",
        source="pubmed",
        title="DAWN duplicate",
        metadata={"doi": "10.1056/NEJMoa1706442", "evidence_pack_id": "anterior_circulation_lvo_m1"},
    )
    by_title = EvidenceRecord(id="title-1", source="pubmed", title="  Device Technique Review!  ")
    title_dup = EvidenceRecord(id="title-2", source="corpus", title="Device technique review")

    deduped = dedupe_evidence([
        generic_by_pmid,
        pack_by_pmid,
        by_doi,
        pack_by_doi,
        by_title,
        title_dup,
    ])

    assert [record.id for record in deduped] == [
        "pmid-25517348",
        "pmid-29129157",
        "title-1",
    ]


def test_dedupe_evidence_learns_identity_keys_from_nonpreferred_duplicates():
    pack_by_title = EvidenceRecord(
        id="old-pack",
        source="pubmed",
        title="Shared thrombectomy source",
        metadata={"evidence_pack_id": "anterior_circulation_lvo_m1"},
    )
    generic_same_title_with_doi = EvidenceRecord(
        id="generic-title-doi",
        source="pubmed",
        title="Shared thrombectomy source",
        metadata={"doi": "10.5555/shared"},
    )
    generic_same_doi_different_title = EvidenceRecord(
        id="generic-doi",
        source="pubmed",
        title="Different title for same source",
        metadata={"doi": "10.5555/shared"},
    )

    deduped = dedupe_evidence([
        pack_by_title,
        generic_same_title_with_doi,
        generic_same_doi_different_title,
    ])

    assert [record.id for record in deduped] == ["old-pack"]


@pytest.mark.asyncio
async def test_core_builder_quarantines_low_applicability_records_and_filters_clinical_synthesis():
    high_tier = EvidenceRecord(
        id="pmid-25517348",
        source="pubmed",
        title="A Randomized Trial of Intraarterial Treatment for Acute Ischemic Stroke",
        text="MR CLEAN thrombectomy trial.",
        metadata={"pmid": "25517348", "doi": "10.1056/NEJMoa1411587"},
    )
    ai_workflow = EvidenceRecord(
        id="pmid-ai",
        source="pubmed",
        title="Artificial intelligence workflow triage for stroke thrombectomy",
        text="Workflow and detection software performance only.",
    )
    m2_only = EvidenceRecord(
        id="pmid-m2",
        source="pubmed",
        title="M2-only thrombectomy outcomes after distal MCA occlusion",
        text="Distal M2-only cohort.",
    )

    class MixedPubMedRetriever:
        async def retrieve(
            self,
            query,
            *,
            max_results=10,
            filter_type=None,
            include_abstracts=True,
        ):
            if "25517348" in query:
                return [high_tier]
            if "[PMID]" in query or "[doi]" in query or query.startswith("10."):
                return []
            if "mechanical thrombectomy technique" in query:
                return [ai_workflow, m2_only]
            return []

    result = await build_core_case_plan(
        BuildCasePlanRequest(
            case_input="mechanical thrombectomy for acute ischemic stroke due to right M1 MCA occlusion",
            max_per_category=2,
        ),
        retrievers=CoreRetrieverSet(
            pubmed=MixedPubMedRetriever(),
            radiology=EmptyCoreRadiologyRetriever(),
            corpus=EmptyCoreCorpusRetriever(),
        ),
    )

    records = {record.id: record for record in result.evidence}
    assert records["pmid-25517348"].metadata["clinical_include"] is True
    assert records["pmid-ai"].metadata["clinical_include"] is False
    assert "AI/workflow" in records["pmid-ai"].metadata["quarantine_reason"]
    assert records["pmid-m2"].metadata["clinical_include"] is False
    assert "M2-only" in records["pmid-m2"].metadata["quarantine_reason"]

    section_text = "\n".join(section["body"] for section in result.structured["sections"])
    assert "A Randomized Trial of Intraarterial Treatment" in section_text
    assert "Artificial intelligence workflow" not in section_text
    assert "M2-only thrombectomy" not in section_text
    assert {item["id"] for item in result.structured["retrieval"]["quarantined_sources"]} == {
        "pmid-ai",
        "pmid-m2",
    }
