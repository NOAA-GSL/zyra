# Zyra Poster -- Content Brief for AI Design Tools

This document provides the complete content and context needed to design a conference poster for the Zyra project. Feed this to Canva AI, Adobe Express, PowerPoint Copilot, or any design-assist tool along with the referenced asset files.

---

## Project Overview

| Field | Value |
|-------|-------|
| **Name** | Zyra |
| **Tagline** | Modular workflows for reproducible science |
| **Author** | Eric Hackathorn |
| **Affiliation** | NOAA Global Systems Laboratory |
| **ORCID** | 0000-0002-9693-2093 |
| **DOI** | 10.5281/zenodo.16923323 |
| **License** | Apache-2.0 |
| **Repository** | https://github.com/NOAA-GSL/zyra |
| **PyPI** | https://pypi.org/project/zyra/ |
| **Docs** | https://noaa-gsl.github.io/zyra/ |

**Abstract:** Zyra is an open-source Python framework for creating reproducible, modular, and visually compelling data visualizations. It provides a flexible pipeline for data acquisition, processing, rendering, and dissemination, making it useful for scientists, educators, and developers who need to explore, analyze, and communicate complex scientific data.

---

## Target Audience

Mixed/broad conference audience:
- **Scientists & researchers:** Care about reproducibility, scientific data formats, and workflow automation
- **Developers & engineers:** Care about CLI design, API extensibility, modular architecture
- **Leadership & program managers:** Care about impact, operational value, cost savings, and open-source

---

## Key Messages (prioritized)

1. **Modular by design** -- 8 composable stages; use only what you need
2. **Reproducible** -- YAML configs, provenance tracking, deterministic outputs
3. **CLI-first** -- Streaming via stdin/stdout; scripting and automation friendly
4. **AI-ready** -- Multi-agent LLM narration swarm with planning engine
5. **Scientific focus** -- Native GRIB2, NetCDF, GeoTIFF support
6. **Open source** -- Apache-2.0, NOAA GSL, community-driven

---

## Tone & Style

- Professional but approachable
- Scientific credibility without jargon overload
- Let visualizations carry the message
- Clean, modern, data-forward design
- Government + open-source credibility

---

## Poster Layout (10 Sections)

### Section 1: Header (full width, top)
Title, logo, author, badges. See `section-prompts/01-header.md`.

### Section 2: The Challenge (full width or left column)
2-3 sentences on the problem Zyra solves. See `section-prompts/02-challenge.md`.

### Section 3: The Pipeline (full width, central/prominent)
8-stage pipeline diagram + compact table. This is the hero visual. See `section-prompts/03-pipeline.md`.

### Section 4: HRRR Weather Use Case (half column)
CLI code snippet + heatmap image. See `section-prompts/04-hrrr.md`.

### Section 5: Drought Pipeline Use Case (half column)
DAG diagram + swarm command. See `section-prompts/05-drought.md`.

### Section 6: AI/LLM Narration Use Case (half column)
Orchestration diagram + provider table. See `section-prompts/06-narration.md`.

### Section 7: Reproducible Pipelines (half column)
YAML config example + dry-run capability. See `section-prompts/07-pipelines.md`.

### Section 8: Visualization Gallery (full width)
2x2 grid of generated images. See `section-prompts/08-gallery.md`.

### Section 9: Key Features (half column or sidebar)
Bullet list of capabilities. See `section-prompts/09-features.md`.

### Section 10: Get Started (bottom, full width)
Install command, resource links, optional QR code. See `section-prompts/10-get-started.md`.

---

## Available Assets

### Logo
- `poster/assets/branding/zyra-logo.png` -- Primary logo (tree with roots)

### Generated Visualizations
- `poster/assets/generated/heatmap.png` -- Scalar heatmap with colorbar and basemap
- `poster/assets/generated/contour.png` -- Filled contour plot with colorbar and basemap
- `poster/assets/generated/vector.png` -- Vector field quiver plot with basemap
- `poster/assets/generated/timeseries.png` -- Time series line chart

### Diagrams (Mermaid source -- render or recreate in design tool)
- `poster/assets/diagrams/pipeline_architecture.mmd` -- 8-stage pipeline flow
- `poster/assets/diagrams/drought_dag.mmd` -- Drought animation DAG
- `poster/assets/diagrams/swarm_orchestration.mmd` -- AI swarm orchestration flow

### Brand Reference
- `poster/assets/branding/zyra-colors.json` -- Color tokens (JSON)
- `poster/assets/branding/zyra-palette.gpl` -- GIMP palette file
- `poster/ai-context/design-system-guide.md` -- Full brand guidelines

---

## Design Constraints

- **Poster size:** 48" x 36" landscape (standard conference)
- **Readability:** Body text readable from 4 feet away
- **Printing:** Ensure all colors work in CMYK
- **Accessibility:** Maintain WCAG AA contrast ratios; do not rely on color alone
- **Branding:** Must include NOAA GSL attribution
