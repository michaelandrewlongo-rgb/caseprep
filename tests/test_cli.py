"""Tests for caseprep.cli — argument parsing and integration."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from caseprep.cli import main
from caseprep.core import BuildCasePlanResult


class TestCliBasics:
    def test_help_flag(self, capsys):
        with pytest.raises(SystemExit) as exc:
            main(["--help"])
        assert exc.value.code == 0
        captured = capsys.readouterr()
        assert "usage: caseprep" in captured.out or "usage: caseprep" in captured.err

    def test_version_flag(self, capsys):
        with pytest.raises(SystemExit) as exc:
            main(["--version"])
        assert exc.value.code == 0

    def test_missing_topic_exits(self):
        # With subcommands, bare `caseprep` prints help and returns 0
        # (previously raised SystemExit with positional topic)
        exit_code = main([])
        assert exit_code == 0


class TestCliGenerate:
    def test_basic_run_creates_output(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "test-case"
            exit_code = main(["brain tumor", "-o", str(out)])
            assert exit_code == 0
            assert (out / "README.md").is_file()
            assert (out / "resource-links.html").is_file()

    def test_bare_topic_uses_generate_path(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "bare-topic"
            resource = out / "resource-links.html"
            with patch("caseprep.cli.generate_caseprep", return_value=resource) as generate:
                exit_code = main(["vestibular schwannoma", "-o", str(out)])

            assert exit_code == 0
            generate.assert_called_once_with(
                "vestibular schwannoma",
                out,
                open_browser=False,
            )

    def test_bare_topic_option_first_uses_generate_path(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "option-first"
            resource = out / "resource-links.html"
            with patch("caseprep.cli.generate_caseprep", return_value=resource) as generate:
                exit_code = main(["-o", str(out), "glioma"])

            assert exit_code == 0
            generate.assert_called_once_with(
                "glioma",
                out,
                open_browser=False,
            )

    def test_bare_topic_option_value_matching_subcommand_uses_generate_path(self):
        resource = Path("build") / "resource-links.html"
        with patch("caseprep.cli.generate_caseprep", return_value=resource) as generate:
            exit_code = main(["-o", "build", "glioma"])

        assert exit_code == 0
        generate.assert_called_once_with(
            "glioma",
            Path("build"),
            open_browser=False,
        )

    def test_bare_topic_open_option_first_uses_generate_path(self):
        resource = Path("glioma-caseprep") / "resource-links.html"
        with patch("caseprep.cli.generate_caseprep", return_value=resource) as generate:
            exit_code = main(["--open", "glioma"])

        assert exit_code == 0
        generate.assert_called_once_with(
            "glioma",
            Path("glioma-caseprep"),
            open_browser=True,
        )

    def test_bare_topic_open_and_output_options_use_generate_path(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "glioma-caseprep"
            resource = out / "resource-links.html"
            with patch("caseprep.cli.generate_caseprep", return_value=resource) as generate:
                exit_code = main(["--open", "glioma", "-o", str(out)])

            assert exit_code == 0
            generate.assert_called_once_with(
                "glioma",
                out,
                open_browser=True,
            )

    def test_default_output_dir_name(self):
        with tempfile.TemporaryDirectory() as d:
            import os
            orig = os.getcwd()
            try:
                os.chdir(d)
                exit_code = main(["acoustic neuroma"])
                assert exit_code == 0
                out = Path(d) / "acoustic-neuroma-caseprep"
                assert out.is_dir()
            finally:
                os.chdir(orig)

    def test_open_flag_does_not_crash(self):
        """--open calls webbrowser.open; just verify it doesn't crash."""
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "test-case"
            exit_code = main(["glioma", "-o", str(out), "--open"])
            assert exit_code == 0  # webbrowser.open is best-effort

    def test_local_pdfs_nonexistent_dir(self, capsys):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "test-case"
            exit_code = main([
                "glioma", "-o", str(out),
                "--local-pdfs", "/nonexistent/path/pdfs",
            ])
            assert exit_code == 0
            captured = capsys.readouterr()
            assert "Not a directory" in captured.out or "No matches" in captured.out


