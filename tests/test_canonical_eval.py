from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import caseprep.evaluation.rubric as rubric
from caseprep.core import BuildCasePlanRequest, EvidenceRecord
from caseprep.core.builder import CoreRetrieverSet, build_core_case_plan
from caseprep.evaluation import (
    CanonicalCase,
    all_canonical_cases,
    degraded_cases,
    evaluate_case_output,
    full_canonical_cases,
)
from caseprep.evaluation.canonical_cases import ACDF_C5_6, DEGRADED_CHIARI
from caseprep.evaluation.rubric import MAJOR_MARKDOWN_FILES
from caseprep.evaluation.rubric import _load_schema, _minimal_yaml_parse


def _concept_fixture_text(canonical_case: CanonicalCase) -> str:
    concepts = "; ".join(canonical_case.required_concepts)
    return (
        f"Fixture evidence for {canonical_case.expected_family}: {concepts}. "
        "This deterministic source-backed note supports the operative dossier."
    )


class CanonicalFixturePubMedRetriever:
    """Stable in-test PubMed retriever keyed by canonical input text."""

    def __init__(self, canonical_case: CanonicalCase):
        self.canonical_case = canonical_case
        self.calls = 0

    async def retrieve(
        self,
        query,
        *,
        max_results=10,
        filter_type=None,
        include_abstracts=True,
    ):
        self.calls += 1
        axis = filter_type or "unfiltered"
        return [
            EvidenceRecord(
                id=f"fixture-{self.canonical_case.id}-{self.calls}",
                source="pubmed",
                title=f"{self.canonical_case.expected_family} {axis} fixture source",
                text=_concept_fixture_text(self.canonical_case),
                metadata={
                    "pubdate": "2026",
                    "pub_types": ["Review"],
                    "fixture": True,
                },
            )
        ]


class CanonicalFixtureRadiologyRetriever:
    async def retrieve(self, query, *, max_results=5, modality=None):
        return [
            EvidenceRecord(
                id="fixture-radiology",
                source="openi",
                title="Fixture radiology image review",
                text="Imaging fixture record for deterministic smoke testing.",
                metadata={"fixture": True},
            )
        ]


class CanonicalFixtureCorpusRetriever:
    def __init__(self, canonical_case: CanonicalCase):
        self.canonical_case = canonical_case

    def retrieve(self, fts_query, *, subdomain=None, top_n=8):
        return [
            EvidenceRecord(
                id=f"fixture-corpus-{self.canonical_case.id}",
                source="corpus",
                title="Fixture corpus synthesis source",
                text=_concept_fixture_text(self.canonical_case),
                metadata={"year": "2026", "evidence_tier": "fixture", "fixture": True},
            )
        ]


def _canonical_fixture_retrievers(canonical_case: CanonicalCase) -> CoreRetrieverSet:
    return CoreRetrieverSet(
        pubmed=CanonicalFixturePubMedRetriever(canonical_case),
        radiology=CanonicalFixtureRadiologyRetriever(),
        corpus=CanonicalFixtureCorpusRetriever(canonical_case),
    )


_CASE_TOKEN_STOPWORDS = {
    "and",
    "for",
    "from",
    "the",
    "with",
    "without",
    "right",
    "left",
    "case",
    "patient",
    "procedure",
    "review",
    "plan",
    "operative",
    "postop",
    "imaging",
    "risk",
    "evidence",
}

_FIXTURE_EVIDENCE_MARKERS = (
    "fixture evidence",
    "fixture radiology",
    "fixture corpus",
    "fixture source",
    "source-backed note",
)


def _section_specific_terms(canonical_case: CanonicalCase) -> tuple[str, ...]:
    """Deterministic terms that distinguish canonical output from boilerplate."""

    terms: set[str] = set()
    normalized_input = rubric._normalize(canonical_case.input_text)
    for token in normalized_input.split():
        if token in _CASE_TOKEN_STOPWORDS:
            continue
        if len(token) >= 4 or any(char.isdigit() for char in token):
            terms.add(token)

    if canonical_case.expected_family:
        terms.add(canonical_case.expected_family.casefold())
        terms.update(part for part in canonical_case.expected_family.casefold().split("_") if len(part) >= 4)

    for concept in canonical_case.required_concepts:
        aliases = rubric._CONCEPT_ALIASES.get(concept, ()) + (concept,)
        for alias in aliases:
            normalized_alias = rubric._normalize(alias)
            if normalized_alias:
                terms.add(normalized_alias)
            for part in normalized_alias.split():
                if len(part) >= 4 and part not in _CASE_TOKEN_STOPWORDS:
                    terms.add(part)

    return tuple(sorted(terms))


