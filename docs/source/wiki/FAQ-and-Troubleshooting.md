# FAQ & Troubleshooting

Common setup and runtime issues, with quick fixes and pointers.

## Installation
- Missing FFmpeg/ffprobe
  - Symptom: compose-video fails; video commands error.
  - Fix: install system packages and ensure they’re on PATH (e.g., `sudo apt-get install ffmpeg`).

- Cartopy/Natural Earth data cache
  - Symptom: visualization fails fetching basemap or coastlines.
  - Fix: pre-populate cache or set `CARTOPY_DATA_DIR` to a writable path.

- GDAL/rasterio build errors
  - Symptom: `pip install rasterio` fails to build.
  - Fix: prefer prebuilt wheels or use conda for heavy geo deps; or skip `geotiff` extra if not needed.

- GRIB support (cfgrib/pygrib)
  - Symptom: cannot decode GRIB2; engine errors or missing system libs.
  - Fix: install `zyra[grib2]`; on some OS, ecCodes system libs may be required. Alternative: use `pygrib` backend or pre-convert to NetCDF.

## CLI usage
- Stdin/stdout
  - Use `-` as input/output where supported and `--stdout` to force stdout.
  - Example: `cat subset.grib2 | zyra process convert-format - netcdf --stdout > out.nc`

- S3 unsigned access
  - Symptom: auth errors for public buckets.
  - Fix: add `--unsigned` to S3 acquire/export when appropriate.

- HTTP behind proxy
  - Symptom: timeouts or SSL errors.
  - Fix: set `HTTP_PROXY`/`HTTPS_PROXY` env vars; verify with `curl`.

## Visualization
- Large memory usage
  - Symptom: OOM during plot/animation.
  - Fix: reduce resolution/subset, chunk data with xarray, or generate frames and compose separately.

## Environments
- Windows quirks
  - Consider WSL2 for better compatibility with geospatial stacks.

- Apple Silicon
  - Prefer prebuilt wheels; some heavy deps may still be x86-only.

## Where to get help
- Stage-Examples.md for working commands
- Install-Extras.md for extras and env setup
- Issues: https://github.com/NOAA-GSL/zyra/issues
