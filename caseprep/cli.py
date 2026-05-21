"""CLI entry point for caseprep."""

import argparse
import asyncio
import sys
from dataclasses import replace
from pathlib import Path

from . import __version__
from .core import BuildCasePlanRequest
from .core.builder import build_core_case_plan
from .generator import generate_caseprep, _slugify
from .pdfs import format_pdf_results, search_local_pdfs


def _cmd_generate(args: argparse.Namespace) -> int:
    """Generate a case prep folder (original CLI behaviour)."""
    output_dir = Path(args.output or (_slugify(args.topic) + "-caseprep"))

    resource_path = generate_caseprep(
        args.topic,
        output_dir,
        open_browser=args.open,
    )

    print(f"Case prep generated → {output_dir.resolve()}")
    print(f"Resource links → {resource_path}")

    if args.local_pdfs:
        print(f"\nSearching local PDFs in {args.local_pdfs} …")
        results = search_local_pdfs(args.topic, args.local_pdfs)
        print(format_pdf_results(results))

    return 0


def _field_value(mapping: dict, key: str) -> object:
    value = mapping.get(key)
    if isinstance(value, dict):
        return value.get("value")
    return value


def _cmd_build(args: argparse.Namespace) -> int:
    """Build a populated case dossier using the core builder."""
    request = BuildCasePlanRequest(
        case_input=args.case_input,
        output_dir=args.output,
        structured_output=True,
    )
    if args.output is None:
        request = replace(request, output_dir=request.resolved_output_dir())
    result = asyncio.run(build_core_case_plan(request))

    if result.output_dir is not None:
        print(f"Case prep built → {result.output_dir.resolve()}")
    else:
        print("Case prep built")

    structured = result.structured if isinstance(result.structured, dict) else {}
    case = structured.get("case") or {}
    if isinstance(case, dict):
        for key in ("pathology", "procedure", "approach"):
            value = _field_value(case, key)
            if value:
                print(f"{key}: {value}")

        missing = case.get("missing_critical_facts")
        if missing is None:
            missing = []
        elif isinstance(missing, str):
            missing = [missing]
        else:
            try:
                missing = list(missing)
            except TypeError:
                missing = [missing]
        if missing:
            print("missing critical facts:")
            for fact in missing:
                print(f"- {fact}")
        else:
            print("missing critical facts: none")

        degraded = case.get("degraded")
        reason = case.get("degradation_reason")
        if degraded is not None:
            print(f"degraded: {degraded}")
        if reason:
            print(f"degradation reason: {reason}")

    procedure_family = structured.get("procedure_family")
    if isinstance(procedure_family, dict):
        family = (
            procedure_family.get("id")
            or procedure_family.get("name")
            or procedure_family.get("label")
        )
    else:
        family = procedure_family
    if family:
        print(f"family: {family}")

    profile = structured.get("profile")
    if isinstance(profile, dict):
        profile_name = profile.get("name") or profile.get("profile")
    else:
        profile_name = profile
    if profile_name:
        print(f"profile: {profile_name}")

    retrieval = structured.get("retrieval") or {}
    if isinstance(retrieval, dict):
        sources = retrieval.get("sources") or {}
        print("source counts:")
        if isinstance(sources, dict) and sources:
            for source, count in sorted(sources.items()):
                print(f"- {source}: {count}")
        else:
            print("- none: 0")

    if result.warnings:
        print("warnings:")
        for warning in result.warnings:
            print(f"- {warning}")
    else:
        print("warnings: none")

    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    """Launch the CasePrep web dashboard."""
    import uvicorn
    from .web import app

    host = args.host
    port = args.port
    url = f"http://{host}:{port}"
    print(f"  CasePrep dashboard → {url}")
    print(f"  API docs           → {url}/docs")
    print(f"  Press Ctrl+C to stop\n")

    if args.open:
        import webbrowser
        webbrowser.open(url)

    uvicorn.run(app, host=host, port=port, log_level=args.log_level)
    return 0


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and run caseprep.  Returns exit code."""
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(
        prog="caseprep",
        description="Generate structured neurosurgical case prep materials.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"caseprep {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # ── generate (default) ──────────────────────────────────────────────
    gen = subparsers.add_parser(
        "generate",
        help="Generate a case prep folder (default command)",
    )
    gen.add_argument(
        "topic",
        help="Case or topic string (e.g. 'vestibular schwannoma')",
    )
    gen.add_argument(
        "-o", "--output",
        type=Path,
        help="Output directory (default: {slug}-caseprep/)",
    )
    gen.add_argument(
        "--open",
        action="store_true",
        help="Open resource-links.html in the default browser after generation.",
    )
    gen.add_argument(
        "--local-pdfs",
        type=Path,
        metavar="DIR",
        help="Directory of PDFs to search for topic matches.",
    )

    # ── build ─────────────────────────────────────────────────────────────
    build = subparsers.add_parser(
        "build",
        help="Build a populated case prep dossier using the core builder",
    )
    build.add_argument(
        "case_input",
        help="Free-text case string",
    )
    build.add_argument(
        "-o", "--output",
        type=Path,
        help="Output directory (default: {slug}-caseprep/)",
    )

    # ── serve ───────────────────────────────────────────────────────────
    srv = subparsers.add_parser(
        "serve",
        help="Launch the CasePrep web dashboard",
    )
    srv.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind host (default: 127.0.0.1)",
    )
    srv.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Bind port (default: 8000)",
    )
    srv.add_argument(
        "--open",
        action="store_true",
        help="Open the dashboard in the default browser on startup.",
    )
    srv.add_argument(
        "--log-level",
        default="info",
        choices=["critical", "error", "warning", "info", "debug"],
        help="Uvicorn log level (default: info)",
    )

    # Backwards compatibility: bare `caseprep <topic>` → `caseprep generate <topic>`.
    # Also support option-first legacy invocations like `caseprep -o out glioma`.
    _subcommands = {"build", "generate", "serve"}
    _top_level_flags = {"-h", "--help", "--version"}
    _options_with_values = {"-o", "--output", "--local-pdfs", "--host", "--port", "--log-level"}

    def _first_command_token(args: list[str]) -> str | None:
        skip_next = False
        for arg in args:
            if skip_next:
                skip_next = False
                continue
            if arg == "--":
                return None
            if arg in _options_with_values:
                skip_next = True
                continue
            if any(arg.startswith(option + "=") for option in _options_with_values if option.startswith("--")):
                continue
            if arg.startswith("-"):
                continue
            return arg
        return None

    if argv and argv[0] not in _top_level_flags and _first_command_token(argv) not in _subcommands:
        argv = ["generate"] + list(argv)

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "build":
        return _cmd_build(args)
    if args.command == "serve":
        return _cmd_serve(args)
    return _cmd_generate(args)


if __name__ == "__main__":
    sys.exit(main())
