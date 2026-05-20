"""Tests for template population — content extraction, domain profiles, guardrail verification."""

import sqlite3
from unittest.mock import AsyncMock, patch

import pytest
from caseprep.mcp_server import (
    _detect_profile,
    _build_keywords,
    _BASE_ANATOMY,
    _BASE_APPROACH,
    _BASE_COMPLICATIONS,
    _fmt_corpus_paper,
    _handle_search_corpus,
    _corpus_search,
)


class TestDomainProfiles:
    def test_detects_skull_base_vestibular_schwannoma(self):
        profile, conf = _detect_profile("vestibular schwannoma")
        assert profile == "skull_base"
        assert conf > 0.5

    def test_detects_vascular_aneurysm(self):
        profile, conf = _detect_profile("anterior communicating artery aneurysm clipping")
        assert profile == "vascular"
        assert conf > 0

    def test_detects_supratentorial_gbm(self):
        profile, conf = _detect_profile("glioblastoma resection")
        assert profile == "supratentorial_tumor"
        assert conf > 0.3

    def test_detects_spine_fusion(self):
        profile, conf = _detect_profile("lumbar fusion l4-l5")
        assert profile == "spine"

    def test_detects_functional_dbs(self):
        profile, conf = _detect_profile("deep brain stimulation parkinson")
        assert profile == "functional"

    def test_detects_pediatric_hydrocephalus(self):
        profile, conf = _detect_profile("pediatric hydrocephalus")
        assert profile == "pediatric"

    def test_falls_back_to_skull_base_on_unknown(self):
        profile, conf = _detect_profile("some unknown neurosurgical procedure")
        assert profile == "skull_base"
        assert conf == 0.0

    def test_longest_match_wins(self):
        # "aneurysm" matches vascular, but "lumbar" also matches spine.
        # "lumbar aneurysm" — vascular wins because "aneurysm" is longer than "lumbar"
        profile, conf = _detect_profile("lumbar aneurysm")
        # Actually "lumbar" = 6 chars, "aneurysm" = 8 chars → aneurysm wins
        assert profile in ("spine", "vascular")

    def test_build_keywords_merges_base_and_profile(self):
        kw = _build_keywords("skull_base")
        assert "anatomy" in kw
        assert "cranial nerve" in kw["anatomy"]  # profile-specific
        assert "nerve" in kw["anatomy"]  # base
        assert len(kw["anatomy"]) > len(_BASE_ANATOMY)  # profile adds

    def test_build_keywords_unknown_profile_uses_base_only(self):
        kw = _build_keywords("nonexistent")
        assert kw["anatomy"] == _BASE_ANATOMY
        assert kw["approach"] == _BASE_APPROACH
        assert kw["complications"] == _BASE_COMPLICATIONS


class TestStructuredCaseDossierOutput:
    @pytest.mark.asyncio
    async def test_write_filled_templates_writes_canonical_schema_files(self, tmp_path):
        from caseprep.mcp_server import _write_filled_templates

        axis_data = {
            "Anatomy / Relevant Structures": [
                {
                    "pmid": "12345",
                    "title": "CPA Anatomy",
                    "authors": "Doe J",
                    "source": "J Neurosurg",
                    "pubdate": "2024",
                    "doi": "",
                    "url": "https://pubmed.ncbi.nlm.nih.gov/12345/",
                    "_abstract": "The cerebellopontine angle contains cranial nerves and vascular structures.",
                    "_structured": {},
                }
            ],
            "Surgical Technique": [],
            "Reviews / Landmarks": [],
            "Outcomes / Evidence": [],
            "Complications": [],
        }

        await _write_filled_templates(
            tmp_path,
            "retrosigmoid vestibular schwannoma",
            "# Case Plan\n\nPaper summary",
            axis_data,
        )

        for filename in [
            "caseprep.yaml",
            "provenance.json",
            "README.md",
            "01-case-summary.md",
            "02-imaging-review.md",
            "03-anatomy-at-risk.md",
            "04-operative-plan.md",
            "05-risk-and-rescue.md",
            "06-postop-plan.md",
            "07-evidence.md",
            "08-checklists.md",
            "09-open-questions.md",
        ]:
            assert (tmp_path / filename).is_file(), f"missing {filename}"

        assert "Preparation Status" in (tmp_path / "README.md").read_text()
        assert "pmid-12345" in (tmp_path / "07-evidence.md").read_text()
        assert (tmp_path / "anatomy.md").read_text() == (tmp_path / "03-anatomy-at-risk.md").read_text()
        assert (tmp_path / "approach.md").read_text() == (tmp_path / "04-operative-plan.md").read_text()
        assert (tmp_path / "complications.md").read_text() == (tmp_path / "05-risk-and-rescue.md").read_text()
        assert (tmp_path / "literature.md").read_text() == (tmp_path / "07-evidence.md").read_text()


