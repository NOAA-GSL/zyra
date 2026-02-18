<div align="center">
  <img src="assets/branding/zyra-logo.png" width="180" alt="Zyra Logo" />
  <h1>Zyra: Modular, Reproducible Data Workflows for Science</h1>
  <p><em>An Open-Source Python Framework by NOAA Global Systems Laboratory</em></p>
  <p>
    <strong>Eric Hackathorn</strong> &middot; NOAA GSL &middot;
    <a href="https://orcid.org/0000-0002-9693-2093">ORCID</a>
  </p>
  <p>
    <a href="https://pypi.org/project/zyra/"><img src="https://img.shields.io/pypi/v/zyra?color=%231A5A69" alt="PyPI" /></a>
    <a href="https://noaa-gsl.github.io/zyra/"><img src="https://img.shields.io/badge/docs-Sphinx-blue" alt="Docs" /></a>
    <a href="https://doi.org/10.5281/zenodo.16923323"><img src="https://img.shields.io/badge/DOI-10.5281%2Fzenodo.16923323-blue" alt="DOI" /></a>
    <a href="https://github.com/NOAA-GSL/zyra"><img src="https://img.shields.io/github/license/NOAA-GSL/zyra" alt="License" /></a>
  </p>
</div>

---

## The Challenge

Environmental and scientific workflows span heterogeneous data sources (HTTP, FTP, S3, APIs) and formats (GRIB2, NetCDF, GeoTIFF). They require repeatable transformation chains and produce diverse outputs -- static maps, animations, interactive pages, and datasets. Existing approaches often rely on ad-hoc scripts that break when data changes and lack reproducibility across teams and environments.

**Zyra** provides a light-weight, CLI-first framework that standardizes common steps while remaining extensible for domain-specific logic.

---

## The Pipeline: 8 Composable Stages

```mermaid
graph LR
    A["1. Import\n(acquire)"] --> B["2. Process\n(transform)"]
    B --> C["3. Simulate"]
    C --> D["4. Decide\n(optimize)"]
    D --> E["5. Visualize\n(render)"]
    E --> F["6. Narrate"]
    F --> G["7. Verify"]
    G --> H["8. Export\n(disseminate)"]

    style A fill:#00529E,stroke:#00172D,color:#FEFEFE,stroke-width:2px
    style B fill:#2C670C,stroke:#00172D,color:#FEFEFE,stroke-width:2px
    style C fill:#8B8985,stroke:#A3A29D,color:#FEFEFE,stroke-width:1px,stroke-dasharray:5 5
    style D fill:#8B8985,stroke:#A3A29D,color:#FEFEFE,stroke-width:1px,stroke-dasharray:5 5
    style E fill:#576216,stroke:#00172D,color:#FEFEFE,stroke-width:2px
    style F fill:#1A5A69,stroke:#00172D,color:#FEFEFE,stroke-width:2px
    style G fill:#5F9DAE,stroke:#00172D,color:#00172D,stroke-width:2px
    style H fill:#00529E,stroke:#00172D,color:#FEFEFE,stroke-width:2px
```

| Stage | Purpose | CLI |
|-------|---------|-----|
| **Import** | Fetch from HTTP/S, S3, FTP, REST API | `zyra acquire` |
| **Process** | Decode, subset, convert (GRIB2, NetCDF, GeoTIFF) | `zyra process` |
| **Simulate** | Generate synthetic/test data | *planned* |
| **Decide** | Parameter optimization and selection | *planned* |
| **Visualize** | Static maps, plots, animations, interactive | `zyra visualize` |
| **Narrate** | AI-driven captions, summaries, reports | `zyra narrate` |
| **Verify** | Quality checks and metadata validation | `zyra verify` |
| **Export** | Push to S3, FTP, Vimeo, local, HTTP POST | `zyra export` |

Stages are **composable** -- use only what you need. Stages support **streaming** via stdin/stdout for Unix-style chaining:

```bash
zyra acquire http $URL -o - | zyra process convert-format - netcdf --stdout | zyra visualize heatmap --input - --var TMP -o plot.png
```

---

## Use Case: HRRR Weather Model Processing

