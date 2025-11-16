This document explains the end-to-end lifecycle of contributions to Zyra, from research and idea exploration through code, documentation, and pull requests. It integrates details from the official CONTRIBUTING guide.

---

## 1. Research & Discovery

- **Where:** Papers, datasets, GitHub Discussions, Zyra Wiki.
- **Purpose:** Identify gaps, validate ethical/educational impact, and survey existing CLI commands.
- **Tools:**
  - [`zyra_capabilities/`](https://github.com/NOAA-GSL/zyra/tree/main/src/zyra/wizard/zyra_capabilities) → canonical per-domain manifest files (see `zyra_capabilities_index.json` for aliases).
  - [`zyra_capabilities.json`](https://github.com/NOAA-GSL/zyra/blob/main/src/zyra/wizard/zyra_capabilities.json) → legacy merged manifest (still updated for compatibility).
  - [Issues](https://github.com/NOAA-GSL/zyra/issues) → see if bugs or enhancements are already reported.
  - [Discussions](https://github.com/NOAA-GSL/zyra/discussions) → explore community design threads.

---

## 2. Idea & Proposal

- **Where:**
  - **Discussions** → for philosophy/design.
  - **Issues** → for bugs, features, or workflow gaps.
- **Templates:**
  - Bug Report → label: `bug`.
  - Feature Request → label: `enhancement`.
  - Workflow Gap → labels: `workflow-gap`, `enhancement`.

---

## 3. Branching Model

- **`main`****:** Stable, production-ready branch. Always passes CI/CD.
- **`staging`****:** Integration branch for feature testing before promotion to `main`.
- **Feature branches:**
  - Create a branch from `staging`, e.g. `feature/my-feature`.
  - Merge into `staging` once complete, tested, and reviewed.
  - Maintainers later promote `staging` → `main` for release.

---

## 4. Code Development

- **Pipeline Alignment:** Follow Zyra’s modular stages (acquisition → processing → rendering → dissemination).
- **CLI Manifest:** Update `zyra_capabilities.json` if introducing a new command.
- **Tests:** Add unit + integration tests (`pytest`).
- **Examples:** Provide runnable workflows demonstrating new functionality.
- **Commit Quality:**
  - Clear commit messages, linked to issue/discussion.
  - Must include a **Signed-off-by** line (Developer Certificate of Origin).\
    Example: `Signed-off-by: Jane Doe <jane.doe@example.com>`
- **Optional AI Assistance:** Code contributions may optionally be developed using generative AI tools such as OpenAI Codex, Claude Code, or GitHub Copilot. Any AI-assisted code must still meet Zyra’s standards for clarity, reproducibility, and documentation.

---

## 5. Documentation

### **Two Categories:**

1. **Docstrings (auto-generated):**

   - Required for all functions, classes, and CLI commands.
   - Auto-generated into reference docs via Sphinx/pdoc.

2. **Wiki Content (conceptual, educational):**

   - Update directly in the [Zyra GitHub Wiki](https://github.com/NOAA-GSL/zyra/wiki).
   - Examples: tutorials, best practices, roadmap.

> ⚠️ The `docs/source/wiki/` folder in the repo is a **read-only mirror** of the Wiki. Do **not** edit it directly in PRs.

---

## 6. Pull Request (PR)

- **Where:** GitHub → from contributor branch into `staging`.
- **Requirements:**
  - Link to related issue/discussion.
  - Passing CI (tests, linting, docs build).
  - Updated docstrings and/or Wiki entry.
  - Clear changelog entry.
  - Signed-off-by line in each commit.

---

## 7. Review & Merge

- **Reviewers:** Community + maintainers.
- **Checklist:**
  - Alignment with Zyra values (reproducible, modular, educational).
  - Tests + docs included.
  - No direct edits to `/docs/source/wiki`.
  - Commits include Signed-off-by lines.
- **Outcome:** PR merged into `staging` → promoted to `main` in release cycle.

---

## Example End-to-End Flow

1. Researcher notices a gap in comparing datasets.
2. Posts idea in **Discussion** → refined into a **Feature Request** issue.
3. Contributor codes new `zyra compare` command, updates docstrings, adds tests + examples.
4. Wiki entry added with tutorial.
5. PR submitted into `staging`, CI passes, reviewers approve.
6. PR merged → later promoted to `main` for release.

