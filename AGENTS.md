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

- Pre-commit is enabled. Config: https://github.com/NOAA-GSL/zyra/blob/main/.pre-commit-config.yaml
- One-time setup:
  - `poetry install --with dev`
  - `poetry run pre-commit install`
- Run hooks manually on all files: `poetry run pre-commit run -a`
- Hooks enforce Ruff formatting/linting (authoritative list in the config above).
- DCO: All commits must include a Signed-off-by line (see CONTRIBUTING). Add `-s` to `git commit` or enable global sign-off: `git config --global format.signoff true`.

Agent Checklist (before returning code)

- [ ] Ran `poetry run ruff format . && poetry run ruff check .` and confirmed clean
- [ ] Ran targeted tests (or full suite if requested) and confirmed passing
- [ ] Limited scope to requested changes; updated or added documentation if needed
- [ ] Called out any assumptions, follow-ups, or external system requirements (e.g., FFmpeg)

Notes for CI and PRs

- CI should run `poetry run ruff format --check . && poetry run ruff check .` to ensure compliance. DCO sign-off is enforced by the GitHub DCO app on pull requests.
- Group related changes into single PRs with a clear description and run instructions.

Repository Guidelines

Project Structure & Module Organization

- Code lives under `src/zyra/`:
  - `connectors/`: source/destination integrations and CLI registrars (`connectors.ingest`, `connectors.egress`, with shared `backends/`). Prefer these over legacy `acquisition/` for new work.
  - `processing/`: data processing (e.g., GRIB/NetCDF/GeoTIFF) exposed via CLI.
  - `visualization/`: visualization commands (static, animated, interactive); CLI registration lives alongside commands.
  - `transform/`: lightweight helpers (metadata scans, enrich/merge, dataset JSON updates).
  - `api/`: FastAPI service exposing selected CLI functionality (see `zyra.api_cli`).
  - `wizard/`: optional assistant UX; ships JSON resources under `src/zyra/wizard/*.json`.
  - `utils/`: shared helpers/utilities (credentials, dates, files, images, I/O).
  - `assets/`: packaged resources (e.g., basemaps/overlays under `assets/images/`). Access via `importlib.resources` (`zyra.assets`).
  - `cli.py`: root CLI entry (`zyra`); `api_cli.py`: API service CLI (`zyra-cli`).

### Assistant/Wizard Resources

- Wizard resources (JSON) are packaged under `src/zyra/wizard/*.json` and may be used to drive interactive flows.
- If a CLI capabilities file is present in the repo, keep it in sync with CLI changes; otherwise, prefer runtime discovery and module docstrings for accuracy.

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

- Synced wiki in repo (for offline/background reading): `/docs/source/wiki/` — this is a cron-synced mirror of the GitHub Wiki. Prefer this path when you need background information by browsing the code repository.
- Wiki (live, high-level docs, patterns, overview): https://github.com/NOAA-GSL/zyra/wiki
- API Reference (module/CLI docs): https://noaa-gsl.github.io/zyra/
- Key wiki pages to ground answers:
  - Workflow Stages: https://github.com/NOAA-GSL/zyra/wiki/Workflow-Stages
  - Stage Examples: https://github.com/NOAA-GSL/zyra/wiki/Stage-Examples
  - Install & Extras: https://github.com/NOAA-GSL/zyra/wiki/Install-Extras
- Pipeline Patterns: https://github.com/NOAA-GSL/zyra/wiki/Pipeline-Patterns

Notes
- The `/docs/source/wiki/` content is generated via a scheduled sync from the GitHub Wiki. Do not hand-edit files in that folder unless the sync process specifically instructs otherwise. If you see a discrepancy between the repo copy and the live wiki, defer to the live wiki as the source of truth and file an issue to correct the mirror.

Documentation contribution guidelines (where to put updates)
- Keep the top-level README concise. For detailed usage and options, prefer module-level READMEs and the wiki.
- Module READMEs live next to code and should contain focused examples and flags:
  - Connectors (ingest/egress/discovery):
    - `src/zyra/connectors/ingest/README.md`
    - `src/zyra/connectors/egress/README.md`
    - `src/zyra/connectors/discovery/README.md`
  - Processing: `src/zyra/processing/README.md`
  - Visualization: `src/zyra/visualization/README.md`
  - Transform: `src/zyra/transform/README.md`
  - API service: `src/zyra/api/README.md`
  - MCP tools: `src/zyra/api/mcp_tools/README.md`
- Sphinx includes these module READMEs under "Module READMEs" in `docs/source/index.rst`. If you add a new README, include it there.
- Keep function/class docstrings current; autodoc consumes them for the API reference pages.
- Use the GitHub Wiki for narrative guides and high-level design. The mirrored copy under `docs/source/wiki/` is not edited directly.

When In Doubt: Decision Flow

- CLI usage or flags
  - Check generated docs: https://noaa-gsl.github.io/zyra/api/zyra.cli.html
  - Run local help where possible: `poetry run zyra --help` (or subcommand `--help`).
  - Cross-check examples in `Stage-Examples.md`.
- Background/context
  - Read the synced wiki in `/docs/source/wiki/`.
  - If stale or missing, read the live wiki: https://github.com/NOAA-GSL/zyra/wiki
- Implementation details
  - Search code under `src/zyra/` (connectors, processing, visualization, transform, api, utils).
- Roadmap/status
  - Issues (enhancements/bugs): https://github.com/NOAA-GSL/zyra/issues
  - Discussions (design/ideas): https://github.com/NOAA-GSL/zyra/discussions
- Security & policy
  - Zyra-API-Security-Quickstart.md, Privacy-and-Data-Usage-Best-Practices-for-Zyra.md, Logging-in-Zyra.md
- Deploy/run
  - Zyra-Containers-Overview-and-Usage.md; API routers/endpoints page

Quick Test Loop (suggested)

```
# Format + lint (required)
poetry run ruff format . && poetry run ruff check .

# Focused tests
poetry run pytest -q -k <pattern>

# Sanity: help text prints and exits
poetry run zyra --help
```

Stage Naming & Aliases (for CLI and docs)

- Preferred: import → process → simulate → decide → visualize → narrate → verify → export
- Aliases: acquire/ingest → process/transform → visualize/render → export/disseminate (legacy: decimate)
- Implemented today: acquire (`http|s3|ftp|vimeo`), process (`decode-grib2|extract-variable|convert-format`), visualize (`heatmap|contour|animate|compose-video|interactive`), export (`local|s3|ftp|post|vimeo`)
- Streaming: many commands accept `-` (stdin/stdout) to support piping.
