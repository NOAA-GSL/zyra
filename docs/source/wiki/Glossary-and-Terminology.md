# Glossary & Terminology

Shared terms and aliases used across Zyra.

- Stages (preferred): import → process → simulate → decide → visualize → narrate → verify → export
- Stage aliases: acquire/ingest → process/transform → visualize/render → export/disseminate (legacy: decimate)
- Connectors: source/destination integrations under `zyra.connectors` with ingest/egress and shared backends.
- Transform: lightweight helpers in `zyra.transform` (e.g., frames metadata, dataset JSON updates).
- Frames metadata: JSON summary produced from a frames directory (used for videos or galleries).
- Dataset JSON: lightweight registry or manifest of datasets/products with IDs and metadata.
- Extras: optional dependency groups (e.g., `connectors`, `processing`, `visualization`, `interactive`, focused `grib2|netcdf|geotiff`).
- Interactive: optional Folium/Plotly outputs for web-friendly visuals.
- Legacy terms: `acquisition` (use `connectors`), `decimate` (use `export`), `datatransfer` (alias of `connectors`).
- Provenance: logs/metadata capturing inputs, parameters, and outputs for reproducibility.

See also
- Workflow-Stages.md, Install-Extras.md, Stage-Examples.md