def _assert_major_sections_not_blank(output_dir: Path, canonical_case: CanonicalCase) -> None:
    specific_terms = _section_specific_terms(canonical_case)
    assert specific_terms or canonical_case.degraded, "canonical smoke check has no case-specific terms"
    for filename in MAJOR_MARKDOWN_FILES:
        path = output_dir / filename
        assert path.exists(), f"missing major markdown file: {filename}"
        text = path.read_text(encoding="utf-8").strip()
        assert text, f"blank major markdown file: {filename}"
        assert not any(pattern.search(text) for pattern in rubric.PLACEHOLDER_PATTERNS), (
            f"generic placeholder remains: {filename}"
        )

        # README.md is the dossier index/status page, not a clinical content
        # section. Keep it covered by basic existence/non-placeholder checks, but
        # do not require case/evidence-derived clinical terms in its body.
        if filename == "README.md":
            continue

        non_heading_text = "\n".join(
            line for line in text.splitlines() if not line.lstrip().startswith("#")
        )
        normalized_non_heading_text = rubric._normalize(non_heading_text)
        has_case_term = any(
            re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", normalized_non_heading_text)
            for term in specific_terms
        )
        # Fixture retrievers intentionally prove deterministic propagation and
        # rendering, not independent clinical synthesis quality. Prefer clinical
        # case terms in section bodies; fixture markers remain a narrow fallback
        # for source/rendering smoke coverage.
        has_fixture_marker = any(marker in non_heading_text.casefold() for marker in _FIXTURE_EVIDENCE_MARKERS)
        has_visible_unresolved_fields = "needs input" in non_heading_text.casefold()
        unresolved_template_scaffold = filename in {
            "02-imaging-review.md",
            "06-postop-plan.md",
        } and has_visible_unresolved_fields
        degraded_missing_fact_scaffold = canonical_case.degraded and has_visible_unresolved_fields
        assert has_case_term or has_fixture_marker or unresolved_template_scaffold or degraded_missing_fact_scaffold, (
            f"generic major markdown file lacks case/evidence-derived content: {filename}"
        )


