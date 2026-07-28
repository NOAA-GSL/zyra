Decode, subset, convert, reproject, or enrich data and metadata.

Aliases accepted for `stage:` — `processing`, `transform`.

Generated from Zyra **0.1.54**. See [Pipeline Schema](Pipeline-Schema) for how `args` keys become CLI flags.

**Commands:** [`api-json`](#process-api-json) · [`audio-metadata`](#process-audio-metadata) · [`audio-transcode`](#process-audio-transcode) · [`convert-format`](#process-convert-format) · [`decode-grib2`](#process-decode-grib2) · [`enrich-datasets`](#process-enrich-datasets) · [`enrich-metadata`](#process-enrich-metadata) · [`extract-variable`](#process-extract-variable) · [`metadata`](#process-metadata) · [`pad-missing`](#process-pad-missing) · [`reproject`](#process-reproject) · [`scan-frames`](#process-scan-frames) · [`update-dataset-json`](#process-update-dataset-json) · [`video-transcode`](#process-video-transcode)

---
### `process api-json`

Read a JSON or NDJSON file/stream, select fields via dot paths, optionally flatten nested objects, explode arrays into multiple rows, and write CSV or JSONL.

**Positionals**

| Arg key | Required | Type | Usable in a pipeline stage? |
| --- | --- | --- | --- |
| `file_or_url` | yes | str | **no — see note** |

> **Not pipeline-addressable.** The runner has no positional mapping for this command, so `file_or_url` would be emitted as a `--flag` and rejected by argparse. Use this command from the CLI, or open an issue to add the mapping.

**Options**

| Arg key | CLI flag | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `records_path` | `--records-path` | str |  | Dot path to array of records (e.g., data.lifelogs or data.chat.messages) |
| `preset` | `--preset` | str |  | Apply provider-specific defaults (e.g., Limitless lifelogs records path) Choices: `limitless-lifelogs` |
| `fields` | `--fields` | str |  | Comma-separated field list (dot paths). If omitted, use first row keys |
| `flatten` | `--flatten` | bool | `False` | Flatten nested objects |
| `explode` | `--explode` | str |  | Repeatable: dot path to array to explode into multiple rows |
| `derived` | `--derived` | str |  | Comma-separated derived columns: word_count,sentence_count,tool_calls_count |
| `format` | `--format` | str | `csv` | Output format Choices: `csv`, `jsonl` |
| `strict` | `--strict` | bool | `False` | Error on missing fields instead of emitting empty strings |
| `output` | `--output` | path | `-` | Output file path or '-' for stdout |

**Chaining:** reads stdin via `file_or_url: "-"`.

### `process audio-metadata`

Run ffprobe to extract duration, bitrate, channels, sample rate, codec, and size; writes JSON.

**Positionals**

| Arg key | Required | Type | Usable in a pipeline stage? |
| --- | --- | --- | --- |
| `input` | yes | str | **no — see note** |

> **Not pipeline-addressable.** The runner has no positional mapping for this command, so `input` would be emitted as a `--flag` and rejected by argparse. Use this command from the CLI, or open an issue to add the mapping.

**Options**

| Arg key | CLI flag | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `output` | `--output` | path | `-` | Output path or '-' for stdout |
| `verbose` | `--verbose` | bool | `False` |  |
| `quiet` | `--quiet` | bool | `False` |  |
| `trace` | `--trace` | bool | `False` |  |

### `process audio-transcode`

Transcode input audio to a target format using ffmpeg. Requires FFmpeg runtime.

**Positionals**

| Arg key | Required | Type | Usable in a pipeline stage? |
| --- | --- | --- | --- |
| `input` | yes | str | **no — see note** |

> **Not pipeline-addressable.** The runner has no positional mapping for this command, so `input` would be emitted as a `--flag` and rejected by argparse. Use this command from the CLI, or open an issue to add the mapping.

**Options**

| Arg key | CLI flag | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `output` | `--output` | path |  | Output file path |
| `to` | `--to` | str | `wav` | Choices: `wav`, `mp3`, `ogg` |
| `sample_rate` | `--sample-rate` | int | `16000` |  |
| `mono` | `--mono` | bool | `True` | Force mono output |
| `stereo` | `--stereo` | bool | `False` | Force stereo output (overrides --mono) |
| `verbose` | `--verbose` | bool | `False` |  |
| `quiet` | `--quiet` | bool | `False` |  |
| `trace` | `--trace` | bool | `False` |  |

**Chaining:** writes via `--output`.

### `process convert-format`

Convert decoded GRIB2 data to NetCDF or GeoTIFF. Supports single input or batch via --inputs.

**Positionals**

| Arg key | Required | Type | Usable in a pipeline stage? |
| --- | --- | --- | --- |
| `file_or_url` | no | str | yes |
| `format` | yes | str (`netcdf`, `geotiff`) | yes |

**Options**

| Arg key | CLI flag | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `output` | `--output` | path |  |  |
| `stdout` | `--stdout` | bool | `False` | Write binary output to stdout instead of a file |
| `inputs` | `--inputs` | path |  | Multiple input paths or URLs |
| `output_dir` | `--output-dir` | path |  | Directory to write outputs for --inputs |
| `output_names` | `--output-names` | path |  | Destination filenames for --inputs, one per input, in order (default: the source stem). Use to name frames by valid time instead of inheriting the source's cycle-relative name. |
| `backend` | `--backend` | str | `cfgrib` | Choices: `cfgrib`, `pygrib`, `wgrib2` |
| `var` | `--var` | str |  | Variable name or regex for multi-var datasets |
| `pattern` | `--pattern` | str |  | Regex for .idx-based subsetting when using HTTP/S3 |
| `unsigned` | `--unsigned` | bool | `False` | Use unsigned S3 access for public buckets |
| `verbose` | `--verbose` | bool | `False` | Verbose logging for this command |
| `quiet` | `--quiet` | bool | `False` | Quiet logging for this command |
| `trace` | `--trace` | bool | `False` | Shell-style trace of key steps and external commands |

**Chaining:** reads stdin via `file_or_url: "-"`; writes via `--output`.

**Example stage**

```yaml
- stage: process
  command: convert-format
  args:
    file_or_url: "samples/demo.grib2"
    format: "netcdf"
    stdout: true
```

### `process decode-grib2`

Decode a GRIB2 file or URL using cfgrib/pygrib/wgrib2 and log basic metadata. Optionally emit raw bytes (with optional .idx subset) to stdout.

**Positionals**

| Arg key | Required | Type | Usable in a pipeline stage? |
| --- | --- | --- | --- |
| `file_or_url` | yes | str | yes |

**Options**

| Arg key | CLI flag | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `backend` | `--backend` | str | `cfgrib` | Choices: `cfgrib`, `pygrib`, `wgrib2` |
| `pattern` | `--pattern` | str |  | Regex for .idx-based subsetting when using HTTP/S3 |
| `unsigned` | `--unsigned` | bool | `False` | Use unsigned S3 access for public buckets |
| `raw` | `--raw` | bool | `False` | Emit raw (optionally .idx-subset) GRIB2 bytes to stdout |
| `verbose` | `--verbose` | bool | `False` | Verbose logging for this command |
| `quiet` | `--quiet` | bool | `False` | Quiet logging for this command |
| `trace` | `--trace` | bool | `False` | Shell-style trace of key steps and external commands |

**Chaining:** reads stdin via `file_or_url: "-"`.

### `process enrich-datasets`

zyra process enrich-datasets

**Options**

| Arg key | CLI flag | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `items_file` | `--items-file` | str |  | Path to items JSON |
| `profile` | `--profile` | str |  | Bundled profile name under zyra.assets.profiles |
| `profile_file` | `--profile-file` | str |  | External profile JSON path |
| `enrich` | `--enrich` | str |  | Enrichment level Choices: `shallow`, `capabilities`, `probe` |
| `enrich_timeout` | `--enrich-timeout` | float | `3.0` | Per-item timeout (s) |
| `enrich_workers` | `--enrich-workers` | int | `4` | Concurrency (workers) |
| `cache_ttl` | `--cache-ttl` | int | `86400` | Cache TTL seconds |
| `offline` | `--offline` | bool | `False` | Disable network during enrichment |
| `https_only` | `--https-only` | bool | `False` | Require HTTPS for remote probing |
| `allow_host` | `--allow-host` | str |  | Allow host suffix (repeatable) |
| `deny_host` | `--deny-host` | str |  | Deny host suffix (repeatable) |
| `max_probe_bytes` | `--max-probe-bytes` | int |  | Skip probing when larger than this size |
| `output` | `--output` | path | `-` | Output path or '-' for stdout |
| `verbose` | `--verbose` | bool | `False` | Verbose logging for this command |
| `quiet` | `--quiet` | bool | `False` | Quiet logging for this command |
| `trace` | `--trace` | bool | `False` | Shell-style trace of key steps and external commands |

### `process enrich-metadata`

Enrich a frames metadata JSON with dataset_id, Vimeo URI, and updated_at; read from file or stdin.

**Options**

| Arg key | CLI flag | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `frames_meta` | `--frames-meta` | path |  | Path to frames metadata JSON |
| `read_frames_meta_stdin` | `--read-frames-meta-stdin` | bool | `False` | Read frames metadata JSON from stdin |
| `dataset_id` | `--dataset-id` | str |  | Dataset identifier to embed |
| `vimeo_uri` | `--vimeo-uri` | str |  | Vimeo video URI to embed in metadata |
| `read_vimeo_uri` | `--read-vimeo-uri` | bool | `False` | Read Vimeo URI from stdin (first line) |
| `output` | `--output` | path | `-` | Output path or '-' for stdout |
| `verbose` | `--verbose` | bool | `False` | Verbose logging for this command |
| `quiet` | `--quiet` | bool | `False` | Quiet logging for this command |
| `trace` | `--trace` | bool | `False` | Shell-style trace of key steps and external commands |

### `process extract-variable`

Extract a variable from GRIB2 by regex pattern. Output selected variable as NetCDF/GRIB2 to stdout when requested, or log the matched variable name.

**Positionals**

| Arg key | Required | Type | Usable in a pipeline stage? |
| --- | --- | --- | --- |
| `file_or_url` | yes | str | yes |
| `pattern` | yes | str | yes |

**Options**

| Arg key | CLI flag | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `backend` | `--backend` | str | `cfgrib` | Choices: `cfgrib`, `pygrib`, `wgrib2` |
| `unsigned` | `--unsigned` | bool | `False` | Use unsigned S3 access for public buckets |
| `stdout` | `--stdout` | bool | `False` | Write selected variable as bytes to stdout |
| `format` | `--format` | str | `netcdf` | Output format for --stdout Choices: `netcdf`, `grib2` |
| `verbose` | `--verbose` | bool | `False` | Verbose logging for this command |
| `quiet` | `--quiet` | bool | `False` | Quiet logging for this command |
| `trace` | `--trace` | bool | `False` | Shell-style trace of key steps and external commands |

**Chaining:** reads stdin via `file_or_url: "-"`.

### `process metadata`

Scan a frames directory to compute start/end timestamps, counts, and missing frames on a cadence.

**Options**

| Arg key | CLI flag | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `frames_dir` | `--frames-dir` | path |  | Directory containing frames |
| `pattern` | `--pattern` | str |  | Regex filter for frame filenames |
| `datetime_format` | `--datetime-format` | str |  | Datetime format used in filenames (e.g., %Y%m%d%H%M%S) |
| `period_seconds` | `--period-seconds` | int |  | Expected cadence to compute missing frames |
| `output` | `--output` | path | `-` | Output path or '-' for stdout |
| `verbose` | `--verbose` | bool | `False` | Verbose logging for this command |
| `quiet` | `--quiet` | bool | `False` | Quiet logging for this command |
| `trace` | `--trace` | bool | `False` | Shell-style trace of key steps and external commands |

### `process pad-missing`

Read frames metadata JSON from 'transform metadata/scan-frames' and generate placeholder images for each missing timestamp using blank, solid color, basemap, or nearest-frame strategies.

**Options**

| Arg key | CLI flag | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `frames_meta` | `--frames-meta` | path |  | Path to frames metadata JSON (from transform metadata/scan-frames) |
| `read_frames_meta_stdin` | `--read-frames-meta-stdin` | bool | `False` | Read frames metadata JSON from stdin |
| `output_dir` | `--output-dir` | path |  | Directory where placeholder frames will be written |
| `fill_mode` | `--fill-mode` | str | `blank` | Strategy for filling gaps (default: blank) Choices: `blank`, `solid`, `basemap`, `nearest` |
| `basemap` | `--basemap` | str |  | Basemap image, package reference, or color (solid/basemap modes) |
| `indicator` | `--indicator` | str |  | Optional overlay indicator, e.g., watermark:MISSING or badge:pkg:... |
| `overwrite` | `--overwrite` | bool | `False` | Replace existing files when output paths already exist |
| `dry_run` | `--dry-run` | bool | `False` | Report planned outputs without writing files |
| `json_report` | `--json-report` | str |  | Optional path to write a JSON summary report |
| `verbose` | `--verbose` | bool | `False` | Verbose logging for this command |
| `quiet` | `--quiet` | bool | `False` | Quiet logging for this command |
| `trace` | `--trace` | bool | `False` | Shell-style trace of key steps and external commands |

### `process reproject`

Warp an already-rendered raster (PNG/JPG/GeoTIFF) from its source projection to a target CRS grid — by default full-globe equirectangular EPSG:4326 at 4096x2048. For native scientific data (GRIB2/NetCDF), use the existing decode/extract/convert path instead; this command is for imagery that was rendered in another projection. Requires the optional rasterio dependency (zyra[processing]).

**Options**

| Arg key | CLI flag | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `input` | `--input` | path |  | Source raster path |
| `output` | `--output` | path |  | Output raster path |
| `inputs` | `--inputs` | path |  | Multiple source rasters for batch reprojection (with --output-dir) |
| `output_dir` | `--output-dir` | path |  | Directory to write outputs for --inputs (each keeps its source filename) |
| `output_names` | `--output-names` | path |  | Destination filenames for --inputs, one per input, in order (default: the source filename) |
| `s_srs` | `--s-srs` | str |  | Source CRS (e.g., EPSG:3413). Overrides any embedded CRS; required for plain images without georeferencing (with --bounds) |
| `t_srs` | `--t-srs` | str | `EPSG:4326` | Target CRS (default: EPSG:4326) |
| `bounds` | `--bounds` | float |  | Source extent in source-CRS units, for rasters without a geotransform |
| `dst_bounds` | `--dst-bounds` | str |  | Target extent in target-CRS units, or 'auto' to derive it from the source's own footprint so regional imagery crops itself (default: full globe for EPSG:4326) |
| `width` | `--width` | int | `4096` | Output width in pixels (default: 4096) |
| `height` | `--height` | int |  | Output height in pixels (default: derived from --width and the target extent's aspect ratio; 2048 for the full globe) |
| `resampling` | `--resampling` | str | `bilinear` | Resampling kernel: bilinear for continuous imagery, nearest for categorical (default: bilinear) Choices: `bilinear`, `nearest` |
| `dst_nodata` | `--dst-nodata` | float |  | Value for pixels outside the source footprint (accepts 'nan' for float sources); default: the source's nodata when present, else 0. Tagged in GeoTIFF output |
| `verbose` | `--verbose` | bool | `False` | Verbose logging for this command |
| `quiet` | `--quiet` | bool | `False` | Quiet logging for this command |
| `trace` | `--trace` | bool | `False` | Shell-style trace of key steps and external commands |

### `process scan-frames`

Alias of 'metadata'. Scan a frames directory and report timestamps, counts, and missing frames.

**Options**

| Arg key | CLI flag | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `frames_dir` | `--frames-dir` | path |  | Directory containing frames |
| `pattern` | `--pattern` | str |  | Regex filter for frame filenames |
| `datetime_format` | `--datetime-format` | str |  | Datetime format used in filenames (e.g., %Y%m%d%H%M%S) |
| `period_seconds` | `--period-seconds` | int |  | Expected cadence to compute missing frames |
| `output` | `--output` | path | `-` | Output path or '-' for stdout |
| `verbose` | `--verbose` | bool | `False` | Verbose logging for this command |
| `quiet` | `--quiet` | bool | `False` | Quiet logging for this command |
| `trace` | `--trace` | bool | `False` | Shell-style trace of key steps and external commands |

### `process update-dataset-json`

Update a dataset.json entry by id using metadata (start/end and Vimeo URI) from a file, stdin, or args.

**Options**

| Arg key | CLI flag | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `input_url` | `--input-url` | path |  | HTTP(S) or s3:// URL of dataset.json |
| `input_file` | `--input-file` | path |  | Local dataset.json path |
| `dataset_id` | `--dataset-id` | str |  | Dataset id to update |
| `meta` | `--meta` | str |  | Path to metadata JSON containing start_datetime/end_datetime/vimeo_uri |
| `read_meta_stdin` | `--read-meta-stdin` | bool | `False` | Read metadata JSON from stdin |
| `start` | `--start` | str |  | Explicit startTime override (ISO) |
| `end` | `--end` | str |  | Explicit endTime override (ISO) |
| `vimeo_uri` | `--vimeo-uri` | str |  | Explicit Vimeo URI (e.g., /videos/12345) |
| `no_set_data_link` | `--no-set-data-link` | bool | `True` | Do not update dataLink from Vimeo URI |
| `output` | `--output` | path | `-` | Output path or '-' for stdout |
| `verbose` | `--verbose` | bool | `False` | Verbose logging for this command |
| `quiet` | `--quiet` | bool | `False` | Quiet logging for this command |
| `trace` | `--trace` | bool | `False` | Shell-style trace of key steps and external commands |

### `process video-transcode`

Transcode videos or JPG image stacks into modern or legacy formats using FFmpeg. Supports SOS presets, metadata capture, and batch processing.

**Positionals**

| Arg key | Required | Type | Usable in a pipeline stage? |
| --- | --- | --- | --- |
| `input` | yes | str | **no — see note** |

> **Not pipeline-addressable.** The runner has no positional mapping for this command, so `input` would be emitted as a `--flag` and rejected by argparse. Use this command from the CLI, or open an issue to add the mapping.

**Options**

| Arg key | CLI flag | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `output` | `--output` | path |  | Output file path (single input) or directory when batching |
| `to` | `--to` | str | `mp4` | Target container format Choices: `mp4`, `webm`, `mov`, `mpg` |
| `codec` | `--codec` | str |  | Video codec to use (sensible default chosen per container) Choices: `h264`, `hevc`, `vp9`, `av1`, `libxvid`, `mpeg2video` |
| `audio_codec` | `--audio-codec` | str |  | Audio codec to use (defaults based on container) |
| `audio_bitrate` | `--audio-bitrate` | str |  | Optional audio bitrate, e.g. 192k |
| `scale` | `--scale` | str |  | Optional scale filter, e.g. 1920x1080 or 1080 |
| `fps` | `--fps` | float |  | Output frames per second (also used as input framerate for sequences) |
| `framerate` | `--framerate` | float |  | Alias for --fps, kept for FFmpeg parity |
| `bitrate` | `--bitrate` | str |  | Target video bitrate (e.g. 8M, 2500k). Defaults to 8M or SOS preset |
| `pix_fmt` | `--pix-fmt` | str |  | Pixel format to emit (default yuv420p for compatibility) |
| `preset` | `--preset` | str |  | FFmpeg encoder preset when supported |
| `crf` | `--crf` | int |  | Constant Rate Factor value for quality-based encoders |
| `gop` | `--gop` | int |  | Group-of-pictures interval (keyframe spacing) |
| `extra_args` | `--extra-args` | str |  | Additional raw FFmpeg arguments (repeatable) |
| `metadata_out` | `--metadata-out` | str |  | Path to write ffprobe metadata JSON |
| `write_metadata` | `--write-metadata` | bool | `False` | Emit ffprobe metadata JSON after transcoding |
| `sos_legacy` | `--sos-legacy` | bool | `False` | Apply SOS defaults: -framerate 30 -b:v 25M -c:v libxvid -pix_fmt yuv420p |
| `no_overwrite` | `--no-overwrite` | bool | `False` | Do not overwrite existing outputs (passes -n to FFmpeg) |
| `verbose` | `--verbose` | bool | `False` |  |
| `quiet` | `--quiet` | bool | `False` |  |
| `trace` | `--trace` | bool | `False` |  |

**Chaining:** writes via `--output`.
