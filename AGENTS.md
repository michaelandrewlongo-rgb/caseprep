# Repository Guidelines

## Project Structure & Module Organization

`caseprep/` contains the Python package. Key modules include `cli.py` for the command-line entry point, `generator.py` for folder/template generation, `web.py` for the FastAPI dashboard, `mcp_server.py` for MCP tools, and `db.py` for SQLite persistence. Static frontend assets live in `caseprep/static/`. Tests are in `tests/` and mirror the main behaviors: CLI, web/API, PDF search, links, radiology, and template population.

## Build, Test, and Development Commands

- `pip install -e ".[dev]"`: install the package locally with pytest.
- `pytest -v`: run the full test suite.
- `caseprep "vestibular schwannoma"`: generate a case-prep folder using the default output name.
- `caseprep generate "pituitary adenoma" -o ~/cases/pa`: generate into a specific directory.
- `caseprep serve --host 127.0.0.1 --port 8000`: run the FastAPI dashboard locally.
- `caseprep-mcp`: start the MCP server entry point.

## Coding Style & Naming Conventions

Use Python 3.10+ syntax and type hints where they clarify interfaces. Follow the existing module style: 4-space indentation, concise docstrings for public functions, `Path` for filesystem work, and explicit imports from local modules. Keep names descriptive and snake_case for functions, variables, and modules. Test classes may use `TestFeatureName`; test functions should start with `test_`. No formatter or linter is currently configured, so keep edits consistent with nearby code.

## Testing Guidelines

The project uses pytest. Add or update tests in `tests/` for behavior changes, especially for CLI argument handling, generated files, API responses, database persistence, and external-service fallbacks. Mock network-dependent handlers as existing web tests do with `unittest.mock.patch` and `AsyncMock`. Prefer temporary directories via `tmp_path` or `tempfile` over writing into the repository.

## Commit & Pull Request Guidelines

Git history currently uses short, imperative commit messages such as `Remove runtime db artifacts, add to gitignore`. Keep commits focused and describe the changed behavior. Pull requests should include a brief summary, test results such as `pytest -v`, linked issues when applicable, and screenshots or API examples for dashboard changes.

## Security & Configuration Tips

Do not commit generated `*-caseprep/`, `*-images/`, local SQLite databases, `.env`, or patient-sensitive materials. These are ignored by `.gitignore`, but verify before committing. Keep external API/network behavior isolated behind mockable handlers so tests remain deterministic.
