Agent Workflow and Guardrails

Purpose: This repository is agent-friendly. Follow these rules to keep changes safe, consistent, and easy to review.

Core Rules

- Lint first: Before making any code changes, run:
  - `poetry run ruff format . && poetry run ruff check .`
  - Fix all issues so `ruff check` returns clean. Only then proceed.
- Small, surgical edits: Change only what’s needed. Keep file/identifier names stable unless the task explicitly requires refactors.
- Tests: Prefer running focused tests for the area you changed:
  - `poetry run pytest -q -k <pattern>` (or the full suite if requested).
- No secrets: Never commit credentials or tokens. Prefer environment variables and documented configuration paths.
- Paths: Avoid absolute paths. Use configurable env vars (e.g., `DATA_DIR`) and `importlib.resources` for packaged assets.
- Style: Follow the project’s coding style and naming conventions (see README and repository guidelines).

Pre-commit Hooks

- This repo ships with a pre-commit configuration to enforce Ruff formatting and linting.
- One-time setup:
  - `poetry install --with dev` (ensures `pre-commit` and `ruff` are available)
  - `poetry run pre-commit install`
- Run hooks manually on all files: `poetry run pre-commit run -a`
- Hooks included:
  - Ruff format (code formatting)
  - Ruff (lint, with autofix; commit fails if fixes were applied)

Agent Checklist (before returning code)

- [ ] Ran `poetry run ruff format . && poetry run ruff check .` and confirmed clean
- [ ] Ran targeted tests (or full suite if requested) and confirmed passing
- [ ] Limited scope to requested changes; updated or added documentation if needed
- [ ] Called out any assumptions, follow-ups, or external system requirements (e.g., FFmpeg)

Notes for CI and PRs

- CI should run `poetry run ruff format --check . && poetry run ruff check .` to ensure compliance.
- Group related changes into single PRs with a clear description and run instructions.

Repository Guidelines

Project Structure & Module Organization

- Code lives under `src/zyra/`:
  - `connectors/`: source/destination integrations and CLI registrars (`connectors.ingest`, `connectors.egress`). Prefer these over legacy `acquisition/` for new work.
  - `processing/`: data processing (e.g., GRIB/NetCDF/GeoTIFF) exposed via the CLI.
  - `visualization/`: visualization commands; CLI registration lives in `visualization/cli_register.py`.
  - `wizard/`: interactive assistant and related utilities.
  - `api/` + `api_cli.py`: HTTP API and CLI entry points.
  - `transform/`: transform helpers (metadata, etc.).
  - `utils/`: shared helpers/utilities.
  - `assets/`: packaged static resources; access with `importlib.resources` (`zyra.assets`).
  - `cli.py`, `pipeline_runner.py`: root CLI and pipeline runner.

Build, Test, and Development

- Install: `poetry install --with dev` (use extras as needed: `-E connectors -E processing -E visualization` or `--all-extras`).
- Shell: `poetry shell`.
- Run: `poetry run python path/to/script.py` or `poetry run python -m module`.
- Lint/format: `poetry run ruff format . && poetry run ruff check .`.
- Tests: `poetry run pytest -q` (filter with `-k pattern`).
- System deps: certain flows require FFmpeg (`ffmpeg`, `ffprobe`).

Coding Style & Naming

- Python 3.10+; UTF-8; Unix newlines; 4-space indent.
- Names: files/functions in `snake_case`; classes in `PascalCase`; constants in `UPPER_CASE`.
- Imports grouped: stdlib, third-party, local.
- Formatting and linting via Ruff (replaces Black/Isort/Flake8 in this repo).

Testing Guidelines

- Tests live under `tests/`; files named `test_*.py`, functions `test_*`.
- Prefer small fixtures and sample assets for data-heavy flows.

Commit & PR Guidelines

- Commits: imperative, concise (e.g., "Add GRIB parser"); group related changes.
- PRs: clear scope and rationale; link issues; include run instructions and screenshots for visual changes.
- Checks: pass Ruff format/lint; run relevant sample scripts if modified.

Security & Configuration

- Do not commit secrets. Prefer IAM roles or env vars (e.g., used by S3 connectors).
- Avoid hard-coded absolute paths; prefer env-configurable paths (e.g., `DATA_DIR`).
- Use `importlib.resources` for packaged assets under `zyra.assets`.
- Pin dependencies when adding new ones; document any system deps (e.g., FFmpeg, PROJ/GEOS).

Dependency Management (Poetry)

- Sources of truth: `pyproject.toml` and `poetry.lock`.
- Export for pip workflows if needed:
  - `poetry export -f requirements.txt --output requirements.txt --without-hashes`
  - Include dev: `poetry export -f requirements.txt --with dev -o requirements-dev.txt`

Documentation Sources

- Authoritative docs live under `docs/source/wiki/` in this repo (built with Sphinx).
- If CI syncs from a GitHub Wiki, treat `docs/source/wiki/` as the source consumed by the docs build (do not hand-edit generated/synced content unless the process specifies).
