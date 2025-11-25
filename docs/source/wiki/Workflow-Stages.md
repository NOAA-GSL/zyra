# Zyra Workflow Stages

This page outlines Zyra’s eight workflow stages with preferred names, common aliases, and how they map to the current CLI and docs. Use this as a north star when designing pipelines and documentation.

## Pipeline at a Glance

- import → process → simulate → decide → visualize → narrate → verify → export
- `zyra swarm --plan plan.yaml` runs these as cooperating agents; a starter plan lives at `samples/swarm/mock_basic.yaml`.
- Use `--log-events` to watch provenance events live and `--dump-memory path/to.db` to inspect prior runs.
- For a real FTP → pad-missing → compose-video pipeline, try `samples/swarm/drought_animation.yaml`
  (requires Pillow, write access to `data/drought/`, and the `earth_vegetation.jpg` basemap in your working directory).
- Use `zyra plan --intent "<request>"` to preview planner-generated manifests (plus heuristic augmentation suggestions) before running `zyra swarm`.

## Stages

### 1. Import (aliases: acquire, ingest)
- Purpose: Fetch bytes and lists from remote/local sources (HTTP/S, S3, FTP, Vimeo, filesystem).
- CLI today: `zyra acquire http|s3|ftp|vimeo` with list/filter options and stdin/stdout support.
- Docs: https://noaa-gsl.github.io/zyra/api/zyra.connectors.html

### 2. Process (alias: transform)
- Purpose: Decode, subset, convert scientific data (GRIB2, NetCDF, GeoTIFF) and reshape for analysis/visuals.
- CLI today: `zyra process decode-grib2 | extract-variable | convert-format`
- Related helper group: `zyra transform` (lightweight metadata utilities: frames metadata, dataset JSON updates).
- Docs: https://noaa-gsl.github.io/zyra/api/zyra.processing.html

### 3. Simulate
- Purpose: Synthesize or emulate data and scenarios (e.g., toy datasets, downsampling, mock streams) for testing and demos.
- CLI today: Not yet a dedicated group; use notebooks/scripts or processing helpers. Planned as a future CLI group.
- Related: Pipeline Patterns, CLI Expansion Plan.

### 4. Decide (alias: optimize)
- Purpose: Score, rank, and select best variants (e.g., parameter sweeps, tiling choices, colormaps) and branch pipelines accordingly.
- CLI today: Not yet a dedicated group; patterns can be expressed via configs or orchestrators (e.g., `zyra run` in the future).
- Related: Wizard Assistant plans; Pipeline Patterns.

### 5. Visualize (alias: render)
- Purpose: Produce static images, animations, and interactive HTML maps/plots.
- CLI today: `zyra visualize heatmap|contour|timeseries|vector [deprecated: wind] | animate | compose-video | interactive`
- Docs: https://noaa-gsl.github.io/zyra/api/zyra.visualization.html

### 6. Narrate
- Purpose: Generate captions, reports, or web pages that contextualize outputs (text + media + metadata).
- CLI today: Not yet a dedicated group; use templates and external tools. Planned integration alongside logging/metadata.
- Related: Wizard Interactive Assistant; Logging in Zyra.

### 7. Verify
- Purpose: Validate integrity and quality (checksums, schema validation, visual/quantitative metrics, provenance).
- CLI today: Not yet a dedicated group; hooks via processing/transform and external validators. Planned as a future CLI group.
- Related: Logging in Zyra.

### 8. Export (alias: disseminate; legacy: decimate)
- Purpose: Move results to destinations (local path, S3, FTP, HTTP POST, Vimeo) with streaming support.
- CLI today: `zyra export local|s3|ftp|post|vimeo` (stdin-friendly with `--read-stdin`).
- Docs: https://noaa-gsl.github.io/zyra/api/zyra.connectors.html

## Notes

- Aliases are supported for familiarity; prefer the primary names in docs/UI.
- Some stages (simulate, decide, narrate, verify) are conceptual today and targeted for future CLI support. See Roadmap-and-Tracking.md.
- For streaming pipelines, many subcommands accept `-` for stdin/stdout.

## Related Reading

- Pipeline Patterns: Pipeline-Patterns.md
- Logging and provenance: Logging-in-Zyra.md
- CLI routes and endpoints: Zyra-API-Routers-and-Endpoints.md
- Security quickstart: Zyra-API-Security-Quickstart.md
- Roadmap & tracking: Roadmap-and-Tracking.md

## Status & Roadmap

- Import: Implemented via `acquire` with HTTP/S, S3, FTP, Vimeo.
  - Next: Unified manifest handling and profile-based discovery.
- Process: Implemented via `process` (decode/extract/convert) and `transform` helpers.
  - Next: More subsetting ops (spatial/temporal), streaming NetCDF transforms.
- Simulate: Conceptual; use notebooks/scripts for now.
  - Next: Add `simulate` CLI group for toy datasets and mock streams.
- Decide: Conceptual; patterns via configs/overrides today.
  - Next: Add `decide`/`optimize` group for parameter sweeps and picking best artifacts.
- Visualize: Implemented (static/animated/interactive).
  - Next: Expand interactive commands; add charting parity across data types.
- Narrate: Conceptual; rely on templates and external tools today.
  - Next: Add `narrate` group for captions/reports with metadata bindings.
- Verify: Conceptual; use logging/metadata and external validators today.
  - Next: Add `verify` group for checksums, schema validation, and basic metrics.
- Export: Implemented via `export` (alias: `disseminate`, legacy: `decimate`).
  - Next: Add resumable uploads and richer auth profiles.
