# Repository Guidelines

## Project Structure & Module Organization
- `src/project_to_epub/` contains the package code.
- `src/project_to_epub/cli.py` defines the Typer CLI and command options.
- `src/project_to_epub/converter.py` handles project scanning, syntax highlighting, and EPUB assembly.
- `tests/` contains the pytest suite:
- `tests/test_converter.py` for unit-level behavior.
- `tests/test_integration.py` for end-to-end conversion checks.
- `tests/conftest.py` for reusable fixtures.
- `test_project/` is a sample project for local/manual smoke testing.
- `.github/workflows/python-publish.yml` runs tests, build checks, and publish jobs.

## Build, Test, and Development Commands
- `python -m venv .venv && source .venv/bin/activate`: create and activate a virtual environment.
- `pip install -e ".[dev]"`: install package in editable mode with dev dependencies.
- `pytest`: run all tests (configured via `pyproject.toml`).
- `ruff check .`: run lint checks (E/F/I/W rules).
- `black . && isort .`: apply formatting and import sorting.
- `python -m build`: build source and wheel distributions.
- `twine check dist/*`: validate package metadata before publishing.
- `project-to-epub ./test_project -o ./test_project.epub`: quick local CLI smoke test.

## Coding Style & Naming Conventions
- Follow Black/isort defaults with `line-length = 88`.
- Use snake_case for modules, functions, and variables; use CapWords for classes (for example, `Project`, `FileEntry`).
- Keep public functions and CLI behavior documented with concise docstrings/help text.
- Preserve readable logging and explicit error messages in CLI and conversion paths.

## Testing Guidelines
- Use pytest; test files must match `test_*.py`.
- Add unit tests for conversion helpers and ignore/filter logic.
- Add integration tests when changing EPUB structure, metadata, or output file handling.
- No coverage threshold is enforced in CI; treat behavior changes as requiring regression tests.

## Commit & Pull Request Guidelines
- Use concise imperative commit subjects, consistent with history (for example, `Add flat TOC option`, `Fix GitHub workflow`).
- Reference issue/PR numbers when applicable (for example, `(#3)`).
- PRs should include purpose, behavior impact, test evidence (`pytest`), and example CLI usage/output for user-facing changes.
