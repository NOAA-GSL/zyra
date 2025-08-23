# Contributing to Zyra

Thanks for your interest in contributing!  
This project thrives on community contributions, and we welcome improvements of all kinds.

---

## License and Contributor Terms

- Zyra is licensed under the MIT License. See `LICENSE` at the repository root.
- By submitting a pull request, issue suggestion, or any code/documentation/artwork (“Contribution”),
  you agree to license your Contribution under the MIT License, and you represent that you have the
  right to do so.
- Do not contribute code or assets you don’t have rights to. If you include third‑party code or data,
  ensure it is compatible with MIT and include proper attribution as required by the original license.
- No CLA is required at this time; contributions are accepted under the project’s MIT terms.

If you have questions about licensing or attribution, please open an issue before submitting your PR.

---

## Branching Workflow

To keep development organized, we use a two-branch model:

- **`main`** → Stable, production-ready branch.  
  - Always passes tests and CI/CD.  
  - Used for tagged releases.  
  - Do **not** commit directly to `main`.

- **`staging`** → Integration branch.  
  - Collects feature branches and fixes before merging into `main`.  
  - Used for testing, docs, and CI validation.  

### Rules
1. **Feature Development**
   - Branch off `staging`:  
     ```bash
     git checkout staging
     git pull origin staging
     git checkout -b feature/my-feature
     ```
   - Open a Pull Request (PR) into `staging`.

2. **Testing & Integration**
   - PRs are merged into `staging`.  
   - CI/CD runs against `staging`.  
   - Once stable, `staging` is merged into `main`.  

3. **Syncing Main & Staging**
   - Occasionally merge `main → staging` to keep hotfixes and metadata aligned.  
   - Always merge `staging → main` via PR when ready to release.

---

## Workflow Gap Issues & PRs

Zyra now uses structured **Workflow Gap** issue and PR templates to ensure new CLI functionality is properly tracked.

### Filing Bug Reports
- Use the `🐞 Bug Report` template (`.github/ISSUE_TEMPLATE/bug_report.md`).
- Provide clear steps to reproduce, expected vs. actual behavior, and environment details.

### Filing Feature Requests
- Use the `✨ Feature Request` template (`.github/ISSUE_TEMPLATE/feature_request.md`).
- Describe the feature, motivation, proposed solution, and alternatives.
- Use this template only for enhancements that do **not** map directly to CLI commands.


### Filing Workflow Gap Issues
- Use the `⚡ Workflow Gap / Missing Command` template (`.github/ISSUE_TEMPLATE/workflow_gap.md`).
- Clearly describe:
  - Which CLI commands exist today
  - What is missing
  - Why the feature is needed
- The template will guide you to include an implementation plan and examples.

### Submitting PRs for Workflow Gaps
- All PRs that add CLI functionality should link to the related Workflow Gap issue.
- The PR template (`.github/PULL_REQUEST_TEMPLATE.md`) includes a checklist:
  - Add tests
  - Write comprehensive **docstrings** (for auto-generated docs)
  - Include examples in workflows
- Ensure all boxes are checked before requesting review.

By following these templates, contributors help keep Zyra’s CLI aligned with real workflows and ensure documentation stays accurate and reproducible.

---

## Code Style

- Python 3.10+ required.  
- Follow [PEP8](https://peps.python.org/pep-0008/).  
- Run `ruff` and `pytest` locally before opening a PR.

---

## Testing

1. Install dev dependencies:
   ```bash
   poetry install
   ```
2. Run tests:
   ```bash
   pytest
   ```

---

## Pull Requests

- Make sure your branch is up-to-date with `staging`.  
- Include descriptive commit messages.  
- Request a review from at least one maintainer.  

---

## Releases

- Releases are tagged from `main`.  
- `staging` must be fully merged into `main` before tagging.

---

Thanks again for contributing!
