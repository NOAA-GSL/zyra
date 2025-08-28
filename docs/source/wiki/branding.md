---
title: Zyra Branding and Mood Board
---

# Zyra Branding and Mood Board

This page tracks the branding mood board and links to assets while keeping draft work separate from public, curated files.

## Directory Structure

- Draft/WIP assets: `branding/moodboard/`
- Curated docs assets: `docs/source/_static/branding/`

Draft assets are the working area for experiments and references. Only copy approved items into the curated `_static/branding/` folder for the docs site.

## Getting Started

1. Add inspirations, references, and early explorations to `branding/moodboard/`.
2. When an asset is ready for broad consumption, copy it into `docs/source/_static/branding/`.
3. Update this page with short notes and links so others can find the latest.

## Guiding Themes

- Clarity: simple, legible, and accessible visuals.
- Openness: collaborative tone, transparent process, and remix-friendly assets.
- NOAA identity: respect NOAA’s visual language while keeping Zyra distinct and modern.

## Asset Links

- Draft mood board assets: `branding/moodboard/`
- Curated/public assets for docs: `docs/source/_static/branding/`
- Palettes (text + app-native formats): `branding/palette/`

> Note: heavy image formats (`*.png`, `*.jpg`, `*.jpeg`, `*.gif`) are tracked via Git LFS per repository settings. Prefer compressed, web-ready formats for curated assets when feasible.

## Next Steps (Issue #81)

- [ ] Upload initial mood board images and references into `branding/moodboard/`.
- [ ] Document chosen palettes, type references, and logo directions here.
- [ ] Select and copy curated assets into `docs/source/_static/branding/`.
- [ ] Announce in a GitHub Discussion to gather feedback before publishing widely.
 - [ ] Export and share app-native palettes (`.ase`, `.aco`) alongside `zyra-palette.gpl`.

## Contributions

Please avoid committing secrets or absolute paths in linked files. Large binaries should be added thoughtfully to keep the repository lean; prefer thumbnails or compressed previews in the docs area.

## Using CSS Variables in Docs

The docs load a small stylesheet with Zyra color variables. You can reference them directly in Markdown (MyST) with inline HTML:

Example badge:

```html
<span class="zyra-badge">Preview</span>
```

Example colored block:

```html
<div style="background: var(--zyra-neutral-200); color: var(--zyra-blue); padding: 8px 12px; border-radius: 6px;">
  Zyra uses <code>var(--zyra-blue)</code> for primary accents.
  See <code>docs/source/_static/css/zyra-theme.css</code> for all variables.
  Machine-readable tokens: <code>docs/source/_static/branding/zyra-colors.json</code>.
  
</div>
```

