"""Golden contract tests for public CasePrep adapters."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "contracts"


def _load_json(name: str) -> Any:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def _strip_descriptions(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _strip_descriptions(child)
            for key, child in value.items()
            if key != "description"
        }
    if isinstance(value, list):
        return [_strip_descriptions(item) for item in value]
    return value


@pytest.mark.asyncio
async def test_mcp_tool_names_and_input_schemas_match_contract():
    from caseprep.mcp_server import list_tools

    tools = await list_tools()
    actual = [
        {
            "name": tool.name,
            "inputSchema": _strip_descriptions(tool.inputSchema),
        }
        for tool in tools
    ]

    assert actual == _load_json("mcp_tools.json")


def test_cli_top_level_help_matches_contract(capsys):
    from caseprep.cli import main

    with pytest.raises(SystemExit) as exc:
        main(["--help"])

    assert exc.value.code == 0
    assert capsys.readouterr().out.rstrip() == (
        FIXTURE_DIR / "cli_help.txt"
    ).read_text(encoding="utf-8").rstrip()


def test_fastapi_route_paths_and_methods_match_contract():
    from caseprep.web import app

    routes = [
        {"path": route.path, "methods": sorted(route.methods or [])}
        for route in app.routes
        if route.path.startswith("/api")
    ]
    actual = sorted(routes, key=lambda route: (route["path"], ",".join(route["methods"])))

    assert actual == _load_json("fastapi_routes.json")
