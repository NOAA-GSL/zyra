**Purpose:** Reusable, working examples of the four‑stage pipeline and how to 
chain stages via stdin/stdout.

**Stages:** `[ Acquisition (Ingest) ] → [ Processing ] → [ Visualization ] → [
 Decimation (Egress) ]`

**CLI Groups:** `acquire`, `process`, `visualize`, `decimate`

**Runner:** `zyra run pipeline.yaml` executes the stages in order, strea
ming bytes between them.

**Overview**

- **Chaining:** Use `-` to read from stdin or write to stdout so stages can be c
hained without temp files.
- **Self‑Registration:** Each stage registers its own CLI; the runner resolves s
tage aliases:
  - acquisition/ingest → `acquire`
  - processing → `process`
  - visualization → `visualize`
  - decimation/egress → `decimate`
- **Location:** Sample YAMLs live under `samples/pipelines/` in the repo.

**Sample Pipelines**

- **nc_passthrough.yaml:** Reads NetCDF from stdin, writes NetCDF to stdout.
  - Command: `cat tests/testdata/demo.nc | zyra run samples/pipelines/nc_p
assthrough.yaml > out.nc`
  - Stages: `process convert-format - netcdf --stdout`

- **nc_to_file.yaml:** Reads NetCDF from stdin, writes a local file.
  - Command: `cat tests/testdata/demo.nc | zyra run samples/pipelines/nc_t
o_file.yaml`
  - Stages: `process convert-format - netcdf --stdout → decimate local - out.nc`

- **extract_variable_to_file.yaml:** Extracts a variable (e.g., TMP), converts t
o NetCDF, saves locally.
  - Command: `cat tests/testdata/demo.nc | zyra run samples/pipelines/extr
act_variable_to_file.yaml`
  - Stages: `process extract-variable - "TMP" → process convert-format - netcdf 
--stdout → decimate local - temperature.nc`

- **compose_video_to_local.yaml:** Composes frames to MP4 and writes the result 
locally.
  - Command: `zyra run samples/pipelines/compose_video_to_local.yaml`
  - Note: Needs a `frames/` directory containing `frame_*.png`. FFmpeg should be
 installed or the compose step gracefully skips.

- **ftp_to_s3.yaml (template):** FTP → compose video → upload to S3.
  - Command: Not CI‑safe; requires network access and credentials (edit placehol
ders first).
  - Stages: `acquire ftp → visualize compose-video → decimate s3`

**Overrides**

- **Global:** Apply when the key exists in a stage’s `args`.
  - Example: `--set var=TMP`
- **Per‑stage (1‑based index):** Targets a single stage by index.
  - Example: `--set 2.var=TMP` (sets `var=TMP` on stage 2 only)
- **Stage‑name:** Robust to reordering; uses aliases listed in Overview.
  - Examples:
    - `--set processing.var=TMP`
    - `--set decimation.backend=local`
- **Combining:** Index‑ and name‑based overrides can be used together; name‑base
d is preferred for maintainability.

**Dry Run & Debugging**

- **Preview execution (text):** `zyra run pipeline.yaml --dry-run`
- **Structured argv (JSON):** `zyra run pipeline.yaml --dry-run --print-ar
gv-format=json`
  - Output structure:
    - [
      {"stage": 1, "name": "acquire", "argv": ["zyra", "acquire", "http", 
"https://..."]},
      {"stage": 2, "name": "process", "argv": ["zyra", "process", "convert
-format", "-", "netcdf"]}
    ]
- **Continue on error:** `--continue-on-error` runs remaining stages even if one
 fails (returns the first non‑zero code at end).

**Best Practices**

- **Small fixtures:** Use tiny test assets (`tests/testdata/demo.nc`) or stdin t
o keep pipelines fast and CI‑friendly.
- **Explicit streams:** Use `"-"` in configs to chain stages via stdin/stdout ra
ther than intermediate files.
- **Backends:** Favor `--output -`/`--input -` for connectors; for S3/FTP, prefe
r using full URLs when possible (e.g., `s3://bucket/key`).
- **Optional deps:** Heavy visualization (Cartopy/tiles) may require opt‑in and 
a writable cache (e.g., Natural Earth data). Guard such pipelines in CI.
- **Credentials:** Never hard‑code secrets; rely on env/role‑based credentials f
or S3/FTP/Vimeo.

**Quick Reference**

- **Run pipelines:** `zyra run pipeline.yaml`
- **Override examples:**
  - Global: `--set var=TMP`
  - Stage name: `--set processing.var=TMP`
- **Debugging:**
  - Dry run (text): `--dry-run`
  - Dry run (JSON): `--dry-run --print-argv-format=json`
  - Continue on error: `--continue-on-error`