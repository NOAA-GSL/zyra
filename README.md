# Zyra (formerly DataVizHub)

## Overview
Zyra is a utility library for building data-driven visual products. It provides composable helpers for data transfer (FTP/HTTP/S3/Vimeo), data processing (GRIB/imagery/video), and visualization (matplotlib + basemap overlays). Use these pieces to script your own pipelines; this repo focuses on the reusable building blocks rather than end-user scripts.

 This README documents the library itself and shows how to compose the components. For complete runnable examples, see the examples repos when available, or adapt the snippets below.

[![PyPI version](https://img.shields.io/pypi/v/zyra.svg)](https://pypi.org/project/zyra/) [![Docs](https://img.shields.io/badge/docs-GitHub_Pages-0A7BBB)](https://noaa-gsl.github.io/zyra/) [![Chat with Zyra Helper Bot](https://img.shields.io/badge/ChatGPT-Zyra_Helper_Bot-00A67E?logo=openai&logoColor=white)](https://chatgpt.com/g/g-6897a3dd5a7481918a55ebe3795f7a26-zyra-helper-bot) [![DOI](https://zenodo.org/badge/854215643.svg)](https://doi.org/10.5281/zenodo.16923322)

> Migration notice: the project has been renamed from DataVizHub to Zyra. The new import namespace is `zyra` and new console scripts are `zyra` and `zyra-cli`. For a transition period, the legacy `datavizhub` namespace and CLI remain available and redirect to Zyra under the hood. Please begin migrating your imports and usage examples to `zyra`.

## Table of Contents
- [Overview](#overview)
- [Features](#features)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Install (Poetry)](#install-poetry)
- [Install (pip extras)](#install-pip-extras)
 - [Stage-Specific Installs](#stage-specific-installs)
- [CLI Overview](#cli-overview)
- [API Service](#api-service)
- [Quick Composition Examples](#quick-composition-examples)
- [Interactive Visualization](#interactive-visualization)
- [Real-World Implementations](#real-world-implementations)
- [Development, Test, Lint](#development-test-lint)
- [Repository Guidelines](#repository-guidelines)
- [Documentation](#documentation)
- [Notes](#notes)
- [License](#license)
- [Links](#links)

## Features
- [Connectors](#connectors-layer): HTTP/FTP/S3/Vimeo backends (functional API) in `zyra.connectors.backends` (legacy `datavizhub.acquisition` still present with deprecations).
- [Processing](#processing-layer): `DataProcessor`, `VideoProcessor`, `GRIBDataProcessor` (in `zyra.processing`).
- [Visualization](#visualization-layer): `PlotManager`, `ColormapManager` (with included basemap/overlay assets in `zyra.assets`).
- [Utilities](#utilities): `CredentialManager`, `DateManager`, `FileUtils`, `ImageManager`, `JSONFileManager` (in `zyra.utils`).


## Project Structure
- `connectors/`: transfer helpers
  - `ingest/` and `egress/` CLI groups, and functional backends under `backends/` (HTTP/S3/FTP/Vimeo).
- `processing/`: data/video processing (GRIB/NetCDF, FFmpeg-based video).
- `visualization/`: plotting utilities and colormaps.
- `transform/`: lightweight helpers (e.g., frames metadata, dataset JSON updates).
- `api/`: FastAPI service exposing CLI stages over HTTP/WebSocket.
- `utils/`: shared helpers (dates, files, images, credentials, I/O).
- `assets/images/`: packaged basemaps and overlays used by plots.

Notes
- Legacy `acquisition/` modules remain for back-compat but are deprecated. Prefer `zyra.connectors.backends.*` and the CLI groups `acquire`/`decimate`.

## Prerequisites
- Python 3.10+
- FFmpeg and ffprobe on PATH for video-related flows.
- Optional: AWS credentials for S3; Vimeo API credentials for upload flows.

## Install (Poetry)
- Core dev env: `poetry install --with dev`
- With optional extras: `poetry install --with dev -E connectors -E processing -E visualization` (or `--all-extras`)
- Spawn a shell: `poetry shell`
- One-off run: `poetry run python -c "print('ok')"`

Notes for development:
- Optional integrations (S3 via boto3, Vimeo via PyVimeo, HTTP via requests) are provided as extras, not dev deps.
- Opt into only what you need using `-E <extra>` flags, or use `--all-extras` for a full-featured env.

## Install (pip extras)
- Core only: `pip install zyra`
- Connectors deps: `pip install "zyra[connectors]"`
- Processing deps: `pip install "zyra[processing]"`
- Visualization deps: `pip install "zyra[visualization]"`
- Interactive deps: `pip install "zyra[interactive]"`
- API service deps: `pip install "zyra[api]"`
- Everything: `pip install "zyra[all]"`

Deprecation note:
- `datatransfer` remains available as an alias of `connectors` for backward compatibility and may be removed in a future release.

Focused installs for GRIB2/NetCDF/GeoTIFF:

```
pip install "zyra[grib2,netcdf,geotiff]"
```

Extras overview:

| Extra     | Packages                    | Enables                                   |
|-----------|-----------------------------|-------------------------------------------|
| `grib2`   | `cfgrib`, `pygrib`          | GRIB2 decoding via xarray/pygrib          |
| `netcdf`  | `netcdf4`, `xarray`         | NetCDF I/O and subsetting                 |
| `geotiff` | `rioxarray`, `rasterio`     | GeoTIFF export from xarray                |
| `interactive` | `folium`, `plotly`      | Interactive maps (Folium) and plots (Plotly) |

Notes:
- Core install keeps footprint small; optional features pull in heavier deps (e.g., Cartopy, SciPy, ffmpeg-python).
- Some example scripts may import plotting libs; install `[visualization]` if you use those flows.

## Stage-Specific Installs
Install only what you need for a given stage. Each stage can run independently with its own optional extras.

- Connectors (transfer) stage:
  - Pip: `pip install -e .[connectors]`
  - Poetry: `poetry install --with dev -E connectors`
  - Alias (deprecated): `datatransfer`
- Processing stage:
  - Pip: `pip install -e .[processing]`
  - Poetry: `poetry install --with dev -E processing`
- Visualization stage (includes Matplotlib, Cartopy, Xarray, SciPy, Contextily):
  - Pip: `pip install -e .[visualization]`
  - Poetry: `poetry install --with dev -E visualization`
- Interactive stage (optional Folium/Plotly):
  - Pip: `pip install -e .[interactive]`
  - Poetry: `poetry install --with dev -E interactive`

Examples:
- Run the visualization CLI with only the visualization extra installed:
  - Heatmap: `python -m zyra.cli heatmap --input samples/demo.npy --output heatmap.png`
  - Contour: `python -m zyra.cli contour --input samples/demo.nc --var T2M --output contour.png --levels 5,10,15 --filled`

Focused extras remain available for targeted installs:
- GRIB2 only: `pip install -e .[grib2]`
- NetCDF only: `pip install -e .[netcdf]`
- GeoTIFF export: `pip install -e .[geotiff]`

Note on interactive installs:
- The `interactive` extra pulls in Folium and/or Plotly, which increase dependency size and runtime memory. If you only need static images and animations, you can skip `interactive` and install just `visualization`.

## CLI Overview

DataVizHub ships a single `zyra` CLI organized into groups that mirror pipeline stages (plus a `transform` helper) and a `run` helper for config-driven pipelines.

### CLI Tree

```
zyra
├─ acquire            # Ingest/fetch bytes from sources
│  ├─ http            # acquire http <url> [--list --pattern REGEX --since ISO --until ISO --date-format FMT] [-o out|-]
│  ├─ s3              # acquire s3 --url s3://bucket/key [--unsigned] [--list --pattern REGEX --since ISO --until ISO --date-format FMT] [-o out|-]
│  ├─ ftp             # acquire ftp <ftp://host/path or host/path> [--list|--sync-dir DIR] [--pattern REGEX --since ISO --until ISO --date-format FMT] [-o out|-]
│  └─ vimeo           # (placeholder)
├─ process            # Decode, extract, convert (supports stdin/stdout)
│  ├─ decode-grib2
│  ├─ extract-variable
│  └─ convert-format
├─ visualize          # Static images, animations, interactive HTML
│  ├─ heatmap | contour | timeseries | vector | wind [deprecated]
│  ├─ animate         # write frames; optional MP4 composition
│  ├─ compose-video   # frames → MP4 (ffmpeg)
│  └─ interactive     # folium/plotly HTML
├─ decimate           # Write/egress bytes to destinations
│  ├─ local           # file path
│  ├─ s3              # s3://bucket/key
│  ├─ ftp             # ftp://host/path or host/path
│  ├─ post            # HTTP POST
│  └─ vimeo           # upload/replace video on Vimeo
├─ transform          # Lightweight transforms/metadata
│  ├─ metadata            # Compute frames metadata JSON (dir scan)
│  ├─ enrich-metadata    # Merge dataset id/Vimeo URI, stamp updated_at
│  └─ update-dataset-json# Update dataset.json entry by id
└─ run                # Run a pipeline from YAML/JSON config
```

Notes
- All subcommands accept `-` for stdin/stdout where applicable to support piping.

### Quick Usage by Group

- Acquire
  - HTTP to file: `zyra acquire http https://example.com/data.bin -o data.bin`
  - HTTP list+filter: `zyra acquire http https://example.com/dir/ --list --pattern '\\.png$' --since 2024-01-01 --date-format %Y%m%d`
  - S3 to stdout: `zyra acquire s3 --url s3://bucket/key -o -`
  - S3 list+filter: `zyra acquire s3 --url s3://bucket/prefix/ --list --pattern '\\.grib2$' --since 2024-08-01 --date-format %Y%m%d`
  - FTP sync directory: `zyra acquire ftp ftp://host/path --sync-dir /data/frames --pattern 'image_(\\d{8})\\.png' --since 2024-08-01 --date-format %Y%m%d`

- Process (streaming-friendly)
  - Decode GRIB2 to raw bytes via `.idx` subset: `zyra process decode-grib2 s3://bucket/file.grib2 --pattern ":TMP:surface:" --raw > subset.grib2`
  - Convert stdin to NetCDF: `cat subset.grib2 | zyra process convert-format - netcdf --stdout > out.nc`

- Visualize
  - Contour PNG from NetCDF: `zyra visualize contour --input out.nc --var TMP --output contour.png --levels 10 --filled`
  - Animate frames and compose to MP4: `zyra visualize animate --mode heatmap --input cube.npy --output-dir frames && zyra visualize compose-video --frames frames -o out.mp4`

- Decimate
  - Upload to S3 from stdin: `cat out.png | zyra decimate s3 -i - --url s3://bucket/products/out.png`
- HTTP POST JSON: `echo '{"ok":true}' | zyra decimate post -i - https://example.com/ingest --content-type application/json`

## Batch Mode

Batch-friendly commands let you process multiple inputs in one invocation. These are ideal for quick ad‑hoc jobs or for building light pipelines without YAML.

| Command | Flags | Behavior |
|--------|-------|----------|
| `acquire http` | `--inputs <url...>`, `--manifest file.txt`, `--output-dir OUT` | Fetch multiple HTTP/HTTPS URLs to OUT (basenames preserved). |
| `acquire s3` | `--inputs <s3://...>`, `--manifest file.txt`, `--output-dir OUT`, `--unsigned` | Fetch multiple S3 objects (s3://bucket/key) to OUT. |
| `acquire ftp` | `--inputs <ftp://...>`, `--manifest file.txt`, `--output-dir OUT` | Fetch multiple FTP paths to OUT. |
| `process convert-format` | `--inputs <in...>`, `--output-dir OUT`, `--format {netcdf,geotiff}` | Convert many inputs to OUT; prints `{"outputs": [...]}`. API: pass `args.files: [..]`. |
| `visualize heatmap` | `--inputs <in...>`, `--output-dir OUT` | Render one PNG per input in OUT. |
| `visualize contour` | `--inputs <in...>`, `--output-dir OUT`, `--levels`, `--filled` | Render one PNG per input in OUT. |
| `visualize vector` | `--inputs <in...>`, `--output-dir OUT` | Render one PNG per input in OUT. |
| `visualize animate` | `--inputs <in...>`, `--output-dir OUT`, `--to-video`, `--combine-to GRID.mp4`, `--grid-cols N` | For each input, writes frames under `OUT/<base>/` and optional per‑input MP4s. Optionally composes a grid MP4 from those videos. |

Notes
- Manifests: acquisition commands accept `--manifest` with one URL/path per line (blank lines and `#` comments ignored).
- API mapping: `process convert-format` maps `args.files` to `--inputs`; other batch commands are CLI-first.
- Output structure: batch commands write to `--output-dir` (and may also print a JSON `outputs` list for quick scripting).

## Quick Composition Examples

## Connectors Layer

The `zyra.connectors.backends` package provides functional helpers for ingress/egress:

- HTTP: `fetch_bytes`, `fetch_text`, `fetch_json`, `post_data`, `list_files`, `get_idx_lines`, `download_byteranges`.
- S3: `fetch_bytes`, `upload_bytes`, `list_files`, `exists`, `delete`, `stat`, `get_idx_lines`, `download_byteranges`.
- FTP: `fetch_bytes`, `upload_bytes`, `list_files`, `exists`, `delete`, `stat`, `sync_directory`.
- Vimeo: `upload_path`, `update_video`, `update_description`.

Examples:

```
from zyra.connectors.backends import ftp as ftp_backend, s3 as s3_backend

# FTP: read a remote file to bytes and write locally
data = ftp_backend.fetch_bytes("ftp://ftp.example.com/pub/file.txt")
with open("file.txt", "wb") as f:
    f.write(data)

# S3: upload local file bytes
with open("local.nc", "rb") as f:
    s3_backend.upload_bytes(f.read(), "s3://my-bucket/path/object.nc")
```

### Advanced Connectors: GRIB subsetting, byte ranges, and listing

Optional helpers speed up GRIB workflows and large file transfers.

- .idx subsetting (S3 public bucket, unsigned):
  ```python
  from zyra.connectors.backends import s3 as s3_backend
  from zyra.utils.grib import idx_to_byteranges

  url = "s3://noaa-hrrr-bdp-pds/hrrr.20230801/conus/hrrr.t00z.wrfsfcf00.grib2"
  lines = s3_backend.get_idx_lines(url, unsigned=True)
  ranges = idx_to_byteranges(lines, r"(:TMP:surface|:PRATE:surface)")
  data = s3_backend.download_byteranges(url, None, ranges.keys(), unsigned=True)
  ```

- Pattern-based listing (regex)
  - S3 prefix listing with regex filter:
    ```python
    from zyra.connectors.backends import s3 as s3_backend
    keys = s3_backend.list_files("s3://bucket/hrrr.20230801/conus/", pattern=r"wrfsfcf\d+\.grib2$")
    ```
  - HTTP directory-style index scraping with regex filter:
    ```python
    from zyra.connectors.backends import http as http_backend
    urls = http_backend.list_files(
        "https://nomads.ncep.noaa.gov/pub/data/nccf/com/hrrr/prod/",
        pattern=r"\.grib2$",
    )
    ```

- Parallel HTTP range downloads via `.idx`:
  ```python
  from zyra.connectors.backends import http as http_backend
  from zyra.utils.grib import idx_to_byteranges

  lines = http_backend.get_idx_lines("https://example.com/path/file.grib2")
  ranges = idx_to_byteranges(lines, r"GUST")
  blob = http_backend.download_byteranges("https://example.com/path/file.grib2", ranges.keys())
  ```

Notes
- Migration: `datavizhub.acquisition.*` is deprecated. Prefer `zyra.connectors.backends.*` and `zyra.utils.grib`.
- Pattern filters use Python regular expressions (`re.search`) applied to full keys/paths/URLs.
- `.idx` resolution appends `.idx` to the GRIB path unless a fully qualified `.idx` path is given.
- For unsigned public S3 buckets, pass `unsigned=True` as shown above.

Credentials
- FTP: supply credentials inline in the URL `ftp://user:pass@host/path` (for quick runs) or use the OO wrapper `FTPConnector(host, username=..., password=...)` in code. Avoid committing secrets; prefer env injection in CI or use `.env` with `CredentialManager` when scripting.
- S3: prefer IAM roles or environment variables; the S3 backend/manager follows standard AWS resolution when not using unsigned mode.
- Vimeo: use API token/keys via environment variables per `CredentialManager` guidance, or pass explicitly when constructing a client in code.

YAML templating with environment variables
- Template credentials in YAML configs and enable strict checking:
  ```yaml
  # Example: inject FTP creds from environment
  - stage: acquire
    command: ftp
    args:
      path: ftp://${FTP_USER}:${FTP_PASS}@ftp.example.com/pub/frames/
      sync_dir: ./frames
      pattern: "image_(\\d{8})\\.png"
      since_period: "P1Y"
      date_format: "%Y%m%d"
  ```
  - Run with strict env: `zyra run pipeline.yaml --strict-env`
  - Provide env: `export FTP_USER=anonymous; export FTP_PASS='test@example.com'` (when embedding directly, URL-encode `@` as `%40`).

Transform: Frames Metadata
- Compute metadata for a frames directory between acquire and visualize:
  - CLI: `zyra transform metadata --frames-dir ./frames --datetime-format %Y%m%d --period-seconds 3600 -o frames_meta.json`

## Processing Layer

The `zyra.processing` package standardizes processors under a common `DataProcessor` interface.

- DataProcessor: abstract base with `load(input_source)`, `process(**kwargs)`, `save(output_path=None)`, and optional `validate()`.
- Processors: `VideoProcessor` (image sequences → video via FFmpeg), `GRIBDataProcessor` (GRIB files → NumPy arrays + utilities).
- Notes: `VideoProcessor` requires system `ffmpeg` and `ffprobe` on PATH; GRIB utilities rely on `pygrib`, `siphon`, and `scipy` where used.

Examples:

```
# Video: compile image frames into a video
from zyra.processing.video_processor import VideoProcessor

vp = VideoProcessor(input_directory="./frames", output_file="./out/movie.mp4")
vp.load("./frames")
if vp.validate():
    vp.process()
    vp.save("./out/movie.mp4")
```

```
# GRIB: read a GRIB file to arrays and dates
from zyra.processing.grib_data_processor import GRIBDataProcessor

gp = GRIBDataProcessor()
data_list, dates = gp.process(grib_file_path="/path/to/file.grib2", shift_180=True)
```

### Processing GRIB2 and NetCDF (bytes-first)

Decode a GRIB2 subset returned as bytes, extract a variable, and write NetCDF:

```
from zyra.processing import grib_decode, extract_variable, convert_to_format

dec = grib_decode(data_bytes, backend="cfgrib")  # default backend
da = extract_variable(dec, r"^TMP$")  # exact/regex match
nc_bytes = convert_to_format(dec, "netcdf", var="TMP")
```

Work with NetCDF directly and subset spatially/temporally:

```
from zyra.processing import load_netcdf, subset_netcdf

ds = load_netcdf(nc_bytes)
sub = subset_netcdf(ds, variables=["TMP"], bbox=(-130,20,-60,55), time_range=("2024-01-01","2024-01-02"))
```

Notes and fallbacks:
- Default backend is `cfgrib` (xarray + eccodes). If unavailable or failing, `pygrib` is attempted when requested; `wgrib2 -json` can be used as a metadata fallback.
- GeoTIFF conversion requires `rioxarray`/`rasterio` and supports a single variable; specify `var` when multiple variables exist.
- GRIB2→NetCDF uses `xarray.to_netcdf()` when possible with a `wgrib2 -netcdf` fallback if present.
- Generic NetCDF→GRIB2 is not supported by `wgrib2`. If `cdo` is installed, `convert_to_grib2()` uses `cdo -f grb2 copy` automatically; otherwise a clear exception is raised.

CLI helpers (grouped commands):
- `zyra process decode-grib2 <file_or_url> [--backend cfgrib|pygrib|wgrib2]`
- `zyra process extract-variable <file_or_url> <pattern> [--backend ...]`
- `zyra process convert-format <file_or_url> <netcdf|geotiff> -o out.ext [--var NAME] [--backend ...]`

## Development, Test, Lint

- Run all tests:
  - Poetry: `poetry run pytest -q`
  - Pip/venv: `pytest -q`

- Run CLI-only tests (marker `cli`):
  - `pytest -m cli`

- Run tile-based visualization tests (require `contextily` and explicit opt-in):
  - `DATAVIZHUB_RUN_TILE_TESTS=1 pytest -m cli`
  - Without this variable set, tile tests are skipped to keep CI stable in minimal runners.

- Run pipeline integration tests (marker `pipeline`):
  - `pytest -m pipeline`
  - Combine with other opts as needed, e.g., `-q` or coverage flags.

## Pipeline Patterns

Sample pipeline configs live under `samples/pipelines/`:

- `nc_passthrough.yaml`: read NetCDF bytes from stdin and emit NetCDF to stdout.
  - Usage: `cat tests/testdata/demo.nc | zyra run samples/pipelines/nc_passthrough.yaml > out.nc`
- `nc_to_file.yaml`: read NetCDF from stdin, then write to `out.nc` via `decimate local`.
  - Usage: `cat tests/testdata/demo.nc | zyra run samples/pipelines/nc_to_file.yaml`
- `ftp_to_s3.yaml`: template for FTP → video composition → S3 upload (placeholders, not CI-safe).
  - Dry-run mapping: `zyra run samples/pipelines/ftp_to_s3.yaml --dry-run`
  - Notes: Requires network access and credentials when running without `--dry-run`.
- `ftp_to_local.yaml`: FTP → transform → video → local file copy (no S3/Vimeo).
  - Dry-run mapping: `zyra run samples/pipelines/ftp_to_local.yaml --dry-run`
  - Live run: writes `/tmp/frames_meta.json` and `/tmp/video.mp4` locally. Requires FTP network access only.
- `extract_variable_to_file.yaml`: extract TMP from stdin, convert to NetCDF, and write to file.
  - Usage: `cat tests/testdata/demo.nc | zyra run samples/pipelines/extract_variable_to_file.yaml`
- `compose_video_to_local.yaml`: compose frames in a directory to MP4 and copy locally.

Overrides
- Global override (applied where key exists): `--set var=TMP`
- Per-stage override using 1-based index (1-based): `--set 2.var=TMP` (sets key `var` on stage 2 only)
- Stage-name override (uses aliases acquisition/ingest→acquire, processing→process, visualization→visualize, decimation/egress→decimate):
  - `--set processing.var=TMP`
  - `--set decimation.backend=local`

Dry run and argv output
- Validate and print the expanded stage argv without executing:
  - Text: `zyra run pipeline.yaml --dry-run`
  - JSON: `zyra run pipeline.yaml --dry-run --print-argv-format=json`
    - Structure:
      ```json
      [
        {"stage": 1, "name": "acquire", "argv": ["zyra", "acquire", "http", "https://..."]},
        {"stage": 2, "name": "process", "argv": ["zyra", "process", "convert-format", "-", "netcdf"]}
      ]
      ```

Error handling
- Stop on first error (default) or continue executing remaining stages:
  - `zyra run pipeline.yaml --continue-on-error`

- Lint/format (if enabled in your env):
  - `poetry run black . && poetry run isort . && poetry run flake8`

## Chaining Commands with --raw and --stdout

The CLI supports streaming binary data through stdout/stdin so you can compose offline pipelines without touching disk.

- `.idx` → extract → convert (one-liner):
  ```bash
  zyra process decode-grib2 file.grib2 --pattern "TMP" --raw | \
  zyra process extract-variable - "TMP" --stdout --format grib2 | \
  zyra process convert-format - geotiff --stdout > tmp.tif
  ```

- Notes on tools and fallbacks:
  - `wgrib2`: When available, `extract-variable --stdout` uses `wgrib2 -match` to subset and emits either GRIB2 (`-grib`) or NetCDF (`-netcdf`).
  - `CDO`: If converting NetCDF→GRIB2 is needed without `wgrib2` support, `convert_to_grib2()` uses `cdo -f grb2 copy` when `cdo` is installed.
  - Python-only fallback: If `wgrib2` is not present, NetCDF streaming still works via xarray (`to_netcdf()`), while GRIB2 streaming may not be available depending on your environment.

- Auto-detection in `convert-format`:
  - `process convert-format` can read from stdin (`-`) and auto-detects GRIB2 vs NetCDF by magic bytes. NetCDF is opened with xarray; GRIB2 uses the configured backend to decode.

Bytes-first demos:
- Use `.idx`-aware subsetting directly with URLs: `zyra process decode-grib2 https://.../file.grib2 --pattern ":(UGRD|VGRD):10 m above ground:"`
- Pipe small outputs without temp files: `zyra process convert-format local.grib2 netcdf --stdout | hexdump -C | head`

Offline demo assets:
- Tiny NetCDF file: `tests/testdata/demo.nc`
- Tiny GRIB2 file: please place a small sample as `tests/testdata/demo.grib2` (we can add one if provided).


## Visualization Layer

Plot a data array with a basemap

```
import numpy as np
from importlib.resources import files, as_file
from zyra.visualization import PlotManager, ColormapManager

# Example data
data = np.random.rand(180, 360)

# Locate packaged basemap asset
resource = files("zyra.assets").joinpath("images/earth_vegetation.jpg")
with as_file(resource) as p:
    basemap_path = str(p)

    # Prepare colormap (continuous)
    cm = ColormapManager()
    cmap = cm.render("YlOrBr")

    # Render and save
    plotter = PlotManager(basemap=basemap_path, image_extent=[-180, 180, -90, 90])
    plotter.render(data, custom_cmap=cmap)
plotter.save("/tmp/heatmap.png")
```

Tile basemaps (static images)

- Requirements: install the visualization extra (includes `contextily`). Tiles are fetched best-effort; offline or missing deps gracefully no-op.
- Heatmap over tiles:

```
poetry install --with dev -E visualization
poetry run python -m zyra.cli heatmap \
  --input samples/demo.npy \
  --output out.png \
  --map-type tile \
  --tile-zoom 3
```

- Contour over a named tile source:

```
poetry run python -m zyra.cli contour \
  --input samples/demo.npy --output contour.png \
  --levels 10 --filled \
  --map-type tile --tile-source Stamen.TerrainBackground
```

- Vector quiver over tiles:

```
poetry run python -m zyra.cli vector \
  --u /path/U.npy --v /path/V.npy \
  --output vec.png \
  --map-type tile --tile-zoom 2
```

Attribution and provider terms
- Respect the terms of the tile provider you use (OpenStreetMap is the default in many cases). Some providers require explicit attribution in the figure or documentation; include an appropriate credit when publishing.
- Interactive Folium maps support attribution and multiple base layers via CLI flags (`--tiles`, `--attribution`, `--wms-*`). For static images, add credits in captions or overlays as needed.

Classified colormap example (optional):

```
colormap_data = [
    {"Color": [255, 255, 229, 0], "Upper Bound": 5e-07},
    {"Color": [255, 250, 205, 51], "Upper Bound": 1e-06},
]
cmap, norm = ColormapManager().render(colormap_data)
plotter.render(data, custom_cmap=cmap, norm=norm)
plotter.save("/tmp/heatmap_classified.png")
```

## Interactive Visualization

Render interactive HTML (Folium or Plotly) via the CLI. Install extras as needed:

- Poetry: `poetry install --with dev -E interactive` (or `-E visualization -E interactive`)
- Pip: `pip install "zyra[interactive]"`

Examples
- Folium heatmap from a NumPy array:

```
python -m zyra.cli interactive \
  --input samples/demo.npy \
  --output out.html \
  --engine folium \
  --mode heatmap
```

- Plotly heatmap (standalone HTML):

```
python -m zyra.cli interactive \
  --input samples/demo.npy \
  --output out_plotly.html \
  --engine plotly \
  --mode heatmap \
  --width 600 --height 300
```

- Folium points from CSV:

```
python -m zyra.cli interactive \
  --input samples/points.csv \
  --output points.html \
  --engine folium \
  --mode points
```

- Folium points with a time column (TimeDimension):

```
python -m zyra.cli interactive \
  --input samples/points_time.csv \
  --output points_time.html \
  --engine folium \
  --mode points \
  --time-column time \
  --period P6H \
  --transition-ms 300
```

- Folium vector quiver from U/V arrays:

```
python -m zyra.cli interactive \
  --mode vector \
  --u /path/U.npy \
  --v /path/V.npy \
  --output vec.html \
  --engine folium \
  --density 0.3 --scale 1.0
```

Base layers and WMS
- Use `--tiles` to set a tile layer (name or URL), e.g., `--tiles OpenStreetMap` or `--tiles "https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png"` with `--attribution`.
- Add WMS overlays with `--wms-url`, `--wms-layers`, and optionally `--wms-format`/`--wms-transparent`. Add a layer control with `--layer-control`.

CRS notes
- The display CRS is PlateCarree (EPSG:4326). Tools will warn if the input CRS differs. Use `--crs` to override, or `--reproject` (limited; requires optional GIS deps) to opt into reprojection.

Compose FTP fetch + video + Vimeo upload

```python
from zyra.connectors.backends import ftp as ftp_backend, vimeo as vimeo_backend
from zyra.processing import VideoProcessor

# Download a frame from FTP and write it to disk (repeat for remaining frames)
frame_bytes = ftp_backend.fetch_bytes("ftp://ftp.example.com/pub/images/img_0001.png")
import os; os.makedirs("/tmp/frames", exist_ok=True)
open("/tmp/frames/img_0001.png", "wb").write(frame_bytes)

VideoProcessor("/tmp/frames", "/tmp/out.mp4").process_videos(fps=30)

vimeo_backend.upload_path("/tmp/out.mp4", name="Latest Render")
```

## Utilities

The `zyra.utils` package provides shared helpers for credentials, dates, files, images, and small JSON configs.

- CredentialManager: read/manage dotenv-style secrets without exporting globally.
- DateManager: parse timestamps in filenames, compute date ranges, and reason about frame cadences.
- FileUtils: simple file/directory helpers like `remove_all_files_in_directory`.
- ImageManager: basic image inspection and change detection.
- JSONFileManager: read/update/write simple JSON files.

Examples:

```
# Credentials
from zyra.utils import CredentialManager

with CredentialManager(".env", namespace="MYAPP_") as cm:
    cm.read_credentials(expected_keys=["API_KEY"])  # expects MYAPP_API_KEY
    token = cm.get_credential("API_KEY")
```

```
# Dates
from zyra.utils import DateManager

dm = DateManager(["%Y%m%d"])
start, end = dm.get_date_range("7D")
print(dm.is_date_in_range("frame_20240102.png", start, end))
```

Batch fetching (functional connectors):

```
from zyra.connectors.backends import http as http_backend

urls = [
  "https://example.com/a.bin",
  "https://example.com/b.bin",
]
import os; os.makedirs("downloads", exist_ok=True)
for u in urls:
    data = http_backend.fetch_bytes(u)
    open(os.path.join("downloads", u.rsplit("/", 1)[-1]), "wb").write(data)
```


Minimal pipeline: build video from images and upload to S3

```python
from zyra.processing import VideoProcessor
from zyra.connectors.backends import s3 as s3_backend

vp = VideoProcessor(input_directory="/data/images", output_file="/data/out/movie.mp4")
vp.load("/data/images")
if vp.validate():
    vp.process()
    vp.save("/data/out/movie.mp4")

with open("/data/out/movie.mp4", "rb") as f:
    s3_backend.upload_bytes(f.read(), "s3://my-bucket/videos/movie.mp4")
```

## Real-World Implementations
- `rtvideo` real-time video pipeline: https://gitlab.sos.noaa.gov/science-on-a-sphere/datasets/real-time-video

## Development, Test, Lint
- Tests: `poetry run pytest -q`
- Formatting: `poetry run black . && poetry run isort .`
- Lint: `poetry run flake8`

## Repository Guidelines
- Project structure, dev workflow, testing, and contribution tips: see [AGENTS.md](AGENTS.md).

## Documentation
- Primary: Project wiki at https://github.com/NOAA-GSL/zyra/wiki
  - API Routers and Endpoints: https://github.com/NOAA-GSL/zyra/wiki/DataVizHub-API-Routers-and-Endpoints
  - Security Quickstart: https://github.com/NOAA-GSL/zyra/wiki/DataVizHub-API-Security-Quickstart
- API docs (GitHub Pages): https://noaa-gsl.github.io/zyra/
- CI-synced wiki: A GitHub Action mirrors the wiki into `docs/source/wiki/` so Sphinx can build it with the docs. Sync commits occur only on `main`; PRs/branches use the synced copy for builds without committing changes.
 - Wizard REPL (experimental): see docs/wizard-cli.md for autocomplete and edit-before-run usage.

## Notes
- Paths: examples use absolute paths (e.g., `/data/...`) for clarity, but the library does not assume a specific root; configure paths via your own settings or env vars if preferred.
- Credentials: do not commit secrets; AWS and Vimeo creds should come from env or secure stores used by `CredentialManager`.
- Dependencies: video flows require system `ffmpeg`/`ffprobe`.
 - Optional extras: see "Install (pip extras)" for targeted installs.

CAPABILITIES vs. FEATURES:
- Acquisition managers expose `capabilities` (remote I/O actions), e.g. `{'fetch','upload','list'}` for S3/FTP; `{'fetch'}` for HTTP; `{'upload'}` for Vimeo.
- Processors expose `features` (lifecycle hooks), e.g. `{'load','process','save','validate'}` for `VideoProcessor` and `GRIBDataProcessor`.

Examples:
```
from zyra.processing.video_processor import VideoProcessor

vp = VideoProcessor("./frames", "./out.mp4")
print(vp.features)      # {'load','process','save','validate'}
```

## License
Distributed under the MIT License. See [LICENSE](LICENSE).

## Links
- Source: https://github.com/NOAA-GSL/zyra
- PyPI: https://pypi.org/project/zyra/
## API Service
Expose the 4-stage CLI over HTTP using FastAPI.

- Install with API extras: `poetry install --with dev -E api` or `--all-extras`.
- Run locally: `poetry run uvicorn zyra.api.server:app --reload --host 0.0.0.0 --port 8000`.
- Convenience script: `./scripts/start-api.sh`.

Quick links:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- Examples page (click-to-run): http://localhost:8000/examples

Endpoints:
- `POST /cli/run` → `{ stage, command, args, mode }` where `mode` is `sync` or `async`.
- `GET /jobs/{job_id}` → job status, `stdout`, `stderr`, `exit_code`.
- `GET /jobs/{job_id}/manifest` → JSON list of produced artifacts (name, path, size, mtime, media_type).
- `GET /jobs/{job_id}/download` → download job artifact.
  - Defaults to the packaged ZIP if present; otherwise the first artifact.
  - `?file=NAME` serves a specific file from the manifest.
  - `?zip=1` dynamically packages current artifacts into a ZIP and serves it.
- `POST /upload` → multipart file upload, returns `file_id` and `path`.
- `WS /ws/jobs/{job_id}` → streaming updates (JSON messages).
  - In-memory mode: WebSocket streaming is supported without Redis as a lightweight pub/sub for logs/progress.
  - Messages are JSON lines with keys like `stdout`, `stderr`, `progress`, and a final payload including `exit_code` and `output_file` when available.

Example request:
```
POST /cli/run
{
  "stage": "process",
  "command": "decode-grib2",
  "args": { "file_or_url": "s3://bucket/key.grib2", "backend": "cfgrib" },
  "mode": "sync"
}
```

Notes:
- For convenience, `args.input` is treated as `file_or_url` for processing commands.
- This service runs CLI functions in-process; no shelling out is used.
 - Optional async backend: set `DATAVIZHUB_USE_REDIS=1` and `DATAVIZHUB_REDIS_URL=redis://host:6379/0`; run an RQ worker: `poetry run rq worker zyra`.
 - WebSocket usage: connect to `ws://localhost:8000/ws/jobs/{job_id}`.
   - Without Redis, in-memory streaming is enabled by default.
   - websocat quickstart:
     ```bash
     # After creating a job and getting $JOB
     npx wscat -c ws://localhost:8000/ws/jobs/$JOB
     ```
   - Python websockets:
     ```python
     import asyncio, json, websockets
     async def stream(job_id: str):
         async with websockets.connect(f"ws://localhost:8000/ws/jobs/{job_id}") as ws:
             async for msg in ws:
                 print(json.loads(msg))
     asyncio.run(stream("<job_id>"))
     ```

Curl upload → run (async) → WebSocket stream → download:
```bash
# 1) Upload
FID=$(curl -sF file=@samples/demo.nc http://localhost:8000/upload | jq -r .file_id)
# 2) Run async job
JOB=$(curl -s -H 'Content-Type: application/json' \
  -d '{"stage":"process","command":"convert-format","mode":"async","args":{"file_or_url":"file_id:'"$FID"'","format":"netcdf","stdout":true}}' \
  http://localhost:8000/cli/run | jq -r .job_id)
# 3) Stream logs
npx wscat -c ws://localhost:8000/ws/jobs/$JOB
# 4) Download result
curl -OJL http://localhost:8000/jobs/$JOB/download
```

Upload → Run integration:
- `POST /upload` returns a `file_id` and `path` in the upload directory.
- You can reference uploaded files in `/cli/run` requests by using a placeholder value `file_id:YOUR_ID` on common input args (`file_or_url`, `input`, `file`, `path`, `url`) or by passing `args.file_id` directly.
- The API resolves placeholders to absolute paths under the upload directory before executing the CLI.
- Example (replace the placeholder with a real `file_id`):

```
POST /cli/run
{
  "stage": "process",
  "command": "convert-format",
  "mode": "sync",
  "args": {
    "file_or_url": "file_id:REPLACE_WITH_FILE_ID",
    "format": "netcdf",
    "stdout": true
  }
}
```

Strict file_id resolution:
- Set `DATAVIZHUB_STRICT_FILE_ID=1` to return `404` if any `file_id` cannot be resolved to an uploaded file path at request time.

Results, TTL, and cleanup:
- Results are stored under `DATAVIZHUB_RESULTS_DIR` (default `/tmp/zyra_results/{job_id}/`).
- `/jobs/{job_id}/download` enforces TTL via `DATAVIZHUB_RESULTS_TTL_SECONDS` (default 86400s).
- A background cleanup task removes expired files and prunes empty job dirs at `DATAVIZHUB_RESULTS_CLEAN_INTERVAL_SECONDS` (default 3600s).
- For heavier-duty cleanup, consider a sidecar (e.g., `tmpreaper`) targeting the results dir.

In‑memory job TTL (non‑Redis mode):
- When Redis is disabled, the API uses an in‑memory job store for status/results.
- Completed jobs (`succeeded`, `failed`, `canceled`) are pruned after `DATAVIZHUB_JOBS_TTL_SECONDS` (default 3600s).
- Set `DATAVIZHUB_JOBS_TTL_SECONDS=0` (or negative) to disable in‑memory TTL cleanup.

MIME detection (optional):
- Install extra for richer MIME detection: `poetry install --with mime`.
- Falls back to `mimetypes` when `python-magic` is not installed.

WebSocket client extra:
- Install `poetry install --with ws` to enable the `zyra-cli --ws` streaming option (bundles `websockets`).
See Batch Mode section for multi-input workflows across acquisition, processing, and visualization.
### Running Tests

- Install dev deps and optional extras:
  - Core dev: `poetry install --with dev`
  - Add HTTP client for TestClient-based tests: `poetry add -G dev httpx`
  - Optional WebSocket client for the CLI wrapper: `poetry install --with ws`
- Run tests:
  - All tests: `poetry run pytest -q`
- Snapshot update (paths + hash) in one go: `bash scripts/update_openapi_snapshot.sh`
- Snapshot check (full OpenAPI SHA256): `poetry run pytest -q -k openapi_hash_snapshot`
- Markers: use `-m redis` for Redis-only tests (skipped by default locally).
### Security (API Key)

- Enable API key auth by setting `DATAVIZHUB_API_KEY` (and optionally `DATAVIZHUB_API_KEY_HEADER`, default `X-API-Key`).
- All API routers (CLI, files, jobs) enforce this key; docs remain readable.
- Clients send the key in the header (default): `X-API-Key: <your-key>`.
- WebSocket: include `?api_key=<your-key>` in the URL (e.g., `ws://host/ws/jobs/<job_id>?api_key=KEY`).
- `/examples` includes an API key field and will pass it in requests and WS URLs.