Acquire the latest High-Resolution Rapid Refresh forecast, convert to NetCDF, and visualize temperature:

```bash
zyra acquire http https://noaa-hrrr-bdp-pds.s3.amazonaws.com/hrrr.20240101/conus/hrrr.t00z.wrfsfcf00.grib2 -o hrrr.grib2
zyra process convert-format hrrr.grib2 netcdf -o hrrr.nc
zyra visualize heatmap --input hrrr.nc --var TMP --colorbar --output hrrr_temp.png
```

<div align="center">
  <img src="assets/generated/heatmap.png" width="500" alt="Heatmap visualization" />
  <br/><em>Heatmap rendered by <code>zyra visualize heatmap</code></em>
</div>

---

## Use Case: Drought Animation Pipeline

A real-world production workflow syncs weekly drought risk frames from NOAA FTP, fills gaps, and composes a video -- all defined as a declarative YAML swarm manifest:

```mermaid
graph TD
    DL["download_frames\n(import / ftp-sync)"] --> SC["scan_frames\n(transform / metadata)"]
    SC --> FM["fill_missing\n(process / pad-missing)"]
    FM --> CA["compose_animation\n(visualize / compose-video)"]
    CA --> SL["save_local\n(export / local)"]

    style DL fill:#00529E,stroke:#00172D,color:#FEFEFE,stroke-width:2px
    style SC fill:#2C670C,stroke:#00172D,color:#FEFEFE,stroke-width:2px
    style FM fill:#2C670C,stroke:#00172D,color:#FEFEFE,stroke-width:2px
    style CA fill:#576216,stroke:#00172D,color:#FEFEFE,stroke-width:2px
    style SL fill:#00529E,stroke:#00172D,color:#FEFEFE,stroke-width:2px
```

```bash
zyra swarm samples/swarm/drought_animation.yaml --parallel --memory provenance.sqlite
```

Each agent logs provenance (start time, duration, command, exit code) to a SQLite store for full reproducibility.

---

## Use Case: AI/LLM Narration Swarm

Zyra orchestrates multi-agent workflows where LLM-powered agents generate, critique, and refine narrative outputs:

```mermaid
graph TD
    UI["User Intent\n(natural language)"] --> PL["Planner\n(zyra plan)"]
    PL --> VE["Value Engine\n(suggest augmentations)"]
    VE --> DAG["Execution DAG\n(parallel / sequential)"]
    DAG --> A1["Stage Agent\n(acquire)"]
    DAG --> A2["Stage Agent\n(process)"]
    DAG --> A3["Stage Agent\n(visualize)"]
    DAG --> A4["LLM Agent\n(narrate)"]
    A1 --> PR["Provenance\n(SQLite)"]
    A2 --> PR
    A3 --> PR
    A4 --> PR

    style UI fill:#50452C,stroke:#00172D,color:#FEFEFE,stroke-width:2px
    style PL fill:#1A5A69,stroke:#00172D,color:#FEFEFE,stroke-width:2px
    style VE fill:#FFC107,stroke:#00172D,color:#00172D,stroke-width:2px
    style DAG fill:#00529E,stroke:#00172D,color:#FEFEFE,stroke-width:2px
    style A1 fill:#2C670C,stroke:#00172D,color:#FEFEFE,stroke-width:2px
    style A2 fill:#2C670C,stroke:#00172D,color:#FEFEFE,stroke-width:2px
    style A3 fill:#576216,stroke:#00172D,color:#FEFEFE,stroke-width:2px
    style A4 fill:#1A5A69,stroke:#00172D,color:#FEFEFE,stroke-width:2px
    style PR fill:#5F9DAE,stroke:#00172D,color:#00172D,stroke-width:2px
```

The narration swarm chains **context**, **summary**, **critic**, and **editor** agents, each backed by configurable LLM providers:

| Provider | Usage |
|----------|-------|
| OpenAI | `--provider openai --model gpt-4` |
| Ollama | `--provider ollama --model gemma` |
| Gemini | `--provider gemini` |
| Mock | `--provider mock` (offline testing) |

Outputs are validated against Pydantic schemas with optional guardrails (RAIL files) for structured, reproducible results.

---

## Use Case: Reproducible Pipeline Configs