class TestCliBuild:
    def test_build_parses_case_input_and_output_dir(self, capsys):
        case_input = (
            "C5-6 anterior cervical discectomy and fusion for right C6 "
            "radiculopathy from foraminal disc osteophyte complex"
        )
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "acdf"
            result = BuildCasePlanResult(
                topic=case_input,
                markdown="# plan",
                output_dir=out,
                mode="core",
                structured={
                    "case": {
                        "pathology": {"value": "foraminal disc osteophyte complex"},
                        "procedure": {"value": "anterior cervical discectomy and fusion"},
                        "approach": {"value": "anterior cervical"},
                        "missing_critical_facts": ["patient age"],
                        "degraded": True,
                        "degradation_reason": "Missing critical facts: patient age",
                    },
                    "procedure_family": {"id": "acdf"},
                    "profile": {"name": "spine"},
                    "retrieval": {"sources": {"pubmed": 2, "corpus": 1}},
                },
                warnings=["Radiology unavailable"],
            )
            builder = AsyncMock(return_value=result)

            with patch("caseprep.cli.build_core_case_plan", builder):
                exit_code = main(["build", case_input, "-o", str(out)])

        assert exit_code == 0
        builder.assert_awaited_once()
        assert builder.await_args is not None
        request = builder.await_args.args[0]
        assert request.case_input == case_input
        assert request.output_dir == out

        captured = capsys.readouterr()
        assert f"Case prep built → {out.resolve()}" in captured.out
        assert "pathology: foraminal disc osteophyte complex" in captured.out
        assert "procedure: anterior cervical discectomy and fusion" in captured.out
        assert "approach: anterior cervical" in captured.out
        assert "family: acdf" in captured.out
        assert "profile: spine" in captured.out
        assert "- patient age" in captured.out
        assert "- corpus: 1" in captured.out
        assert "- pubmed: 2" in captured.out
        assert "- Radiology unavailable" in captured.out

    def test_build_without_output_passes_default_output_dir(self, capsys):
        case_input = "left frontal glioma craniotomy"
        with tempfile.TemporaryDirectory() as d:
            import os
            orig = os.getcwd()
            os.chdir(d)
            try:
                expected = Path(d) / "left-frontal-glioma-craniotomy-caseprep"

                async def fake_builder(request):
                    return BuildCasePlanResult(
                        topic=request.case_input,
                        markdown="# plan",
                        output_dir=request.output_dir,
                        mode="core",
                        structured={},
                    )

                with patch("caseprep.cli.build_core_case_plan", side_effect=fake_builder) as builder:
                    exit_code = main(["build", case_input])
            finally:
                os.chdir(orig)

        assert exit_code == 0
        assert builder.await_args is not None
        request = builder.await_args.args[0]
        assert request.case_input == case_input
        assert request.output_dir == expected

        captured = capsys.readouterr()
        assert f"Case prep built → {expected.resolve()}" in captured.out

    def test_build_missing_structured_output_does_not_crash(self, capsys):
        case_input = "glioma"
        result = BuildCasePlanResult(
            topic=case_input,
            markdown="# plan",
            output_dir=None,
            mode="core",
        )
        object.__setattr__(result, "structured", None)
        builder = AsyncMock(return_value=result)

        with patch("caseprep.cli.build_core_case_plan", builder):
            exit_code = main(["build", case_input, "-o", "out"])

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Case prep built" in captured.out
        assert "warnings: none" in captured.out

    def test_build_topic_only_degraded_structured_output_prints_safely(self, capsys):
        case_input = "glioma"
        result = BuildCasePlanResult(
            topic=case_input,
            markdown="# plan",
            output_dir=None,
            mode="core",
            structured={
                "case": {
                    "pathology": "glioma",
                    "degraded": True,
                    "degradation_reason": "Topic-only input; missing procedural detail",
                },
            },
        )
        builder = AsyncMock(return_value=result)

        with patch("caseprep.cli.build_core_case_plan", builder):
            exit_code = main(["build", case_input, "-o", "out"])

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "pathology: glioma" in captured.out
        assert "missing critical facts: none" in captured.out
        assert "degraded: True" in captured.out
        assert "degradation reason: Topic-only input; missing procedural detail" in captured.out

    def test_build_non_dict_sources_and_string_missing_facts_print_safely(self, capsys):
        case_input = "glioma"
        result = BuildCasePlanResult(
            topic=case_input,
            markdown="# plan",
            output_dir=None,
            mode="core",
            structured={
                "case": {"missing_critical_facts": "need MRI"},
                "retrieval": {"sources": []},
            },
        )
        builder = AsyncMock(return_value=result)

        with patch("caseprep.cli.build_core_case_plan", builder):
            exit_code = main(["build", case_input, "-o", "out"])

        assert exit_code == 0
        captured = capsys.readouterr()
        assert captured.out.count("- need MRI") == 1
        assert "- n\n" not in captured.out
        assert "source counts:" in captured.out
        assert "- none: 0" in captured.out
