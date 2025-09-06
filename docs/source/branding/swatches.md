# Zyra Color Swatches

A quick visual reference of the core Zyra palette using the CSS variables loaded by the docs theme.

<style>
.swatches { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 12px; }
.swatch { border: 1px solid #e0e0e0; border-radius: 8px; padding: 8px; background: #fff; }
.chip { height: 56px; border-radius: 6px; margin-bottom: 8px; border: 1px solid #ddd; }
.meta { font-size: 0.85em; line-height: 1.25; color: #333; }
.meta code { font-size: 0.85em; }
</style>

<div class="swatches">
  <div class="swatch">
    <div class="chip" style="background: var(--zyra-navy);"></div>
    <div class="meta"><strong>Navy</strong><br><code>--zyra-navy</code><br>#00172D</div>
  </div>
  <div class="swatch">
    <div class="chip" style="background: var(--zyra-blue);"></div>
    <div class="meta"><strong>Ocean Blue</strong><br><code>--zyra-blue</code><br>#1A5A69</div>
  </div>
  <div class="swatch">
    <div class="chip" style="background: var(--zyra-cable-blue);"></div>
    <div class="meta"><strong>Cable Blue</strong><br><code>--zyra-cable-blue</code><br>#00529E</div>
  </div>
  <div class="swatch">
    <div class="chip" style="background: var(--zyra-sky);"></div>
    <div class="meta"><strong>Seafoam</strong><br><code>--zyra-sky</code><br>#5F9DAE</div>
  </div>
  <div class="swatch">
    <div class="chip" style="background: var(--zyra-teal);"></div>
    <div class="meta"><strong>Deep Teal</strong><br><code>--zyra-teal</code><br>#091A1B</div>
  </div>
  <div class="swatch">
    <div class="chip" style="background: var(--zyra-teal-accent);"></div>
    <div class="meta"><strong>Mist</strong><br><code>--zyra-teal-accent</code><br>#9AB2B1</div>
  </div>
  <div class="swatch">
    <div class="chip" style="background: var(--zyra-green);"></div>
    <div class="meta"><strong>Leaf Green</strong><br><code>--zyra-green</code><br>#2C670C</div>
  </div>
  <div class="swatch">
    <div class="chip" style="background: var(--zyra-olive);"></div>
    <div class="meta"><strong>Olive</strong><br><code>--zyra-olive</code><br>#576216</div>
  </div>
  <div class="swatch">
    <div class="chip" style="background: var(--zyra-soil);"></div>
    <div class="meta"><strong>Soil</strong><br><code>--zyra-soil</code><br>#50452C</div>
  </div>
  <div class="swatch">
    <div class="chip" style="background: var(--zyra-amber);"></div>
    <div class="meta"><strong>Amber</strong><br><code>--zyra-amber</code><br>#FFC107</div>
  </div>
  <div class="swatch">
    <div class="chip" style="background: var(--zyra-red);"></div>
    <div class="meta"><strong>Red</strong><br><code>--zyra-red</code><br>#F44336</div>
  </div>
  <div class="swatch">
    <div class="chip" style="background: var(--zyra-neutral-900);"></div>
    <div class="meta"><strong>Neutral 900</strong><br><code>--zyra-neutral-900</code><br>#232323</div>
  </div>
  <div class="swatch">
    <div class="chip" style="background: var(--zyra-neutral-700);"></div>
    <div class="meta"><strong>Neutral 700</strong><br><code>--zyra-neutral-700</code><br>#8B8985</div>
  </div>
  <div class="swatch">
    <div class="chip" style="background: var(--zyra-neutral-600);"></div>
    <div class="meta"><strong>Neutral 600</strong><br><code>--zyra-neutral-600</code><br>#A3A29D</div>
  </div>
  <div class="swatch">
    <div class="chip" style="background: var(--zyra-neutral-400);"></div>
    <div class="meta"><strong>Neutral 400</strong><br><code>--zyra-neutral-400</code><br>#D8D7D3</div>
  </div>
  <div class="swatch">
    <div class="chip" style="background: var(--zyra-neutral-200);"></div>
    <div class="meta"><strong>Neutral 200</strong><br><code>--zyra-neutral-200</code><br>#F7F5EE</div>
  </div>
  <div class="swatch">
    <div class="chip" style="background: var(--zyra-neutral-50);"></div>
    <div class="meta"><strong>Neutral 50</strong><br><code>--zyra-neutral-50</code><br>#FEFEFE</div>
  </div>
</div>

Sources

- CSS variables: `docs/source/_static/css/zyra-theme.css`
- Tokens JSON: `docs/source/_static/branding/zyra-colors.json`
- Palette files: `branding/palette/`

### Contrast Legend

- AA (normal text): ratio >= 4.5:1
- AA (large text ≥ 18pt/14pt bold): ratio >= 3.0:1
- AAA (normal text): ratio >= 7.0:1

Each swatch shows contrast vs white (`#FFFFFF`) and vs Neutral 900 (`#232323`).
Badges indicate pass/fail for AA (normal) and AAA (normal). Use large-text threshold (3.0) for headings.

## Theme Toggle Demo

Use the toggle to preview components on light and dark backgrounds.

<p>
  <button id="demo-theme-toggle" class="btn outline">Toggle Theme (Light)</button>
</p>

<div id="demo-playground" class="demo light">
  <div class="group">
    <span class="btn primary">Primary (Cable Blue)</span>
    <span class="btn success">Success (Leaf Green)</span>
    <span class="btn outline">Outline (Ocean Blue)</span>
    <span class="btn dark">Dark (Navy)</span>
  </div>
  <div class="group">
    <span class="zyra-badge leaf">Leaf</span>
    <span class="zyra-badge cable">Cable</span>
    <span class="zyra-badge olive">Olive</span>
    <span class="zyra-badge soil">Soil</span>
    <span class="zyra-badge">Neutral</span>
  </div>
</div>

## Color Pairing Guidelines

- Dark backgrounds: use `--zyra-navy` with text `--zyra-neutral-50`; accents `--zyra-sky` or `--zyra-teal-accent` for subtle contrast.
- Light backgrounds: use `--zyra-neutral-50/200` with text `--zyra-neutral-900`.
- Primary CTA: `--zyra-cable-blue` on light backgrounds; on dark backgrounds, consider `--zyra-sky` for better contrast.
- Success/positive: `--zyra-green` (Leaf Green) on light backgrounds; use outline styles on dark if contrast is low.
- Warnings/errors: keep `--zyra-amber` and `--zyra-red` for status semantics, not brand accents.
- Earthy accents: `--zyra-olive` and `--zyra-soil` for secondary UI, dividers, or cards.

Aim for WCAG AA contrast (>= 4.5:1 for body text, 3:1 for large text). Prefer white (`#fff`) text on Cable Blue/Leaf Green; use `--zyra-neutral-900` on `--zyra-sky`.

## Foreground Recommendations

The table below recommends a foreground (text) color for each brand background, based on the highest available contrast and WCAG thresholds.

<div id="recommendations-table"></div>

## Example Components

Buttons

<p>
  <span class="btn primary">Primary (Cable Blue)</span>
  <span class="btn success">Success (Leaf Green)</span>
  <span class="btn outline">Outline (Ocean Blue)</span>
  <span class="btn dark">Dark (Navy)</span>
  <span class="zyra-badge leaf">Leaf</span>
  <span class="zyra-badge cable">Cable</span>
  <span class="zyra-badge olive">Olive</span>
  <span class="zyra-badge soil">Soil</span>
  <span class="zyra-badge">Neutral</span>
  
</p>
