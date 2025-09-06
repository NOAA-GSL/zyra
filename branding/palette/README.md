# Zyra Palettes

Shared color palettes for branding and visualization. A text-based palette (`.gpl`) is provided for portability. You can also export/import app-native palettes (e.g., `.ase`, `.aco`) as needed.

## Files

- `zyra-palette.gpl` — GIMP palette format (text, readable in many tools).
- Optionally add: `zyra-palette.ase` (Adobe Swatch Exchange), `zyra-palette.aco` (Photoshop), Affinity palettes, etc. These will be tracked via Git LFS automatically.

## Suggested Base Colors

The starter palette includes neutrals and NOAA-inspired blues/teals with accessible, high-contrast options for UI and docs.

## Usage

- Figma/Sketch: import the `.gpl` via a converter (e.g., SwatchBooker or online converters) to `.ase`.
- Adobe (Illustrator/Photoshop): import `.ase` directly. Use a converter to produce `.ase` from the provided `.gpl` if needed.
- Affinity: import `.afpalette` or `.ase`. Export from your tool and commit the file here if you want to share it.

## Converting

- Convert `.gpl` → `.ase` via: SwatchBooker (desktop), ImageMagick-based scripts, or online tools.
- When exporting app-native palette files, keep names consistent (e.g., `zyra-palette.ase`).

## Notes

- Commit only public, license‑compatible palettes.
- For docs/web usage, prefer CSS variables or inline styles derived from these swatches rather than embedding app-native files.

