# Repository Guidelines

## Project Structure & Module Organization
- `acquisition/`: I/O helpers unified under `base.DataAcquirer` (e.g., `ftp_manager.py`, `http_manager.py`, `s3_manager.py`, `vimeo_manager.py`).
- `processing/`: processors unified under `base.DataProcessor` (e.g., `grib_data_processor.py`, `video_processor.py`).
- `visualization/`: renderers unified under `base.Renderer` (e.g., `plot_manager.py`, `colormap_manager.py`).
- `utils/`: shared helpers (e.g., `credential_manager.py`, `date_manager.py`, `file_utils.py`, `image_manager.py`, `json_file_manager.py`).
- `assets/`: static resources packaged with the library (e.g., `assets/images/` for basemaps/overlays); prefer `importlib.resources` to resolve paths at runtime.
- `samples/`: runnable examples and small utilities (optional, not always present).

## Build, Test, and Development Commands
- Install with Poetry (core): `poetry install --with dev` (creates the venv).
- Opt-in extras locally as needed, e.g.: `poetry install --with dev -E connectors -E processing -E visualization` or `--all-extras`.
- Spawn shell: `poetry shell`.
- Run a script or module: `poetry run python path/to/your_script.py` or `poetry run python -m your.module`.
- Lint/format: `poetry run ruff format . && poetry run ruff check .` (Ruff replaces Black/Isort/Flake8 when configured).
- FFmpeg-required flows: ensure `ffmpeg` and `ffprobe` are installed on the system.

## Coding Style & Naming Conventions
- Indentation: 4 spaces; UTF-8; Unix newlines.
- Filenames: `snake_case` (e.g., `ftp_manager.py`, `plot_manager.py`), classes in `PascalCase` (e.g., `FTPManager`, `PlotManager`).
- Functions/variables: `snake_case`; constants: `UPPER_CASE`.
- Imports: standard lib, third-party, local (separated groups).
- Formatting: run `black .` and `isort .`; lint with `flake8` before opening PRs.

## Testing Guidelines
- Framework: `pytest`.
- Location: `tests/` at the repo root; name files `test_*.py` and functions `test_*`.
- Run tests: `poetry run pytest -q` (optionally `-k pattern` to filter).
- Data-heavy flows: prefer tiny fixtures or sample assets in `samples/`.

## Commit & Pull Request Guidelines
- Commits: imperative mood, concise subject (e.g., "Add GRIB parser"); group related changes.
- Conventional prefixes optional (seen: `ci:`). Avoid WIP commits in PRs.
- PRs: clear description, scope, and rationale; link issues; include run instructions and screenshots for visual changes.
- Checks: pass lint/format; run sample scripts touched by the change.

## Security & Configuration Tips
- Credentials: never commit secrets. For AWS, prefer IAM roles or env vars consumed by `S3Manager` (`datavizhub.acquisition.s3_manager`).
- Paths: avoid hard-coded absolute paths; make paths configurable via env (e.g., `DATA_DIR`).
- Assets: packaged resources live under `datavizhub.assets`; use `importlib.resources` to resolve paths (works in wheels/sdists).
- Dependencies: pin if adding new requirements; document any system deps (e.g., FFmpeg, PROJ/GEOS for Cartopy).

## Dependency Management (Poetry)
- Primary files: `pyproject.toml` and `poetry.lock` control dependencies and reproducibility.
- No `requirements.txt` is needed. If a pip-only workflow requires it, export via:
  - `poetry export -f requirements.txt --output requirements.txt --without-hashes`
  - Include dev groups when needed: `poetry export -f requirements.txt --with dev -o requirements-dev.txt`

Dev container:
- The dev container installs dev dependencies plus all extras by default (`poetry install --with dev --all-extras`). This ensures optional integrations (S3 via boto3, Vimeo via PyVimeo, HTTP via requests, processing/visualization stacks) are available out of the box.

## Documentation Sources
- Wiki: https://github.com/NOAA-GSL/datavizhub/wiki (authoritative documentation for humans and AIs).
- CI-synced wiki: A GitHub Action mirrors the GitHub Wiki into `docs/source/wiki/` so it is built with Sphinx. Do not edit `docs/source/wiki/` directly; changes are committed only on `main`.
