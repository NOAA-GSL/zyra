# Copilot Repository Instructions for Zyra

## Project Summary
Zyra is an open-source **Python framework for scientific data visualization**.  
It provides a **modular pipeline** for:
- Data acquisition
- Data processing
- Rendering
- Dissemination (export, publishing)

The project supports **educators, researchers, and developers** who need reproducible, extensible workflows.

- **Language:** Python 3.10+  
- **Package Manager:** [Poetry](https://python-poetry.org/)  
- **Containerization:** Docker / Docker Compose  
- **Linting/Formatting:** Ruff + Pre-commit hooks  
- **Tests:** Pytest  

---

## Environment & Build Instructions

### Bootstrap
- Always use **Poetry** for dependency management.
- Run:
  ```bash
  poetry install
  ```
- This creates the virtual environment and installs dependencies from `pyproject.toml` + `poetry.lock`.

### Build & Run
- Build is managed via Poetry:
  ```bash
  poetry build
  ```
- Run Zyra inside Poetry shell:
  ```bash
  poetry shell
  python -m zyra
  ```

### Tests
- Tests are located in `tests/`.
- Always run via Poetry:
  ```bash
  poetry run pytest
  ```

### Lint & Formatting
- Ruff is configured in `ruff.toml`.
- Run:
  ```bash
  poetry run ruff check .
  poetry run ruff format .
  ```
- Pre-commit is configured in `.pre-commit-config.yaml`:
  ```bash
  pre-commit install
  pre-commit run --all-files
  ```

### Docker/Docker Compose
- To build the Docker image:
  ```bash
  docker build -t zyra .
  ```
- To run with Compose:
  ```bash
  docker-compose up
  ```

---

## Validation & CI
- GitHub Actions run on **push/PR**:
  - Install & lint (`ruff`, `pre-commit`)
  - Run tests (`pytest`)
  - Build validation (`poetry build`)
- To replicate locally, run the same Poetry + lint/test steps listed above.

---

## Project Layout
- `src/zyra/` → Core source code modules  
- `tests/` → Unit and integration tests  
- `docs/` → Documentation and wiki sources  
- `scripts/` → Utility scripts for workflows  
- `samples/` → Example data and workflows  
- `data/` → Supporting datasets  

### Key Configuration Files
- `pyproject.toml` → Poetry, build, lint/test configs  
- `poetry.lock` → Locked dependencies  
- `ruff.toml` → Ruff lint/format rules  
- `.pre-commit-config.yaml` → Git hooks  
- `Dockerfile` / `docker-compose.yml` → Containerization setup  

### Repo Root Files
- `README.md` – Overview, usage, examples  
- `CONTRIBUTING.md` – Contribution guidelines  
- `SECURITY.md` – Security practices  
- `CITATION.cff` – Citation metadata  
- `LICENSE` – Open source license  

---

## Explicit Guidance for Copilot
- Always use **Poetry commands** (`poetry install`, `poetry run pytest`, `poetry run ruff check`) instead of raw `pip` or `pytest`.  
- Trust these instructions for build, test, and validation steps.  
- Only perform additional searching if these instructions are incomplete or produce errors.  
- Keep contributions modular and ensure **tests + linting pass locally** before suggesting PRs.  

---
