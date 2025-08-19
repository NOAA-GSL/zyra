# Wiki Sync Workflow

## Why
- Keeps wiki knowledge versioned with code for branches and PRs.
- Ensures contributors can build docs with up-to-date wiki content.
- Simplifies builds by removing Docker-based wiki mirroring.

## How
- A GitHub Action syncs the GitHub Wiki into `docs/source/wiki/` on pushes, PRs, and a daily schedule.
- Sphinx (with `myst_parser`) builds Markdown wiki pages alongside the docs.
- Commits of wiki changes occur only on `main` to keep history clean.

## Editing Rules
- Edit wiki pages via the GitHub Wiki UI.
- Do not edit `docs/source/wiki/` directly; it is overwritten on sync.
