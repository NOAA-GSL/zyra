# DataVizHub

## Overview
DataVizHub is a utility library for building data-driven visual products. It provides composable helpers for data transfer (FTP/HTTP/S3/Vimeo), data processing (GRIB/imagery/video), and visualization (matplotlib + basemap overlays). Use these pieces to script your own pipelines; this repo focuses on the reusable building blocks rather than end-user scripts.

 This README documents the library itself and shows how to compose the components. For complete runnable examples, see the examples repos when available, or adapt the snippets below.

[![PyPI version](https://img.shields.io/pypi/v/datavizhub.svg)](https://pypi.org/project/datavizhub/) [![Docs](https://img.shields.io/badge/docs-GitHub_Pages-0A7BBB)](https://noaa-gsl.github.io/datavizhub/) [![Chat with DataVizHub Helper Bot](https://img.shields.io/badge/ChatGPT-DataVizHub_Helper_Bot-00A67E?logo=openai&logoColor=white)](https://chatgpt.com/g/g-6897a3dd5a7481918a55ebe3795f7a26-datavizhub-helper-bot)

## Table of Contents
- [Overview](#overview)
- [Features](#features)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Install (Poetry)](#install-poetry)
- [Install (pip extras)](#install-pip-extras)
 - [Stage-Specific Installs](#stage-specific-installs)
- [CLI Overview](#cli-overview)
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
- [Acquisition](#acquisition-layer): `DataAcquirer`, `FTPManager`, `HTTPHandler`, `S3Manager`, `VimeoManager` (in `datavizhub.acquisition`).
- [Processing](#processing-layer): `DataProcessor`, `VideoProcessor`, `GRIBDataProcessor` (in `datavizhub.processing`).
- [Visualization](#visualization-layer): `PlotManager`, `ColormapManager` (with included basemap/overlay assets in `datavizhub.assets`).
- [Utilities](#utilities): `CredentialManager`, `DateManager`, `FileUtils`, `ImageManager`, `JSONFileManager` (in `datavizhub.utils`).


## Project Structure
- `acquisition/`: I/O helpers (S3, FTP, HTTP, Vimeo).
- `processing/`: data/video processing (GRIB/NetCDF, FFmpeg-based video).
- `visualization/`: plotting utilities and colormaps.
- `utils/`: shared helpers (dates, files, images, credentials).
- `assets/images/`: packaged basemaps and overlays used by plots.

## Prerequisites
- Python 3.10+
- FFmpeg and ffprobe on PATH for video-related flows.
- Optional: AWS credentials for S3; Vimeo API credentials for upload flows.

## Install (Poetry)
- Core dev env: `poetry install --with dev`
- With optional extras: `poetry install --with dev -E datatransfer -E processing -E visualization` (or `--all-extras`)
- Spawn a shell: `poetry shell`
- One-off run: `poetry run python -c "print('ok')"`

Notes for development:
- Optional integrations (S3 via boto3, Vimeo via PyVimeo, HTTP via requests) are provided as extras, not dev deps.
- Opt into only what you need using `-E <extra>` flags, or use `--all-extras` for a full-featured env.

## Install (pip extras)
- Core only: `pip install datavizhub`
- Datatransfer deps: `pip install "datavizhub[datatransfer]"`
- Processing deps: `pip install "datavizhub[processing]"`
- Visualization deps: `pip install "datavizhub[visualization]"`
- Interactive deps: `pip install "datavizhub[interactive]"`
- Everything: `pip install "datavizhub[all]"`

Focused installs for GRIB2/NetCDF/GeoTIFF:

```
pip install "datavizhub[grib2,netcdf,geotiff]"
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

- Acquisition stage:
  - Pip: `pip install -e .[datatransfer]`
  - Poetry: `poetry install --with dev -E datatransfer`
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
  - Heatmap: `python -m datavizhub.cli heatmap --input samples/demo.npy --output heatmap.png`
  - Contour: `python -m datavizhub.cli contour --input samples/demo.nc --var T2M --output contour.png --levels 5,10,15 --filled`

Focused extras remain available for targeted installs:
- GRIB2 only: `pip install -e .[grib2]`
- NetCDF only: `pip install -e .[netcdf]`
- GeoTIFF export: `pip install -e .[geotiff]`

Note on interactive installs:
- The `interactive` extra pulls in Folium and/or Plotly, which increase dependency size and runtime memory. If you only need static images and animations, you can skip `interactive` and install just `visualization`.

## CLI Overview

DataVizHub ships a single `datavizhub` CLI organized into four groups that mirror the pipeline stages, plus a `run` helper for config-driven pipelines.

### CLI Tree

```
datavizhub
├─ acquire            # Ingest/fetch bytes from sources
│  ├─ http            # acquire http <url> [-o out|-]
│  ├─ s3              # acquire s3 --url s3://bucket/key [-o out|-]
│  ├─ ftp             # acquire ftp <ftp://host/path or host/path> [-o out|-]
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
│  └─ post            # HTTP POST
└─ run                # Run a pipeline from YAML/JSON (coming soon)
```

Notes
- All subcommands accept `-` for stdin/stdout where applicable to support piping.
- Legacy flat commands (e.g., `datavizhub decode-grib2`, `datavizhub contour`) remain available for backward compatibility.

### Quick Usage by Group

- Acquire
  - HTTP to file: `datavizhub acquire http https://example.com/data.bin -o data.bin`
  - S3 to stdout: `datavizhub acquire s3 --url s3://bucket/key -o -`

- Process (streaming-friendly)
  - Decode GRIB2 to raw bytes via `.idx` subset: `datavizhub process decode-grib2 s3://bucket/file.grib2 --pattern ":TMP:surface:" --raw > subset.grib2`
  - Convert stdin to NetCDF: `cat subset.grib2 | datavizhub process convert-format - netcdf --stdout > out.nc`

- Visualize
  - Contour PNG from NetCDF: `datavizhub visualize contour --input out.nc --var TMP --output contour.png --levels 10 --filled`
  - Animate frames and compose to MP4: `datavizhub visualize animate --mode heatmap --input cube.npy --output-dir frames && datavizhub visualize compose-video --frames frames -o out.mp4`

- Decimate
  - Upload to S3 from stdin: `cat out.png | datavizhub decimate s3 -i - --url s3://bucket/products/out.png`
- HTTP POST JSON: `echo '{"ok":true}' | datavizhub decimate post -i - https://example.com/ingest --content-type application/json`

## Quick Composition Examples

## Acquisition Layer

The `datavizhub.acquisition` package standardizes data source integrations under a common `DataAcquirer` interface.

- DataAcquirer: abstract base with `connect()`, `fetch(remote, local=None)`, `list_files(remote=None)`, `upload(local, remote)`, `disconnect()`.
- Helpers: context manager support (`with` auto-connect/disconnect), `fetch_many()` batch helper, and utility methods for path handling and simple retries.
- Managers: `FTPManager`, `HTTPHandler`, `S3Manager`, `VimeoManager` expose consistent behavior and capability flags.
  - Capabilities: each manager advertises a `CAPABILITIES` set, e.g. `{'fetch','upload','list'}` for FTP/S3.
  - Unsupported ops raise `NotSupportedError` (e.g., `HTTPHandler.upload`).

Examples:

```
from datavizhub.acquisition.ftp_manager import FTPManager

with FTPManager(host="ftp.example.com") as ftp:
    ftp.fetch("/pub/file.txt", "file.txt")

from datavizhub.acquisition.s3_manager import S3Manager
s3 = S3Manager(access_key, secret_key, "my-bucket")
s3.connect()
s3.upload("local.nc", "path/object.nc")
s3.disconnect()
```

### Advanced Acquisition: GRIB subsetting, byte ranges, and listing

Managers expose optional advanced helpers (inspired by NODD) to speed up GRIB workflows and large file transfers.

- .idx subsetting
  - S3 example (public bucket, unsigned):
    ```python
    from datavizhub.acquisition.s3_manager import S3Manager

    s3 = S3Manager(None, None, bucket_name="noaa-hrrr-bdp-pds", unsigned=True)
    lines = s3.get_idx_lines("hrrr.20230801/conus/hrrr.t00z.wrfsfcf00.grib2")
    ranges = s3.idx_to_byteranges(lines, r"(:TMP:surface|:PRATE:surface)")
    data = s3.download_byteranges("hrrr.20230801/conus/hrrr.t00z.wrfsfcf00.grib2", ranges.keys())
    ```

- Pattern-based listing (regex)
  - S3 prefix listing with regex filter:
    ```python
    keys = s3.list_files("hrrr.20230801/conus/", pattern=r"wrfsfcf\d+\.grib2$")
    ```
  - HTTP directory-style index scraping with regex filter:
    ```python
    from datavizhub.acquisition import HTTPManager
    urls = HTTPManager().list_files(
        "https://nomads.ncep.noaa.gov/pub/data/nccf/com/hrrr/prod/",
        pattern=r"\.grib2$",
    )
    ```

- Parallel range downloads
  - HTTP byte ranges:
    ```python
    from datavizhub.acquisition import HTTPManager
    http = HTTPManager()
    lines = http.get_idx_lines("https://example.com/path/file.grib2")
    ranges = http.idx_to_byteranges(lines, r"GUST")
    blob = http.download_byteranges("https://example.com/path/file.grib2", ranges.keys(), max_workers=10)
    ```
  - FTP byte ranges (uses REST and one connection per thread):
    ```python
    from datavizhub.acquisition import FTPManager
    ftp = FTPManager(host="ftp.example.com")
    ftp.connect()
    lines = ftp.get_idx_lines("/pub/file.grib2")
    ranges = ftp.idx_to_byteranges(lines, r"PRES:surface")
    blob = ftp.download_byteranges("/pub/file.grib2", ranges.keys(), max_workers=4)
    ftp.disconnect()
    ```

Notes
- Pattern filters use Python regular expressions (`re.search`) applied to full keys/paths/URLs.
- `.idx` resolution appends `.idx` to the GRIB path unless a fully qualified `.idx` path is given.
- For unsigned public S3 buckets, pass `unsigned=True` as shown above.

## Processing Layer

The `datavizhub.processing` package standardizes processors under a common `DataProcessor` interface.

- DataProcessor: abstract base with `load(input_source)`, `process(**kwargs)`, `save(output_path=None)`, and optional `validate()`.
- Processors: `VideoProcessor` (image sequences → video via FFmpeg), `GRIBDataProcessor` (GRIB files → NumPy arrays + utilities).
- Notes: `VideoProcessor` requires system `ffmpeg` and `ffprobe` on PATH; GRIB utilities rely on `pygrib`, `siphon`, and `scipy` where used.

Examples:

```
# Video: compile image frames into a video
from datavizhub.processing.video_processor import VideoProcessor

vp = VideoProcessor(input_directory="./frames", output_file="./out/movie.mp4")
vp.load("./frames")
if vp.validate():
    vp.process()
    vp.save("./out/movie.mp4")
```

```
# GRIB: read a GRIB file to arrays and dates
from datavizhub.processing.grib_data_processor import GRIBDataProcessor

gp = GRIBDataProcessor()
data_list, dates = gp.process(grib_file_path="/path/to/file.grib2", shift_180=True)
```

### Processing GRIB2 and NetCDF (bytes-first)

Decode a GRIB2 subset returned as bytes, extract a variable, and write NetCDF:

```
from datavizhub.processing import grib_decode, extract_variable, convert_to_format

dec = grib_decode(data_bytes, backend="cfgrib")  # default backend
da = extract_variable(dec, r"^TMP$")  # exact/regex match
nc_bytes = convert_to_format(dec, "netcdf", var="TMP")
```

Work with NetCDF directly and subset spatially/temporally:

```
from datavizhub.processing import load_netcdf, subset_netcdf

ds = load_netcdf(nc_bytes)
sub = subset_netcdf(ds, variables=["TMP"], bbox=(-130,20,-60,55), time_range=("2024-01-01","2024-01-02"))
```

Notes and fallbacks:
- Default backend is `cfgrib` (xarray + eccodes). If unavailable or failing, `pygrib` is attempted when requested; `wgrib2 -json` can be used as a metadata fallback.
- GeoTIFF conversion requires `rioxarray`/`rasterio` and supports a single variable; specify `var` when multiple variables exist.
- GRIB2→NetCDF uses `xarray.to_netcdf()` when possible with a `wgrib2 -netcdf` fallback if present.
- Generic NetCDF→GRIB2 is not supported by `wgrib2`. If `cdo` is installed, `convert_to_grib2()` uses `cdo -f grb2 copy` automatically; otherwise a clear exception is raised.

CLI helpers (grouped commands):
- `datavizhub process decode-grib2 <file_or_url> [--backend cfgrib|pygrib|wgrib2]`
- `datavizhub process extract-variable <file_or_url> <pattern> [--backend ...]`
- `datavizhub process convert-format <file_or_url> <netcdf|geotiff> -o out.ext [--var NAME] [--backend ...]`

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
  - Usage: `cat tests/testdata/demo.nc | datavizhub run samples/pipelines/nc_passthrough.yaml > out.nc`
- `nc_to_file.yaml`: read NetCDF from stdin, then write to `out.nc` via `decimate local`.
  - Usage: `cat tests/testdata/demo.nc | datavizhub run samples/pipelines/nc_to_file.yaml`
- `ftp_to_s3.yaml`: template for FTP → video composition → S3 upload (placeholders, not CI-safe).
- `extract_variable_to_file.yaml`: extract TMP from stdin, convert to NetCDF, and write to file.
  - Usage: `cat tests/testdata/demo.nc | datavizhub run samples/pipelines/extract_variable_to_file.yaml`
- `compose_video_to_local.yaml`: compose frames in a directory to MP4 and copy locally.

Overrides
- Global override (applied where key exists): `--set var=TMP`
- Per-stage override using 1-based index (1-based): `--set 2.var=TMP` (sets key `var` on stage 2 only)
- Stage-name override (uses aliases acquisition/ingest→acquire, processing→process, visualization→visualize, decimation/egress→decimate):
  - `--set processing.var=TMP`
  - `--set decimation.backend=local`

Dry run and argv output
- Validate and print the expanded stage argv without executing:
  - Text: `datavizhub run pipeline.yaml --dry-run`
  - JSON: `datavizhub run pipeline.yaml --dry-run --print-argv-format=json`
    - Structure:
      ```json
      [
        {"stage": 1, "name": "acquire", "argv": ["datavizhub", "acquire", "http", "https://..."]},
        {"stage": 2, "name": "process", "argv": ["datavizhub", "process", "convert-format", "-", "netcdf"]}
      ]
      ```

Error handling
- Stop on first error (default) or continue executing remaining stages:
  - `datavizhub run pipeline.yaml --continue-on-error`

- Lint/format (if enabled in your env):
  - `poetry run black . && poetry run isort . && poetry run flake8`

## Chaining Commands with --raw and --stdout

The CLI supports streaming binary data through stdout/stdin so you can compose offline pipelines without touching disk.

- `.idx` → extract → convert (one-liner):
  ```bash
  datavizhub decode-grib2 file.grib2 --pattern "TMP" --raw | \
  datavizhub extract-variable - "TMP" --stdout --format grib2 | \
  datavizhub convert-format - geotiff --stdout > tmp.tif
  ```

- Notes on tools and fallbacks:
  - `wgrib2`: When available, `extract-variable --stdout` uses `wgrib2 -match` to subset and emits either GRIB2 (`-grib`) or NetCDF (`-netcdf`).
  - `CDO`: If converting NetCDF→GRIB2 is needed without `wgrib2` support, `convert_to_grib2()` uses `cdo -f grb2 copy` when `cdo` is installed.
  - Python-only fallback: If `wgrib2` is not present, NetCDF streaming still works via xarray (`to_netcdf()`), while GRIB2 streaming may not be available depending on your environment.

- Auto-detection in `convert-format`:
  - `convert-format` can read from stdin (`-`) and auto-detects GRIB2 vs NetCDF by magic bytes. NetCDF is opened with xarray; GRIB2 uses the configured backend to decode.

Bytes-first demos:
- Use `.idx`-aware subsetting directly with URLs: `datavizhub decode-grib2 https://.../file.grib2 --pattern ":(UGRD|VGRD):10 m above ground:"`
- Pipe small outputs without temp files: `datavizhub convert-format local.grib2 netcdf --stdout | hexdump -C | head`

Offline demo assets:
- Tiny NetCDF file: `tests/testdata/demo.nc`
- Tiny GRIB2 file: please place a small sample as `tests/testdata/demo.grib2` (we can add one if provided).


## Visualization Layer

Plot a data array with a basemap

```
import numpy as np
from importlib.resources import files, as_file
from datavizhub.visualization import PlotManager, ColormapManager

# Example data
data = np.random.rand(180, 360)

# Locate packaged basemap asset
resource = files("datavizhub.assets").joinpath("images/earth_vegetation.jpg")
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
poetry run python -m datavizhub.cli heatmap \
  --input samples/demo.npy \
  --output out.png \
  --map-type tile \
  --tile-zoom 3
```

- Contour over a named tile source:

```
poetry run python -m datavizhub.cli contour \
  --input samples/demo.npy --output contour.png \
  --levels 10 --filled \
  --map-type tile --tile-source Stamen.TerrainBackground
```

- Vector quiver over tiles:

```
poetry run python -m datavizhub.cli vector \
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
- Pip: `pip install "datavizhub[interactive]"`

Examples
- Folium heatmap from a NumPy array:

```
python -m datavizhub.cli interactive \
  --input samples/demo.npy \
  --output out.html \
  --engine folium \
  --mode heatmap
```

- Plotly heatmap (standalone HTML):

```
python -m datavizhub.cli interactive \
  --input samples/demo.npy \
  --output out_plotly.html \
  --engine plotly \
  --mode heatmap \
  --width 600 --height 300
```

- Folium points from CSV:

```
python -m datavizhub.cli interactive \
  --input samples/points.csv \
  --output points.html \
  --engine folium \
  --mode points
```

- Folium points with a time column (TimeDimension):

```
python -m datavizhub.cli interactive \
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
python -m datavizhub.cli interactive \
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
from datavizhub.acquisition.ftp_manager import FTPManager
from datavizhub.acquisition.vimeo_manager import VimeoManager
from datavizhub.processing import VideoProcessor

ftp = FTPManager(host="ftp.example.com", username="anonymous", password="test@test.com")
ftp.connect()
ftp.fetch("/pub/images/img_0001.png", "/tmp/frames/img_0001.png")
# ...download the rest of the frames as needed...

VideoProcessor("/tmp/frames", "/tmp/out.mp4").process_videos(fps=30)

vimeo = VimeoManager(client_id="...", client_secret="...", access_token="...")
vimeo.upload_video("/tmp/out.mp4", "Latest Render")
```

## Utilities

The `datavizhub.utils` package provides shared helpers for credentials, dates, files, images, and small JSON configs.

- CredentialManager: read/manage dotenv-style secrets without exporting globally.
- DateManager: parse timestamps in filenames, compute date ranges, and reason about frame cadences.
- FileUtils: simple file/directory helpers like `remove_all_files_in_directory`.
- ImageManager: basic image inspection and change detection.
- JSONFileManager: read/update/write simple JSON files.

Examples:

```
# Credentials
from datavizhub.utils import CredentialManager

with CredentialManager(".env", namespace="MYAPP_") as cm:
    cm.read_credentials(expected_keys=["API_KEY"])  # expects MYAPP_API_KEY
    token = cm.get_credential("API_KEY")
```

```
# Dates
from datavizhub.utils import DateManager

dm = DateManager(["%Y%m%d"])
start, end = dm.get_date_range("7D")
print(dm.is_date_in_range("frame_20240102.png", start, end))
```

Capabilities and batch fetching:

```
from datavizhub.acquisition import DataAcquirer
from datavizhub.acquisition.ftp_manager import FTPManager

acq: DataAcquirer = FTPManager("ftp.example.com")
print(acq.capabilities)  # e.g., {'fetch','upload','list'}

with acq:
    results = acq.fetch_many(["/pub/a.txt", "/pub/b.txt"], dest_dir="downloads")
    for remote, ok in results:
        print(remote, ok)
```


Minimal pipeline: build video from images and upload to S3

```python
from datavizhub.processing import VideoProcessor
from datavizhub.acquisition.s3_manager import S3Manager

vp = VideoProcessor(input_directory="/data/images", output_file="/data/out/movie.mp4")
vp.load("/data/images")
if vp.validate():
    vp.process()
    vp.save("/data/out/movie.mp4")

s3 = S3Manager("ACCESS_KEY", "SECRET_KEY", "my-bucket")
s3.connect()
s3.upload("/data/out/movie.mp4", "videos/movie.mp4")
s3.disconnect()
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
- Primary: Project wiki at https://github.com/NOAA-GSL/datavizhub/wiki
- API docs (GitHub Pages): https://noaa-gsl.github.io/datavizhub/
- Dev container: A read-only mirror of the wiki is auto-cloned into `/wiki` when the dev container starts. It auto-refreshes at most once per hour. This folder is ignored by Git and is not part of the repository on GitHub.
- Force refresh: `bash .devcontainer/postStart.sh --force` (or set `DOCS_REFRESH_SECONDS` to adjust the hourly cadence).
- Note: There is no `docs/` directory in the main repo. If you are not using the dev container, read the wiki directly.

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
from datavizhub.acquisition.s3_manager import S3Manager
from datavizhub.processing.video_processor import VideoProcessor

s3 = S3Manager("AKIA...", "SECRET...", "my-bucket"); s3.connect()
print(s3.capabilities)  # {'fetch','upload','list'}

vp = VideoProcessor("./frames", "./out.mp4")
print(vp.features)      # {'load','process','save','validate'}
```

## License
Distributed under the MIT License. See [LICENSE](LICENSE).

## Links
- Source: https://github.com/NOAA-GSL/datavizhub
- PyPI: https://pypi.org/project/datavizhub/
