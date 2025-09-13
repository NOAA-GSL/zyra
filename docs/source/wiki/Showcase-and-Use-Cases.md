# Showcase & Use Cases

A curated set of example scenarios showing how Zyra’s stages fit real workflows. Add links to repos, notebooks, and outputs as they become available.

Zyra Assistant
- The Zyra Assistant can help brainstorm and outline end‑to‑end workflows based on your goals (e.g., which stages to use, data and format choices, and example commands).
- It can also draft or submit GitHub Issues to request additional capabilities or improvements in Zyra.
- [![Chat with Zyra Assistant](https://img.shields.io/badge/ChatGPT-Zyra%20Assistant-00A67E?logo=openai&logoColor=white)](https://chatgpt.com/g/g-6897a3dd5a7481918a55ebe3795f7a26-zyra-assistant)
- Open issues: https://github.com/NOAA-GSL/zyra/issues

## Education
- Classroom weather maps
  - import: HTTP/S3 → sample GRIB2/NetCDF
  - process: convert to NetCDF; extract `T2M`
  - visualize: heatmap with labeled colorbar; optional animation
  - export: PNG/MP4 to local or S3
  - Example commands:
    - `zyra process convert-format sample.grib2 netcdf --stdout > sample.nc`
    - `zyra visualize heatmap --input sample.nc --var T2M --output t2m.png`

- Science On a Sphere (SOS)
  - import/process: prepare global imagery frames
  - visualize: animate frames; compose MP4
  - export: upload to Vimeo/S3 for distribution

## Research
- Model subset and analysis
  - import: grab a single variable/time slice from a model archive
  - process: subset and convert format for analysis
  - visualize: contour or vector plots; compare cases over time

- Event case studies
  - import/process: retrieve event windows (e.g., hurricanes)
  - visualize: time series and composite maps
  - narrate (planned): add captions and context
  - verify (planned): compute metrics and quality checks

## Operations
- Daily product generation
  - import: list/filter latest files from S3/FTP
  - process: transform → standardized NetCDF/GeoTIFF
  - visualize: generate PNGs and MP4s
  - export: push to object storage and web endpoints

- API service integration
  - Use the FastAPI service to trigger CLI runs remotely; stream logs via WebSocket
  - See: Zyra-API-Routers-and-Endpoints.md

## Media & Outreach
- Public visuals and explainer videos
  - visualize: story-friendly colormaps and annotations
  - export: Vimeo upload; share links
  - narrate (planned): generate captions/snippets from metadata

## Contribute Examples
- Add links to repos or notebooks here.
- For feature requests or missing steps, see: Roadmap-and-Tracking.md

Related
- Stage-Examples.md — concise examples per stage
- Pipeline-Patterns.md — chaining stages and pipeline configs
- Install-Extras.md — set up the right environment
