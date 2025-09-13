# CLI Cheatsheet

Quick commands for common tasks. Many subcommands support `-` for stdin/stdout to enable piping.

## Import
- HTTP → file: `zyra acquire http https://example.com/data.bin -o data.bin`
- S3 list: `zyra acquire s3 --url s3://bucket/prefix/ --list --pattern "\\.grib2$"`
- FTP sync: `zyra acquire ftp ftp://host/path --sync-dir ./frames --pattern "image_(\\d{8})\\.png" --since 2024-08-01 --date-format %Y%m%d`

## Search
- SOS profile: `zyra search --query "tsunami" --profile sos`
- OGC WMS: `zyra search --query "Temperature" --ogc-wms "https://...GetCapabilities"`
- Include local + enrich: `zyra search --query "sst" --ogc-wms <url> --include-local --enrich shallow`

## Process
- GRIB2 → NetCDF: `zyra process convert-format file.grib2 netcdf --stdout > out.nc`
- Decode GRIB2 subset: `zyra process decode-grib2 s3://bucket/file.grib2 --pattern ":TMP:surface:" --raw > subset.grib2`
- Extract variable: `zyra process extract-variable demo.nc T2M --stdout | zyra process convert-format - netcdf --stdout > t2m.nc`

## Visualize
- Heatmap: `zyra visualize heatmap --input out.nc --var T2M --output heatmap.png`
- Contour: `zyra visualize contour --input out.nc --var T2M --levels 5,10,15 --filled --output contour.png`
- Animate frames: `zyra visualize animate --frames ./frames --output frames`
- Compose MP4: `zyra visualize compose-video --frames ./frames --output movie.mp4`

## Export
- Local (stdin → file): `cat out.nc | zyra export local - -o saved.nc`
- S3 (stdin → object): `cat out.nc | zyra export s3 --url s3://bucket/out.nc -i -`
- HTTP POST JSON: `echo '{\"ok\":true}' | zyra export post - https://example.com/ingest --content-type application/json`

## Piping Patterns
- List → fetch → convert → save:
  - `zyra acquire s3 --url s3://bucket/prefix/ --list ...` (pick one)
  - `zyra acquire s3 --url s3://bucket/file.grib2 -o - | zyra process convert-format - netcdf --stdout > out.nc`

## Tips
- Use `-` for stdin/stdout and `--stdout` to force stdout where supported.
- Prefer primary stage names (import/process/visualize/export); legacy `decimate` remains as alias for export.
- Install extras as needed (see Install-Extras.md).
