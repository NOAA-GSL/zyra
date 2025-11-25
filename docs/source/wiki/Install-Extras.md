# Install and Extras

A quick guide to installing Zyra with optional extras. Use these to tailor your environment to the workflow stages you need.

## Python Version
- Requires Python 3.10+

## Core Install
- Pip (core only): `pip install zyra`
- Poetry (dev): `poetry install --with dev`

## Stage-Focused Extras

- connectors (import/export backends)
  - Pip: `pip install "zyra[connectors]"`
  - Includes: `boto3`, `requests`, `PyVimeo`
  - Enables: HTTP/S, FTP, S3, Vimeo

- processing (GRIB2, NetCDF, GeoTIFF, FFmpeg helpers)
  - Pip: `pip install "zyra[processing]"`
  - Includes: `cfgrib`, `pygrib`, `netcdf4`, `xarray`, `rioxarray`, `rasterio`, `siphon`, `scipy`, `ffmpeg-python`

- visualization (static plots/maps)
  - Pip: `pip install "zyra[visualization]"`
  - Includes: `cartopy`, `matplotlib`, `xarray`, `scipy`, `pandas`, `contextily`

- interactive (optional interactive visuals)
  - Pip: `pip install "zyra[interactive]"`
  - Includes: `folium`, `plotly`

- api (FastAPI service and optional job infra)
  - Pip: `pip install "zyra[api]"`
  - Includes: `fastapi`, `uvicorn`, `python-multipart`, `redis`, `rq`

- all (everything above)
  - Pip: `pip install "zyra[all]"`

Poetry equivalents (dev env)
- connectors: `poetry install --with dev -E connectors`
- processing: `poetry install --with dev -E processing`
- visualization: `poetry install --with dev -E visualization`
- interactive: `poetry install --with dev -E interactive`
- api: `poetry install --with dev -E api`
- all: `poetry install --with dev --all-extras`

## Focused Extras
- grib2 only: `pip install "zyra[grib2]"`
- netcdf only: `pip install "zyra[netcdf]"`
- geotiff export: `pip install "zyra[geotiff]"`

## Examples
- Minimal heatmap (NetCDF input):
  - `pip install "zyra[visualization]"`
  - `zyra visualize heatmap --input demo.nc --var T2M --output out.png`
- GRIB2 → NetCDF conversion:
  - `pip install "zyra[processing]"`
  - `zyra process convert-format file.grib2 netcdf --stdout > out.nc`
- S3 copy (stdin/stdout friendly):
  - `pip install "zyra[connectors]"`
  - `zyra acquire s3 --url s3://bucket/key -o - | zyra export s3 --url s3://other/key -i -`

## Notes
- Optional deps are large; install only what you need.
- Many commands support `-` for stdin/stdout to enable streaming pipelines.
- Legacy terms: `datatransfer` (alias of `connectors`), `decimate` (alias of `export`). Prefer the primary names in new docs.
