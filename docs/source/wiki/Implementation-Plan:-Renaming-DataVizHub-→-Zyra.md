This document outlines the detailed steps required to rename the **DataVizHub** project to **Zyra**, covering codebase, documentation, packaging, and community communication.

---

## 1. Repository & GitHub Setup
- [x] Rename GitHub repository: `NOAA-GSL/datavizhub` → `NOAA-GSL/zyra`.
- [x] Update repository **description** and **topics**.
- [x] Ensure GitHub redirects work; test links to old repo.
- [x] Update branch protection rules if they reference `datavizhub`.

---

## 2. Codebase Changes
### 2.1 Core Package
- [ ] Rename `src/datavizhub/` → `src/zyra/`.
- [ ] Update all imports:
  ```python
  from datavizhub.module import X
  ```
  ➝
  ```python
  from zyra.module import X
  ```

### 2.2 Compatibility Shim
- [ ] Add `src/datavizhub/__init__.py`:
  ```python
  import warnings
  from zyra import *

  warnings.warn(
      "The 'datavizhub' package has been renamed to 'zyra'. Please update your imports.",
      DeprecationWarning
  )
  ```

### 2.3 Configuration
- [ ] Update `pyproject.toml`:
  - `name = "zyra"`
  - `packages = [{ include = "zyra", from = "src" }]`
  - Update CLI scripts:
    ```toml
    [tool.poetry.scripts]
    zyra = "zyra.cli:main"
    zyra-cli = "zyra.api_cli:main"
    ```
  - Update homepage, source, and tracker URLs.
- [ ] Update `poetry.lock` (regenerate).
- [ ] Update Dockerfile, docker-compose.yml if names/tags reference `datavizhub`.

---

## 3. Documentation Updates
- [ ] Update `README.md` (title, usage examples, badges).
- [ ] Update `/docs/` and `/docs/source/wiki/` references.
- [ ] Update `CONTRIBUTING.md`, `SECURITY.md`, and other policy docs.
- [ ] Update code examples and tutorials.

---

## 4. Tests
- [ ] Add compatibility shim (ensures tests still pass with old `datavizhub` imports).
- [ ] Gradually refactor tests to import `zyra`.
- [ ] Update CLI-related tests:
  - `datavizhub` → `zyra`
  - `datavizhub-cli` → `zyra-cli`
- [ ] Remove shim after at least one stable release cycle.

---

## 5. Packaging & Distribution
- [ ] Publish `zyra` to PyPI.
- [ ] Optionally, keep a deprecated `datavizhub` PyPI package that depends on `zyra` and shows deprecation warning.
- [ ] Update Docker image tags (e.g., `zyra:latest`).
- [ ] Update conda-forge recipe if applicable.

---

## 6. Community & Communication
- [ ] Announce rename in GitHub Discussions.
- [ ] Post migration notice in `README.md`:
  > Project renamed: DataVizHub → Zyra. Please update your imports. Old namespace remains supported until [date].
- [ ] Notify contributors in active PRs/issues.
- [ ] Update Zenodo DOI / citation if needed.

---

## 7. Migration Timeline
1. **Phase 1 (Compatibility)**: Introduce `zyra`, keep `datavizhub` shim. Announce rename.
2. **Phase 2 (Transition)**: Update docs, tests, and examples to use `zyra` exclusively.
3. **Phase 3 (Deprecation)**: Remove `datavizhub` shim and deprecated PyPI package after at least one release cycle.

---

## 8. Verification
- [ ] Run full test suite after renaming.
- [ ] Build documentation locally.
- [ ] Validate CLI commands (`zyra` and `zyra-cli`).
- [ ] Confirm PyPI and Docker distributions work.

---

## Deliverables
- Updated repo with `zyra` as main package.
- Compatibility shim for smooth transition.
- Migration guide in `README.md`.
- Community announcement in Discussions.

