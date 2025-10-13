# Transform

Commands
- `metadata` — Compute frames metadata JSON from a directory of images (alias: `scan-frames`).
- `enrich-metadata` — Enrich frames metadata JSON with dataset id, Vimeo URI, and timestamp.
- `update-dataset-json` — Update dataset JSON fields from CLI args or another file.
- `shapefile-to-geojson` — Convert shapefiles to GeoJSON with optional time normalization.
- `csv-to-geojson` — Convert CSV point tables to GeoJSON with optional time normalization.

metadata
- `--frames-dir DIR` — directory containing images
- `--pattern REGEX` — filter filenames
- `--datetime-format` — parse timestamps from filenames
- `--period-seconds N` — expected cadence to compute missing frames
- Output: `-o out.json` or `-` for stdout

Examples
- `zyra transform scan-frames --frames-dir ./frames --pattern '\\.(png|jpg)$' --period-seconds 300 -o frames.json`
- `zyra transform shapefile-to-geojson --input data/250314_FRW.shp --timezone America/Chicago --default-year 2025 -o warnings.geojson`
- `zyra transform csv-to-geojson --input data/250314_regional_hotspots.csv --timezone America/Chicago --event-date 2025-03-14 -o hotspots.geojson`