Define multi-stage pipelines as YAML -- no scripting required:

```yaml
name: FTP to Local Video
stages:
  - stage: acquire
    command: ftp
    args:
      path: ftp://ftp.nnvl.noaa.gov/SOS/DroughtRisk_Weekly
      sync_dir: ./frames
      since_period: "P1Y"
  - stage: visualize
    command: compose-video
    args:
      frames: ./frames
      output: video.mp4
      fps: 4
  - stage: export
    command: local
    args:
      input: video.mp4
      path: /output/video.mp4
```

```bash
zyra run pipeline.yaml                          # execute
zyra run pipeline.yaml --dry-run                 # preview commands
zyra run pipeline.yaml --set visualize.fps=8     # override parameters
```

---

## Building Off the Foundation

Zyra provides three layers of access — from terminal commands to autonomous AI agents — all sharing the same 8-stage pipeline architecture:

```mermaid
graph BT
    CLI["1. CLI\nzyra [command]"] --> API["2. Python API\nimport zyra"]
    API --> MCP["3. MCP + AI Agents\ntools/discover"]

    style CLI fill:#2C670C,stroke:#00172D,color:#FEFEFE,stroke-width:2px
    style API fill:#00529E,stroke:#00172D,color:#FEFEFE,stroke-width:2px
    style MCP fill:#1A5A69,stroke:#00172D,color:#FEFEFE,stroke-width:2px
```

| Layer | Description |
|-------|-------------|
| **CLI** | Scriptable, streaming commands via `stdin/stdout` for Unix-style pipeline composition |
| **Python API** | Programmatic access via `import zyra` for custom modules and automated workflows |
| **MCP + AI Agents** | Every pipeline stage exposed as an MCP tool for LLM agent discovery and execution |

Whether invoked from bash, Python, REST (`zyra serve`), or an AI agent, every execution follows the same architecture with full provenance tracking.

---

## Visualization Gallery

<table>
  <tr>
    <td align="center">
      <img src="assets/generated/heatmap.png" width="380" alt="Heatmap" /><br/>
      <code>zyra visualize heatmap</code>
    </td>
    <td align="center">
      <img src="assets/generated/contour.png" width="380" alt="Contour" /><br/>
      <code>zyra visualize contour</code>
    </td>
  </tr>
  <tr>
    <td align="center">
      <img src="assets/generated/vector.png" width="380" alt="Vector Field" /><br/>
      <code>zyra visualize vector</code>
    </td>
    <td align="center">
      <img src="assets/generated/timeseries.png" width="380" alt="Time Series" /><br/>
      <code>zyra visualize timeseries</code>
    </td>
  </tr>
</table>

---

## Key Features

- **Scientific formats**: GRIB2, NetCDF, GeoTIFF with xarray, cfgrib, rasterio
- **Connectors**: HTTP/S, S3, FTP, REST API, Vimeo
- **Visualization**: heatmaps, contours, vectors, particles, animations, interactive maps (Folium, Plotly)
- **AI integration**: multi-agent narration swarm, planning engine, value engine, guardrails
- **Provenance**: SQLite-based event logging for full reproducibility
- **Service mode**: FastAPI REST API + MCP tools for LLM integration
- **Modular extras**: `pip install "zyra[visualization]"`, `"zyra[processing]"`, `"zyra[llm]"`, or `"zyra[all]"`
- **Python 3.10+** &middot; **Apache 2.0** &middot; **CLI-first** &middot; **Streaming-friendly**

---

## Get Started

```bash
pip install zyra          # core
pip install "zyra[all]"   # everything
zyra --help               # explore commands
```

| Resource | Link |
|----------|------|
| GitHub | [github.com/NOAA-GSL/zyra](https://github.com/NOAA-GSL/zyra) |
| PyPI | [pypi.org/project/zyra](https://pypi.org/project/zyra/) |
| Documentation | [noaa-gsl.github.io/zyra](https://noaa-gsl.github.io/zyra/) |
| Wiki | [github.com/NOAA-GSL/zyra/wiki](https://github.com/NOAA-GSL/zyra/wiki) |
| DOI | [10.5281/zenodo.16923323](https://doi.org/10.5281/zenodo.16923323) |
