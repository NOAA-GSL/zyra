## Goal
Transform the existing CLI into a complete, modular, four-stage pipeline:
```
[ Acquisition (Ingest) ] → [ Processing ] → [ Visualization ] → [ Decimation (Egress) ]
```
- Rename `acquisition/` to `connectors/` to reflect both inbound and outbound data flow.
- Split into `ingest/` and `egress/` submodules, sharing common backend code in `backends/`.
- Each stage has its own CLI subcommands.
- All commands accept stdin/stdout for chaining.
- Add `run` command to execute pipelines from YAML/JSON config files.

---

## 1. Refactor CLI Structure

### 1.1 Top-Level Groups
- Modify `src/zyra/cli.py`:
  - Create **four top-level subparsers**: `acquire`, `process`, `visualize`, `decimate`, plus `run`.
  - Remove existing flat commands (`decode-grib2`, `convert-format`, etc.) and nest under `process`.

### 1.2 Module Self-Registration
- In each stage's `__init__.py`, add:
```python
def register_cli(subparsers):
    """Register CLI commands for this stage."""
```
- `cli.py` calls:
```python
from zyra.connectors import ingest, egress
from zyraimport processing, visualization

ingest.register_cli(acquire_subparser)
processing.register_cli(process_subparser)
visualization.register_cli(visualize_subparser)
egress.register_cli(decimate_subparser)
```

---

## 2. Connectors Module Structure

```
src/zyra/connectors/
    backends/
        s3.py
        http.py
        ftp.py
        vimeo.py
    ingest/
        __init__.py
        ingest_manager.py
    egress/
        __init__.py
        egress_manager.py
```

### 2.1 Ingest
- `ingest_manager.py` maps CLI commands to inbound fetchers:
  - `acquire http <url>` → `backends/http.py`
  - `acquire s3 <bucket>/<key>` → `backends/s3.py`
  - `acquire ftp <server>/<path>` → `backends/ftp.py`
  - `acquire vimeo <video_id>` → `backends/vimeo.py`
- All commands:
  - Accept `--output` (default `-` = stdout).
  - Stream binary data directly.

### 2.2 Egress
- `egress_manager.py` maps CLI commands to outbound writers:
  - `decimate local <path>`
  - `decimate s3 <bucket>/<key>` → `backends/s3.py`
  - `decimate ftp <server>/<path>` → `backends/ftp.py`
  - `decimate post <url>` → `backends/http.py`
- All commands:
  - Accept stdin (`-`) as input.
  - Write binary data directly.

---

## 3. Processing (`src/zyra/processing/`)
- Move existing CLI functions into `process` namespace:
  - `decode-grib2`
  - `extract-variable`
  - `convert-format`
- Add missing processors:
  - NetCDF subset/extract
  - Video conversion
- All commands:
  - Accept stdin/stdout.
  - Auto-detect formats.

---

## 4. Visualization (`src/zyra/visualization/`)
- New commands:
  - `visualize plot --type contour|timeseries --var <name>`
  - `visualize colormap --set <name>`
  - `visualize animate --frames <dir> --output <video>`
- Output:
  - Default to stdout.
  - Save to file if `--output` provided.

---

## 5. Shared Features

### 5.1 I/O Utilities
`src/zyra/utils/io_utils.py`:
```python
def open_input(path_or_dash):
    return sys.stdin.buffer if path_or_dash == "-" else open(path_or_dash, "rb")

def open_output(path_or_dash):
    return sys.stdout.buffer if path_or_dash == "-" else open(path_or_dash, "wb")
```

### 5.2 Format Detection
- `detect_format()` using magic bytes.

### 5.3 Common CLI Options
- `cli_common.py` for shared flags: `--var`, `--bbox`, `--time`, `--format`, `--backend`.

---

## 6. Pipeline Configs

### 6.1 CLI Usage
```bash
zyra run pipeline.yaml
zyra run pipeline.yaml --set var=temp --set output=out.png
```

### 6.2 YAML Example
```yaml
name: Temperature Visualization Pipeline
stages:
  - stage: acquisition
    command: acquire
    args:
      backend: s3
      bucket: bucket-name
      key: data/file.grib2

  - stage: processing
    command: decode-grib2
    args: {}

  - stage: processing
    command: extract-variable
    args:
      var: temperature

  - stage: visualization
    command: plot
    args:
      type: contour
      var: temperature

  - stage: decimation
    command: s3
    args:
      bucket: bucket-name
      key: products/temperature.png
```

### 6.3 Implementation
- New module: `src/zyra/pipeline_runner.py`
- Parse config → apply overrides → execute stages sequentially via pipes or function calls.

---

## 7. Streaming Support
- File-like object support across all commands.
- Chunked reads/writes for large files.

---

## 8. Testing
- Unit tests for each CLI command (file and pipe).
- Integration tests for multi-stage pipelines.
- Pipeline config tests.

---

## 9. Documentation
- Update README to show four-stage CLI and `connectors/` refactor.
- Add "Pipeline Patterns" to wiki.
- Provide sample pipeline configs.

