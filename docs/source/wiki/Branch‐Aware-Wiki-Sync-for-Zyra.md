## Goals
- Mirror the **GitHub Wiki** into `docs/wiki/`.
- Make wiki pages part of the **Sphinx site**.
- Ensure **contributors in feature branches** can build docs with up-to-date wiki.
- Keep commit history clean: **sync commits only happen in `main`**.
- Remove **Docker-based wiki sync** to simplify builds.

---

## 1. Add Branch-Aware GitHub Action for Wiki Sync

Create `.github/workflows/sync-wiki.yml`:

```yaml
name: Sync Wiki to Docs

on:
  push:
    branches:
      - "**"          # Run on all branches
  pull_request:        # Ensure PR builds include wiki
  schedule:
    - cron: "0 6 * * *"  # Daily sync at 6 AM UTC
  workflow_dispatch:    # Manual trigger

jobs:
  sync-wiki:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout main repo
        uses: actions/checkout@v4
        with:
          path: main

      - name: Checkout wiki repo
        uses: actions/checkout@v4
        with:
          repository: NOAA-GSL/zyra.wiki
          path: wiki

      - name: Sync wiki into docs/wiki
        run: |
          rsync -av --delete wiki/ main/docs/wiki/

      - name: Commit wiki changes (main only)
        run: |
          cd main
          if [ "$GITHUB_REF_NAME" = "main" ]; then
            git config user.name "github-actions[bot]"
            git config user.email "github-actions[bot]@users.noreply.github.com"
            git add docs/wiki/
            if ! git diff --cached --quiet; then
              git commit -m "chore(docs): sync wiki into docs/wiki"
              git push
            else
              echo "No changes to commit"
            fi
          else
            echo "Skipping commit: branch is $GITHUB_REF_NAME"
          fi
```

On feature branches and PRs: wiki is **synced locally** so docs build works.  
On `main`: wiki changes are **committed and pushed**.

---

## 2. Update Sphinx to Support Wiki Pages

In `docs/source/conf.py`:

```python
extensions = [
    "myst_parser",              # Enables Markdown
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
]

source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}
```

Install `myst-parser` via Poetry or pip.

---

## 3. Add Wiki to Docs Site Navigation

In `docs/source/index.rst`:

```rst
Welcome to Zyra's Documentation
=====================================

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   api/index
   wiki/index
   contributing/wiki-sync
```

Create `docs/wiki/index.md`:

```markdown
# Zyra Wiki

This section mirrors the official [GitHub Wiki](https://github.com/NOAA-GSL/zyra/wiki).

Contents are synced automatically.
```

---

## 4. Add Contributor Documentation

Create `docs/source/contributing/wiki-sync.md`:

```markdown
# Wiki Sync Workflow

## Why
- Ensures wiki knowledge is AI-accessible.
- Keeps docs version-controlled with code.
- Removes duplication between Docker and CI.

## How
- GitHub Action syncs wiki â `docs/wiki/`.
- Sphinx builds wiki pages into the docs site.
- Commits only happen on `main`.

## Editing Rules
- Edit via the GitHub Wiki â synced to repo on next run.
- Do not edit `docs/wiki/` directly (overwritten on sync).
```

---

## 5. Remove Docker-Based Wiki Sync
- Delete wiki fetch steps from `Dockerfile`.
- Ensure `docs/wiki/` is not ignored in `.dockerignore`.
- Containers now build purely from repo contents.

---

## 6. Verify End-to-End
1. Run workflow manually (`workflow_dispatch`).
2. Confirm `docs/wiki/` populated in branch builds.
3. Merge to `main` â verify wiki commit appears.
4. Build docs (`make html`) â wiki pages visible.
5. Confirm container builds still include synced docs.

---

## Deliverables
1. `.github/workflows/sync-wiki.yml` (branch-aware).
2. Updated `conf.py` with `myst_parser`.
3. Updated `index.rst` with wiki & contributing guide.
4. `docs/wiki/index.md` entrypoint.
5. `docs/source/contributing/wiki-sync.md` contributor guide.
6. `Dockerfile` cleaned of wiki sync logic.

---

## Benefits
- Always up-to-date wiki in every branch.
- Clean commit history (sync commits only in `main`).
- Docs site integrates wiki automatically.
- Simplified container builds.
- AI assistants can read wiki content directly from repo.