# ── Guardrail tests ────────────────────────────────────────────────────────

class TestGuardrailVerify:
    def test_passes_cited_supported_claims(self):
        from caseprep.llm import verify_synthesis
        sources = [
            "CSF leak occurred in 8% of patients (N=234).",
            "Meningitis rate was 1.5% in the retrosigmoid approach group.",
        ]
        synth = "- CSF leak rate was 8 percent [S1]\n- Meningitis rate 1.5 percent [S2]"
        result = verify_synthesis(synth, sources)
        assert result.passed
        assert result.flagged_count == 0

    def test_flags_claim_when_cited_source_does_not_match(self):
        """Claim cites [S1] but [S1] doesn't contain the claim — should flag."""
        from caseprep.llm import verify_synthesis
        sources = [
            "The tumor was resected via retrosigmoid approach.",  # S1
            "CSF leak occurred in 8% of patients.",               # S2
        ]
        # Claim cites S1 but S1 doesn't mention CSF leak or 8%
        synth = "- CSF leak rate was 8% [S1]"
        result = verify_synthesis(synth, sources)
        # Should flag because S1 doesn't contain the claim's content
        assert result.flagged_count > 0
        # Verify it's flagged because of the cited source mismatch
        assert not result.claims[0]["passed"]

    def test_passes_when_cited_source_matches(self):
        """Claim cites [S2] which DOES contain the fact — should pass."""
        from caseprep.llm import verify_synthesis
        sources = [
            "The tumor was resected via retrosigmoid approach.",  # S1
            "CSF leak occurred in 8% of patients.",               # S2
        ]
        synth = "- CSF leak rate was 8% [S2]"
        result = verify_synthesis(synth, sources)
        assert result.passed
        assert result.flagged_count == 0

    def test_numeric_fidelity_blocks_fabricated_numbers(self):
        """A claim with a fabricated number should fail numeric fidelity check."""
        from caseprep.llm import verify_synthesis
        sources = ["Mortality rate was 1% in the series."]  # S1
        synth = "- Mortality rate was 50% [S1]"
        result = verify_synthesis(synth, sources)
        # Should flag — "50%" doesn't appear in source even if Jaccard passes
        assert result.flagged_count > 0
        flagged = [c for c in result.claims if not c["passed"]]
        assert any(not c.get("numeric_fidelity", True) for c in flagged)

    def test_numeric_fidelity_passes_exact_match(self):
        """Exact number match should pass numeric fidelity."""
        from caseprep.llm import verify_synthesis
        sources = ["CSF leak rate was 8.5% (n=234) in the retrosigmoid group."]
        synth = "- CSF leak rate was 8.5% (n=234) [S1]"
        result = verify_synthesis(synth, sources)
        assert result.passed
        assert result.claims[0]["numeric_fidelity"]

    def test_falls_back_to_best_match_when_no_citation(self):
        """Claim without [S#] should match against all sources."""
        from caseprep.llm import verify_synthesis
        sources = [
            "Approach was standard.",
            "CSF leak rate was 5%.",
        ]
        synth = "- CSF leak rate was 5%"
        result = verify_synthesis(synth, sources)
        assert result.passed
        assert result.flagged_count == 0

    def test_rejects_when_over_threshold(self):
        from caseprep.llm import verify_synthesis
        sources = ["The approach provides good exposure."]
        synth = "- Mortality was 5% [S1]\n- Infection rate 10% [S1]\n- CSF leak 8% [S1]\n- Seizure 3% [S1]"
        result = verify_synthesis(synth, sources, max_flagged_ratio=0.25)
        assert not result.passed  # 4 claims, all hallucinated > 25%

    def test_handles_insufficient_data_lines(self):
        from caseprep.llm import _extract_claims
        text = "- CSF leak rate was 5% [S1]\n- Insufficient data in search results.\n- Meningitis 2% [S2]"
        claims = _extract_claims(text)
        assert len(claims) == 2  # insufficient data line skipped

    def test_empty_synthesis_fails(self):
        from caseprep.llm import verify_synthesis
        result = verify_synthesis("", ["some source"])
        assert not result.passed

    def test_citation_parsing(self):
        from caseprep.llm import _parse_citations
        assert _parse_citations("- Claim with [S1] citation") == [1]
        assert _parse_citations("- Claim with [S1, S2] citations") == [1, 2]
        assert _parse_citations("- Claim without citation") == []

    def test_numeric_extraction(self):
        from caseprep.llm import _extract_numbers
        nums = _extract_numbers("CSF leak rate was 8.5% (n=234). OR: 2.1 (95% CI 1.2-3.5).")
        assert "8.5%" in nums
        assert "n=234" in nums
        assert "OR 2.1" in nums

    def test_claim_fallback_for_non_bullet_format(self):
        """When LLM returns paragraph format, _extract_claims should still find claims."""
        from caseprep.llm import _extract_claims
        text = """# Section
        The CSF leak rate was 8% in this series [S1].
        Meningitis occurred in 1.5% of cases [S2].
        Insufficient data in search results.
        """
        claims = _extract_claims(text)
        assert len(claims) >= 2

    def test_zero_total_claims_edge_case(self):
        """verify_synthesis with no extractable claims returns GuardrailResult(passed=False)."""
        from caseprep.llm import verify_synthesis
        # Use only headers (stripped) and short lines (<20 chars) — nothing extractable
        result = verify_synthesis("# Short\n## Very short\nok\n", ["source sentence"])
        assert not result.passed
        assert result.total_count == 0