def _write_caseprep_yaml(
    output_dir: Path,
    *,
    family: str | None,
    degraded: bool,
    missing_facts: list[str] | None = None,
    key_sources: list[dict[str, str]] | None = None,
) -> None:
    schema = {
        "procedure_family": {"id": family} if family else None,
        "structured_case": {
            "procedure_family": {"value": family} if family else {"value": None},
            "degraded": degraded,
            "missing_critical_facts": missing_facts or [],
        },
        "case": {
            "evidence": {
                "key_sources": key_sources or [],
            }
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "caseprep.yaml").write_text(json.dumps(schema), encoding="utf-8")


def _write_major_markdown(output_dir: Path, *, family: str | None, text: str, degraded: bool = False) -> None:
    degradation_line = "- Degradation status: degraded/generic case summary" if degraded else "- Degradation status: not degraded"
    (output_dir / "01-case-summary.md").write_text(
        f"""# Case Summary

## Parsed Case Summary

- Procedure family: `{family or ''}`
- Missing critical facts:
- none identified
{degradation_line}

{text}
""",
        encoding="utf-8",
    )
    (output_dir / "03-anatomy-at-risk.md").write_text(text, encoding="utf-8")
    (output_dir / "04-operative-plan.md").write_text(text, encoding="utf-8")
    (output_dir / "05-risk-and-rescue.md").write_text(text, encoding="utf-8")
    (output_dir / "07-evidence.md").write_text(
        """# Evidence

## Key Sources

| ID | Source | Year | Evidence Type | Relevance | Verification |
|---|---|---:|---|---|---|
| PMID:1 | Useful source | 2024 | cohort | operative | cited |
""",
        encoding="utf-8",
    )


def test_canonical_case_sets_have_four_full_and_five_degraded_cases() -> None:
    full_cases = full_canonical_cases()
    weak_cases = degraded_cases()

    assert len(full_cases) == 4
    assert {case.expected_family for case in full_cases} == {
        "spine_acdf",
        "tumor_convexity_meningioma",
        "posterior_fossa_chiari",
        "endovascular_thrombectomy",
    }
    assert len(weak_cases) == 5
    assert all(case.degraded for case in weak_cases)
    assert all(case.expected_family is None for case in weak_cases)
    assert len(all_canonical_cases()) == 9


@pytest.mark.asyncio
@pytest.mark.parametrize("canonical_case", full_canonical_cases(), ids=lambda case: case.id)
async def test_full_canonical_cases_build_and_pass_eval_with_fixture_retrievers(
    tmp_path: Path,
    canonical_case: CanonicalCase,
) -> None:
    output_dir = tmp_path / canonical_case.id

    result = await build_core_case_plan(
        BuildCasePlanRequest(
            case_input=canonical_case.input_text,
            output_dir=output_dir,
            max_per_category=1,
        ),
        retrievers=_canonical_fixture_retrievers(canonical_case),
    )
    report = evaluate_case_output(output_dir, canonical_case)

    assert result.mode == "core"
    assert result.artifacts
    assert result.structured["procedure_family"]["id"] == canonical_case.expected_family
    _assert_major_sections_not_blank(output_dir, canonical_case)
    assert report.passed is True, report
    assert report.missing_required_concepts == ()
    assert report.deterministic_failures == ()


@pytest.mark.asyncio
@pytest.mark.parametrize("canonical_case", degraded_cases(), ids=lambda case: case.id)
async def test_degraded_cases_build_and_evaluate_as_degraded(
    tmp_path: Path,
    canonical_case: CanonicalCase,
) -> None:
    output_dir = tmp_path / canonical_case.id

    await build_core_case_plan(
        BuildCasePlanRequest(
            case_input=canonical_case.input_text,
            output_dir=output_dir,
            max_per_category=1,
        ),
        retrievers=CoreRetrieverSet(
            pubmed=CanonicalFixturePubMedRetriever(canonical_case),
            radiology=CanonicalFixtureRadiologyRetriever(),
            corpus=CanonicalFixtureCorpusRetriever(canonical_case),
        ),
    )
    report = evaluate_case_output(output_dir, canonical_case)

    _assert_major_sections_not_blank(output_dir, canonical_case)
    assert report.passed is True, report
    assert report.degradation_status == "degraded"
    assert report.deterministic_failures == ()


def test_major_section_smoke_rejects_generic_boilerplate(tmp_path: Path) -> None:
    output_dir = tmp_path / "generic-boilerplate"
    output_dir.mkdir()
    generic_text = """# Section

## Checklist

- Review available studies.
- Confirm operative plan with attending.
- Monitor for standard complications.
"""
    for filename in MAJOR_MARKDOWN_FILES:
        (output_dir / filename).write_text(generic_text, encoding="utf-8")

    with pytest.raises(AssertionError, match="lacks case/evidence-derived content"):
        _assert_major_sections_not_blank(output_dir, ACDF_C5_6)


def test_major_section_smoke_rejects_case_terms_only_in_headings(tmp_path: Path) -> None:
    output_dir = tmp_path / "heading-only-case-terms"
    output_dir.mkdir()
    heading_only_text = """# Operative Plan - C5-6 ACDF

## C5-6 Anterior Cervical Discectomy and Fusion

- Review available studies.
- Confirm operative plan with attending.
- Monitor for standard complications.
"""
    for filename in MAJOR_MARKDOWN_FILES:
        (output_dir / filename).write_text(heading_only_text, encoding="utf-8")

    with pytest.raises(AssertionError, match="lacks case/evidence-derived content"):
        _assert_major_sections_not_blank(output_dir, ACDF_C5_6)



def test_major_section_smoke_allows_readme_as_nonclinical_index(tmp_path: Path) -> None:
    output_dir = tmp_path / "readme-index"
    output_dir.mkdir()
    for filename in MAJOR_MARKDOWN_FILES:
        body = (
            "# CasePrep dossier\n\nGenerated files are listed below.\n"
            if filename == "README.md"
            else (
                "Anterior cervical exposure, discectomy, decompression, foraminal uncinate work, "
                "graft cage plate fixation, and dysphagia recurrent laryngeal nerve risk."
            )
        )
        (output_dir / filename).write_text(body, encoding="utf-8")

    _assert_major_sections_not_blank(output_dir, ACDF_C5_6)


def test_full_case_passes_with_family_concepts_evidence_and_missing_facts_section(tmp_path: Path) -> None:
    output_dir = tmp_path / "acdf"
    concept_text = "\n".join(f"- {concept}" for concept in ACDF_C5_6.required_concepts)
    _write_caseprep_yaml(
        output_dir,
        family=ACDF_C5_6.expected_family,
        degraded=False,
        missing_facts=[],
        key_sources=[{"id": "PMID:1", "title": "Useful source"}],
    )
    _write_major_markdown(output_dir, family=ACDF_C5_6.expected_family, text=concept_text)

    report = evaluate_case_output(output_dir, ACDF_C5_6)

    assert report.passed is True
    assert report.score == 100
    assert report.missing_required_concepts == ()
    assert report.deterministic_failures == ()
    assert report.degradation_status == "not degraded"


def test_degraded_case_requires_degraded_label_and_nonempty_missing_facts(tmp_path: Path) -> None:
    output_dir = tmp_path / "chiari"
    _write_caseprep_yaml(
        output_dir,
        family=None,
        degraded=True,
        missing_facts=["procedure", "approach"],
    )
    _write_major_markdown(
        output_dir,
        family=None,
        degraded=True,
        text="Generic Chiari topic only; missing procedure and approach are explicit.",
    )

    report = evaluate_case_output(output_dir, DEGRADED_CHIARI)

    assert report.passed is True
    assert report.degradation_status == "degraded"
    assert report.deterministic_failures == ()


def test_full_case_reports_deterministic_failures(tmp_path: Path) -> None:
    output_dir = tmp_path / "bad-acdf"
    _write_caseprep_yaml(
        output_dir,
        family="wrong_family",
        degraded=False,
        missing_facts=[],
        key_sources=[],
    )
    (output_dir / "01-case-summary.md").write_text(
        """# Case Summary

## Parsed Case Summary

- Procedure family: `wrong_family`
- Missing critical facts:
- none identified
- Degradation status: not degraded

TODO
""",
        encoding="utf-8",
    )
    (output_dir / "07-evidence.md").write_text(
        """# Evidence

| ID | Source | Year | Evidence Type | Relevance | Verification |
|---|---|---:|---|---|---|
| TODO | TODO |  |  |  |  |
""",
        encoding="utf-8",
    )

    report = evaluate_case_output(output_dir, ACDF_C5_6)

    assert report.passed is False
    assert "anterior cervical exposure" in report.missing_required_concepts
    assert any("parsed family mismatch" in failure for failure in report.deterministic_failures)
    assert any("evidence table is empty" in failure for failure in report.deterministic_failures)
    assert any("placeholder text remains" in failure for failure in report.deterministic_failures)


def test_degraded_case_reports_missing_degradation_and_missing_facts(tmp_path: Path) -> None:
    output_dir = tmp_path / "bad-degraded"
    _write_caseprep_yaml(output_dir, family=None, degraded=False, missing_facts=[])
    _write_major_markdown(output_dir, family=None, degraded=False, text="Bare topic without missing facts.")

    report = evaluate_case_output(output_dir, DEGRADED_CHIARI)

    assert report.passed is False
    assert "degraded case is not labeled degraded" in report.deterministic_failures
    assert "degraded case does not expose missing critical facts" in report.deterministic_failures


def test_alias_matching_accepts_alternative_concept_terms(tmp_path: Path) -> None:
    case = CanonicalCase(
        id="alias-smoke",
        input_text="alias smoke",
        expected_family="endovascular_thrombectomy",
        required_concepts=("TICI/mTICI", "femoral/radial access", "CSF leak"),
    )
    output_dir = tmp_path / "alias"
    _write_caseprep_yaml(
        output_dir,
        family="endovascular_thrombectomy",
        degraded=False,
        key_sources=[{"id": "PMID:1"}],
    )
    _write_major_markdown(
        output_dir,
        family="endovascular_thrombectomy",
        text="mTICI reperfusion via transfemoral approach; cerebrospinal fluid leak precautions.",
    )

    report = evaluate_case_output(output_dir, case)

    assert report.passed is True
    assert report.missing_required_concepts == ()


def test_allowed_unresolved_clinical_fields_do_not_fail_placeholder_check(tmp_path: Path) -> None:
    output_dir = tmp_path / "allowed-unresolved"
    concept_text = "\n".join(f"- {concept}" for concept in ACDF_C5_6.required_concepts)
    _write_caseprep_yaml(
        output_dir,
        family=ACDF_C5_6.expected_family,
        degraded=False,
        missing_facts=["MRI date needs clinician verification"],
        key_sources=[{"id": "PMID:1"}],
    )
    _write_major_markdown(
        output_dir,
        family=ACDF_C5_6.expected_family,
        text=f"Patient-specific laterality `needs input`; measurements `needs clinician verification`.\n{concept_text}",
    )

    report = evaluate_case_output(output_dir, ACDF_C5_6)

    assert report.passed is True
    assert not any("placeholder text remains" in failure for failure in report.deterministic_failures)


def test_minimal_yaml_parse_handles_nested_dicts_and_lists() -> None:
    parsed = _minimal_yaml_parse(
        """
procedure_family:
  id: spine_acdf
structured_case:
  procedure_family:
    value: spine_acdf
  degraded: false
  missing_critical_facts:
    - approach
    - levels
case:
  evidence:
    key_sources:
      - id: PMID:1
        title: Useful source
      - id: PMID:2
        title: Other source
sections:
  - id: anatomy
    title: Anatomy at risk
"""
    )

    assert parsed["procedure_family"]["id"] == "spine_acdf"
    assert parsed["structured_case"]["procedure_family"]["value"] == "spine_acdf"
    assert parsed["structured_case"]["degraded"] is False
    assert parsed["structured_case"]["missing_critical_facts"] == ["approach", "levels"]
    assert parsed["case"]["evidence"]["key_sources"][0]["id"] == "PMID:1"
    assert parsed["case"]["evidence"]["key_sources"][1]["title"] == "Other source"
    assert parsed["sections"] == [{"id": "anatomy", "title": "Anatomy at risk"}]


def test_minimal_yaml_parse_handles_project_bare_dash_list_items() -> None:
    parsed = _minimal_yaml_parse(
        """
case:
  evidence:
    key_sources:
      -
        id: S1
        title: Foo
        source: pubmed
      -
        id: S2
        title: Bar
structured_case:
  missing_critical_facts:
    -
      field: laterality
      reason: not stated
"""
    )

    key_sources = parsed["case"]["evidence"]["key_sources"]
    assert key_sources == [
        {"id": "S1", "title": "Foo", "source": "pubmed"},
        {"id": "S2", "title": "Bar"},
    ]
    assert parsed["structured_case"]["missing_critical_facts"] == [
        {"field": "laterality", "reason": "not stated"}
    ]


def test_load_schema_returns_empty_dict_for_malformed_yaml(tmp_path: Path) -> None:
    schema_path = tmp_path / "caseprep.yaml"
    schema_path.write_text("structured_case: [unterminated\n", encoding="utf-8")

    assert _load_schema(schema_path) == {}


def test_load_schema_returns_empty_dict_for_malformed_yaml_without_pyyaml(
    tmp_path: Path, monkeypatch
) -> None:
    schema_path = tmp_path / "caseprep.yaml"
    schema_path.write_text("structured_case: [unterminated\n", encoding="utf-8")

    monkeypatch.setattr(rubric, "yaml", None)

    assert rubric._load_schema(schema_path) == {}


def test_load_schema_returns_empty_dict_when_fallback_parser_raises(tmp_path: Path, monkeypatch) -> None:
    schema_path = tmp_path / "caseprep.yaml"
    schema_path.write_text("structured_case: [unterminated\n", encoding="utf-8")

    def raise_parse_error(text: str) -> dict[str, object]:
        raise ValueError("malformed fallback yaml")

    monkeypatch.setattr(rubric, "yaml", None)
    monkeypatch.setattr(rubric, "_minimal_yaml_parse", raise_parse_error)

    assert rubric._load_schema(schema_path) == {}
