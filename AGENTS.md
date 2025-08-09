# Repository Guidelines

## Project Structure & Module Organization
- `datatransfer/`: I/O helpers (e.g., `S3Manager.py`, `HTTPManager.py`).
- `processing/`: data/video processing (e.g., `GRIBDataProcessor.py`, `VideoProcessor.py`).
- `visualization/`: plotting utilities (e.g., `PlotManager.py`, `ColormapManager.py`).
- `utils/`: shared helpers (dates, files, images, credentials).
- `samples/`: runnable examples and small utilities.
- `images/`: basemaps and overlays used by plots.
- `pols.py`: example script for pollen plots (reads NetCDF from `/data/temp/pollen/`).

## Build, Test, and Development Commands
- Install with Poetry: `poetry install` (creates and manages the venv).
- Spawn shell: `poetry shell`; run once-off: `poetry run python pols.py`.
- Run samples: `poetry run python samples/global_smoke.py` (ensure data paths exist).
- Lint/format (if added): `poetry run black . && poetry run isort . && poetry run flake8`.
- FFmpeg-required flows: ensure `ffmpeg` and `ffprobe` are installed on the system.

## Coding Style & Naming Conventions
- Indentation: 4 spaces; UTF-8; Unix newlines.
- Filenames: follow existing pattern (e.g., `XyzManager.py`), classes in `PascalCase`.
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
- Credentials: never commit secrets. For AWS, prefer IAM roles or env vars consumed by `S3Manager`.
- Paths: scripts may assume data under `/data/...`; make paths configurable via env (e.g., `DATA_DIR`).
- Dependencies: pin if adding new requirements; document any system deps (e.g., FFmpeg, PROJ/GEOS for Cartopy).

## Dependency Management (Poetry)
- Primary files: `pyproject.toml` and `poetry.lock` control dependencies and reproducibility.
- No `requirements.txt` is needed. If a pip-only workflow requires it, export via:
  - `poetry export -f requirements.txt --output requirements.txt --without-hashes`
  - Include dev groups when needed: `poetry export -f requirements.txt --with dev -o requirements-dev.txt`

## Documentation Sources
- Wiki: https://github.com/NOAA-GSL/datavizhub/wiki (authoritative documentation for humans and AIs).
- Dev container mirror: `/app/docs` contains an auto-cloned snapshot of the wiki for offline/context use. It auto-refreshes at most once per hour on container start. Force refresh with `bash .devcontainer/postStart.sh --force`. This folder is ignored by Git and is not part of the main repository—do not commit its contents.