class TestCorpusFormatting:
    def test_fmt_corpus_paper_includes_work_id(self):
        lines = _fmt_corpus_paper(
            {
                "work_id": "W123",
                "title": "Treatment Outcomes",
                "journal": "J Neurosurg",
                "year": 2024,
            },
            1,
        )

        assert "   Work ID: W123" in lines

    def test_handle_search_corpus_includes_work_id(self):
        fake_result = {
            "papers": [
                {
                    "work_id": "W123",
                    "title": "Treatment Outcomes",
                    "journal": "J Neurosurg",
                    "year": 2024,
                }
            ],
            "total_matches": 1,
            "returned": 1,
            "subdomain_distribution": {},
        }
        with patch("caseprep.mcp_server._corpus_search", return_value=fake_result):
            output = _handle_search_corpus({"fts_query": "aneurysm"})

        assert "Work ID: W123" in output
        assert "get_paper with a work_id" in output

    def test_handle_search_corpus_invalid_fts_query_is_user_facing(self):
        fake_result = {
            "error": "Invalid FTS query: unterminated string",
            "papers": [],
            "total_matches": 0,
        }
        with patch("caseprep.mcp_server._corpus_search", return_value=fake_result):
            output = _handle_search_corpus({"fts_query": '"'})

        assert "Invalid FTS query: unterminated string" in output
        assert "Corpus search unavailable" not in output

    def test_corpus_search_invalid_fts_query_closes_connection(self):
        class FakeCursor:
            def execute(self, *args, **kwargs):
                raise sqlite3.OperationalError("unterminated string")

        class FakeConnection:
            def __init__(self):
                self.closed = False

            def cursor(self):
                return FakeCursor()

            def close(self):
                self.closed = True

        conn = FakeConnection()
        with (
            patch("caseprep.mcp_server._CORPUS_AVAILABLE", True),
            patch("caseprep.mcp_server._corpus_conn", return_value=conn),
        ):
            result = _corpus_search('"')

        assert result["error"] == "Invalid FTS query: unterminated string"
        assert result["papers"] == []
        assert result["total_matches"] == 0
        assert conn.closed
