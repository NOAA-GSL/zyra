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
- [Quick Composition Examples](#quick-composition-examples)
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
- Everything: `pip install "datavizhub[all]"`

Notes:
- Core install keeps footprint small; optional features pull in heavier deps (e.g., Cartopy, SciPy, ffmpeg-python).
- Some example scripts may import plotting libs; install `[visualization]` if you use those flows.

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
- Dev container: A read-only mirror of the wiki is auto-cloned into `wiki` when the dev container starts. It auto-refreshes at most once per hour. This folder is ignored by Git and is not part of the repository on GitHub.
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
