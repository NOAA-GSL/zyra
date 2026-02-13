# Zyra Design System Guide

This document provides brand guidelines for AI-powered design tools (Canva, Adobe Express, PowerPoint Copilot, Figma AI, etc.) when creating visual materials for the Zyra project.

---

## Brand Identity

**Project:** Zyra
**Organization:** NOAA Global Systems Laboratory (GSL)
**Tagline:** Modular workflows for reproducible science
**Logo:** Tree with roots motif -- symbolizes growth, branching workflows, and deep data roots
**Tone:** Professional, accessible, scientific but approachable. Balances government credibility with modern open-source energy.

---

## Color Palette

### Primary Colors
| Name | Hex | RGB | Usage |
|------|-----|-----|-------|
| Navy | `#00172D` | 0, 23, 45 | Headings, primary text, backgrounds |
| Ocean Blue | `#1A5A69` | 26, 90, 105 | Secondary headings, links, accent elements |
| Cable Blue | `#00529E` | 0, 82, 158 | Call-to-action buttons, highlighted items |

### Accent Colors
| Name | Hex | RGB | Usage |
|------|-----|-----|-------|
| Seafoam | `#5F9DAE` | 95, 157, 174 | Borders, secondary accents, lighter UI elements |
| Mist | `#9AB2B1` | 154, 178, 177 | Subtle backgrounds, dividers |
| Deep Teal | `#091A1B` | 9, 26, 27 | Dark backgrounds, footer areas |

### Earth Tones
| Name | Hex | RGB | Usage |
|------|-----|-----|-------|
| Leaf Green | `#2C670C` | 44, 103, 12 | Success states, "implemented" indicators, nature themes |
| Olive | `#576216` | 87, 98, 22 | Secondary earth accent, visualization stage |
| Soil | `#50452C` | 80, 69, 44 | Grounding elements, footer backgrounds |

### Semantic Colors
| Name | Hex | RGB | Usage |
|------|-----|-----|-------|
| Amber | `#FFC107` | 255, 193, 7 | Warnings, highlights, attention markers |
| Red | `#F44336` | 244, 67, 54 | Errors, critical alerts |

### Neutrals
| Name | Hex | RGB | Usage |
|------|-----|-----|-------|
| Neutral 900 | `#232323` | 35, 35, 35 | Body text |
| Neutral 700 | `#8B8985` | 139, 137, 133 | Secondary text |
| Neutral 600 | `#A3A29D` | 163, 162, 157 | Muted text, placeholders |
| Neutral 400 | `#D8D7D3` | 216, 215, 211 | Borders, dividers |
| Neutral 200 | `#F7F5EE` | 247, 245, 238 | Light backgrounds |
| Neutral 50 | `#FEFEFE` | 254, 254, 254 | White/canvas |

---

## Typography

### Recommendations
- **Headings:** Clean sans-serif (e.g., Inter, Source Sans Pro, Roboto, or system defaults). Bold weight.
- **Body text:** Same sans-serif family, regular weight, for readability.
- **Code snippets:** Monospace (e.g., JetBrains Mono, Fira Code, Source Code Pro, Consolas).
- **Size hierarchy:** Title 36-48pt, Section headers 24-28pt, Body 14-16pt, Code 12-14pt (for poster at standard conference size).

### Code Block Styling
- Background: `#F7F5EE` (Neutral 200)
- Border: `#D8D7D3` (Neutral 400)
- Text: `#232323` (Neutral 900)
- Keywords/commands: `#00529E` (Cable Blue) or `#1A5A69` (Ocean Blue)

---

## Logo Usage

- **Primary logo:** `poster/assets/branding/zyra-logo.png` -- tree with roots design
- **Minimum size:** 100px width for digital, 1 inch for print
- **Clear space:** Maintain at least the height of the "Z" in "Zyra" around the logo
- **On dark backgrounds:** Use the light variant of the logo
- **On light backgrounds:** Use the standard logo
- **Do not:** Stretch, rotate, add effects, or change logo colors

---

## Visual Style Guidelines

1. **Clarity** -- Simple, legible, accessible visuals. Prefer whitespace over clutter.
2. **Openness** -- Collaborative tone. Use open-source badges and links prominently.
3. **NOAA Identity** -- Respect NOAA's visual language while keeping Zyra distinct and modern.
4. **Data-forward** -- Let visualizations (maps, charts, diagrams) be the hero elements.
5. **Modular feel** -- Use grid layouts and card-based sections to reflect the modular pipeline.

---

## Poster Dimensions

- **Standard conference poster:** 48" x 36" (landscape) or 42" x 30"
- **Digital/web version:** 1920px wide or responsive Markdown (the README.md)
- **Orientation:** Landscape preferred for conference display

---

## Color Palette File References

- **JSON tokens:** `poster/assets/branding/zyra-colors.json`
- **GIMP palette:** `poster/assets/branding/zyra-palette.gpl`
