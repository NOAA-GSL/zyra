# Zyra Branding Workspace

This directory contains work-in-progress branding materials (mood boards, references, drafts). Curated, web‑optimized assets for the docs site belong in `docs/source/_static/branding/`.

## Structure

- `branding/moodboard/` — Raw inspirations, drafts, reference images, and exploration files.
- `branding/palette/` — Shared color palettes (text and app-native formats) and guidance.

## Contribution Guidelines

- Use descriptive filenames: `category_subject_variant_v1.ext` (e.g., `logo_wordmark_outline_v1.png`).
- Keep drafts here; copy only approved assets to `docs/source/_static/branding/`.
- Large binaries are tracked via Git LFS (see repo `.gitattributes`). Run `git lfs install` once locally.
- Prefer lossless or high-quality sources here; publish compressed, web‑ready derivatives in `_static/branding/`.

## File Size & Formats

- Source/design files (e.g., `*.psd`, `*.ai`, `*.indd`, `*.pptx`, `*.pdf`, `*.tif`) are LFS‑tracked.
- Docs site assets should be optimized (`*.webp`, `*.avif`, `*.png`, `*.jpg`) and remain under the pre‑commit size limit.
- Fonts: commit only if licensing permits. Prefer `*.woff2` in docs; keep `*.ttf/otf` here if needed.

## Publishing Flow

1. Add drafts to `branding/moodboard/`.
2. Select items for publication; export optimized copies and place in `docs/source/_static/branding/`.
3. Update `docs/source/wiki/branding.md` with links, brief notes, and thumbnails if helpful.

