# Introduction to Zyra

---

**Jump to:**  
[Kid Version](#kid-version) | [High School Version](#high-school-version) | [College Version](#college-version) | [White Paper Version](#white-paper-version)

---

## Kid Version
Imagine you have a big box of LEGO bricks mixed together — some from space sets, some from castles, some from race cars.  
**Zyra** is like a magical robot helper that:
1. **Finds** the bricks you want (getting data from the internet or your computer).  
2. **Puts them in order** (sorting and cleaning the pieces so they fit).  
3. **Builds and shares** something amazing (pictures, videos, or maps you can show to friends) — and sometimes it helps you check your build or tell its story.

It makes science data less messy and more fun to look at.

---

## High School Version
Zyra is a Python tool that:
- **Collects** data from many sources like websites, cloud storage, and scientific file formats.  
- **Processes** it so it’s easier to work with (cutting, reshaping, converting formats).  
- **Visualizes** it in charts, maps, and animations, and can **publish** results.  

Think of it like a factory with up to **eight stations** (you can skip ones you don’t need):
- **Import** (get data) → **Process** (clean/convert) → **Simulate** (make examples) → **Decide** (pick best settings) → **Visualize** (make graphics) → **Narrate** (add captions/reports) → **Verify** (check quality) → **Export** (share).

It’s modular — you can swap out any station for your own tool.

---

## College Version
Zyra is an open-source, modular Python framework for reproducible scientific data workflows organized as up to **eight stages**:
1. **Import** – HTTP/FTP/S3/local fetch and listing; supports manifests and streaming I/O.  
2. **Process** – Subset, transform, and convert (e.g., GRIB2⇄NetCDF, GeoTIFF).  
3. **Simulate** – Generate synthetic or toy datasets for demos/tests.  
4. **Decide** – Explore parameter spaces and select best variants.  
5. **Visualize** – Static maps/plots, animations, and interactive outputs.  
6. **Narrate** – Produce captions, summaries, or pages that contextualize outputs.  
7. **Verify** – Integrity/quality checks, metadata validation, provenance.  
8. **Export** – Write to local paths, S3/FTP, HTTP POST, or video destinations.  

Not all stages are required in every workflow; the pipeline is **composable** and **streaming‑friendly** (stdin/stdout). Under the hood, implemented pieces map to modules like `zyra.connectors` (import/export), `zyra.processing`, `zyra.visualization`, and `zyra.transform`, with shared helpers in `zyra.utils`.

---

## White Paper Version
**Abstract:**  
Zyra is a composable Python framework for end‑to‑end scientific data workflows. It organizes work into eight conceptual stages — import, process, simulate, decide, visualize, narrate, verify, and export — providing reproducibility, modularity, and interoperability across environmental and geospatial datasets.

### Motivation & Scope
Modern environmental workflows span heterogeneous data sources and formats, require repeatable transformations, and produce diverse outputs (plots, animations, interactive pages, datasets). Zyra provides a light‑weight, CLI‑first framework that standardizes common steps while remaining extensible for domain‑specific logic.

### Design Principles
- Modularity: small, composable commands and helpers; opt‑in extras for heavy deps.  
- Streaming by default: stdin/stdout support to avoid temporary files and enable Unix‑style chaining.  
- Reproducibility: explicit configs, deterministic transforms, comprehensive logging and metadata.  
- Interoperability: rely on well‑adopted libraries (xarray, netCDF4, rasterio, matplotlib/cartopy, ffmpeg).  
- Extensibility: pluggable connectors and processors; minimal glue code to register new commands.  

### Architecture (stages → modules)
- Import/Export → `zyra.connectors` (HTTP/FTP/S3/Vimeo, local paths, HTTP POST) with list/filter, sync, and streaming I/O.  
- Process → `zyra.processing` (GRIB2 decoding, NetCDF/GeoTIFF conversion, extraction, subsetting); `zyra.transform` for lightweight metadata updates.  
- Visualize → `zyra.visualization` (static plots/maps, animations, interactive HTML).  
- Simulate / Decide / Narrate / Verify → conceptual today; tracked on the roadmap and expressed via configs/orchestrators and external tools until dedicated CLI groups mature.  
- Utilities → `zyra.utils` (credentials, date/time ranges, files/images, JSON/YAML I/O).  

See also: Workflow-Stages.md for an overview and Stage-Examples.md for concise commands.

### Execution Model
- CLI groups mirror stages (`acquire`, `process`, `visualize`, `export`) and accept `-` for stdin/stdout where applicable.  
- Commands are side‑effect free where possible and return non‑zero exit codes on failure.  
- A config‑driven runner can chain stages; external orchestrators (n8n, cron, shell) are supported by design.  

### Data & Formats
- Gridded data: GRIB2 (via cfgrib/pygrib), NetCDF (via netCDF4/xarray), GeoTIFF (via rioxarray/rasterio).  
- Imagery/video: PNG/JPEG/MP4 (via ffmpeg-python).  
- Protocols: HTTP/S, FTP, S3, filesystem; Vimeo for video publishing.  
- CRS/geo: handled by libraries (cartopy, rasterio); follow CF conventions where possible.  

### Configuration & Metadata
- JSON/YAML configs for pipelines and per‑stage arguments.  
- Frames and dataset metadata helpers under `zyra.transform` (e.g., directory scans, enrich/merge).  
- Provenance captured via logs, timestamps, argument echoes, and optional JSON sidecars.  

### Extensibility
- Connectors: add a backend (e.g., new cloud/object store) by implementing list/fetch/upload and registering a subcommand.  
- Processors: add decode/convert/extract operations by exposing CLI wrappers around library calls.  
- Visualizers: add new plot types by adhering to common I/O options (`--input`, `--output`, `--var`, etc.).  

### Security & Compliance
- Credentials are read from environment and standard config locations; do not hard‑code secrets.  
- Optional API service (FastAPI) supports API keys and CORS options (see Zyra-API-Security-Quickstart.md).  
- Artifact handling supports deterministic outputs and optional checksums via verify stage (planned).  

### Performance Considerations
- Stream and chunk large files; avoid load‑all where unnecessary.  
- Prefer xarray/dask patterns where feasible (future work) to enable out‑of‑core transforms.  
- Use format‑appropriate compression (e.g., NetCDF deflate) when exporting.  

### Deployment Modes
- Local CLI via pip extras or poetry.  
- Containerized workloads for reproducible environments (see Zyra-Containers-Overview-and-Usage.md).  
- Optional API service for remote execution and WebSocket streaming; job results persisted with TTL (see Zyra-API-Routers-and-Endpoints.md).  

### Limitations & Roadmap
- Simulate, Decide, Narrate, Verify: conceptual in current releases; tracked in Roadmap-and-Tracking.md.  
- Cartopy tile caching and large model assets may require writable caches and careful environment setup.  
- Parallel/cluster execution is orchestrator‑dependent; native dask integration is planned.  

### References
- Workflow overview: Workflow-Stages.md  
- Examples: Stage-Examples.md  
- API & CLI docs: https://noaa-gsl.github.io/zyra/  
- Security: Zyra-API-Security-Quickstart.md  
