# Zyra

[![PyPI version](https://img.shields.io/pypi/v/zyra.svg)](https://pypi.org/project/zyra/) [![Docs](https://img.shields.io/badge/docs-GitHub_Pages-0A7BBB)](https://noaa-gsl.github.io/zyra/) [![Chat with Zyra Assistant](https://img.shields.io/badge/ChatGPT-Zyra%20Assistant-00A67E?logo=openai&logoColor=white)](https://chatgpt.com/g/g-6897a3dd5a7481918a55ebe3795f7a26-zyra-assistant) [![DOI](https://zenodo.org/badge/854215643.svg)](https://doi.org/10.5281/zenodo.16923322)

[![Zyra Presentation](https://github.com/user-attachments/assets/24b250cd-f4f1-4f47-a378-abba43af253d)](https://docs.google.com/presentation/d/1hdB2qLgzdiHQUzB3u_Mv2gU1wdh8xbcWsOh-dXjz9ME/present?usp=sharing)

Zyra is an open-source Python framework for modular, reproducible data workflows — helping you import, process, visualize, and export scientific and environmental data.

## Highlights
- **Modular pieces:** connectors, processors, visualizers, and utilities.
- **CLI-first & streaming-friendly:** compose stages with pipes and configs.
- **Install what you need:** keep core small; add extras per stage.

## Quickstart

Install

```
pip install zyra
```

Try the CLI

```
zyra --help
```

Minimal example

```
# Acquire → Process → Visualize
zyra acquire http https://example.com/sample.grib2 -o sample.grib2
zyra process convert-format sample.grib2 netcdf --stdout > sample.nc
zyra visualize heatmap --input sample.nc --var VAR --output plot.png
```

### More Examples per Module

See module-level READMEs under `src/zyra/` for focused examples and options:
- Connectors/Ingest: `src/zyra/connectors/ingest/README.md`
- Processing: `src/zyra/processing/README.md`
- API (service): `src/zyra/api/README.md`
- MCP Tools: `src/zyra/api/mcp_tools/README.md`

## Learn More (Wiki)
- Getting Started: https://github.com/NOAA-GSL/zyra/wiki/Getting-Started-with-Zyra
- Workflow Stages: https://github.com/NOAA-GSL/zyra/wiki/Workflow-Stages
- Stage Examples: https://github.com/NOAA-GSL/zyra/wiki/Stage-Examples
- Install & Extras: https://github.com/NOAA-GSL/zyra/wiki/Install-Extras
- Pipeline Patterns: https://github.com/NOAA-GSL/zyra/wiki/Pipeline-Patterns
- Containers Overview: https://github.com/NOAA-GSL/zyra/wiki/Zyra-Containers-Overview-and-Usage
- API Routers & Endpoints: https://github.com/NOAA-GSL/zyra/wiki/Zyra-API-Routers-and-Endpoints
 - Zyra Assistant Instructions: https://github.com/NOAA-GSL/zyra/wiki/Zyra-Assistant-Instructions

## Stage Map
- Overview: https://github.com/NOAA-GSL/zyra/wiki/Workflow-Stages

### Import (acquire/ingest)
- Docs: https://noaa-gsl.github.io/zyra/api/zyra.connectors.html
- Examples: https://github.com/NOAA-GSL/zyra/wiki/Stage-Examples

### Process (transform)
- Docs: https://noaa-gsl.github.io/zyra/api/zyra.processing.html
- Examples: https://github.com/NOAA-GSL/zyra/wiki/Stage-Examples

### Simulate
- Examples: https://github.com/NOAA-GSL/zyra/wiki/Stage-Examples

### Decide (optimize)
- Roadmap: https://github.com/NOAA-GSL/zyra/wiki/Roadmap-and-Tracking

### Visualize (render)
- Docs: https://noaa-gsl.github.io/zyra/api/zyra.visualization.html
- Examples: https://github.com/NOAA-GSL/zyra/wiki/Stage-Examples

### Narrate
- Roadmap: https://github.com/NOAA-GSL/zyra/wiki/Roadmap-and-Tracking

### Verify
- Roadmap: https://github.com/NOAA-GSL/zyra/wiki/Roadmap-and-Tracking

### Export (disseminate; legacy: decimate)
- Docs: https://noaa-gsl.github.io/zyra/api/zyra.connectors.html
- Examples: https://github.com/NOAA-GSL/zyra/wiki/Stage-Examples

## API & Reference Docs
- GitHub Pages: https://noaa-gsl.github.io/zyra/
- CLI reference: https://noaa-gsl.github.io/zyra/api/zyra.cli.html
- Modules:
  - Connectors: https://noaa-gsl.github.io/zyra/api/zyra.connectors.html
  - Processing: https://noaa-gsl.github.io/zyra/api/zyra.processing.html
  - Visualization: https://noaa-gsl.github.io/zyra/api/zyra.visualization.html
  - Transform: https://noaa-gsl.github.io/zyra/api/zyra.transform.html
  - Utils: https://noaa-gsl.github.io/zyra/api/zyra.utils.html
  - API (service): https://noaa-gsl.github.io/zyra/api/zyra.api.html

## Contributing
- Guide: [CONTRIBUTING.md](CONTRIBUTING.md)
- Discussions: https://github.com/NOAA-GSL/zyra/discussions
- Issues: https://github.com/NOAA-GSL/zyra/issues

## License
Apache-2.0 — see LICENSE
