# Processing

Commands
- `api-json` — Transform JSON/NDJSON to CSV/JSONL (select/flatten/explode/derive).
- `decode-grib2` — Decode GRIB2 and print metadata (supports cfgrib/pygrib/wgrib2 backends).
- `extract-variable` — Extract a variable from a dataset and write to NetCDF.
- `convert-format` — Convert decoded data to NetCDF/GeoTIFF (when supported).
- `audio-transcode` — Transcode audio (wav/mp3/ogg) via ffmpeg.
- `audio-metadata` — Print audio metadata via ffprobe.

api-json
- CLI: `zyra process api-json <file_or_url>`
- Records: `--records-path PATH`
- Fields/flatten: `--fields id,text,user.role`, `--flatten`
- Explode arrays: `--explode tags`
- Derived: `--derived word_count,sentence_count,tool_calls_count`
- Strictness: `--strict` (error on missing fields)
- Output: `--format csv|jsonl`, `--output PATH|-`

### Limitless lifelogs (JSON → CSV)

Import NDJSON (from the ingest examples) and turn each `contents[]` item into a CSV row with selected fields.

Preview and explore keys
- `zyra process api-json lifelogs.jsonl --preset limitless-lifelogs --explode contents --format jsonl --output - | head -n5`
- Tip: add `--flatten` to flatten nested objects when exploring in JSONL output.

Reliable CSV export (explicit fields; no flatten)
- `zyra process api-json lifelogs.jsonl --preset limitless-lifelogs --explode contents --fields id,title,contents.type,contents.content,contents.speakerName,contents.startTime,contents.endTime,contents.startOffsetMs,contents.endOffsetMs,startTime,endTime,updatedAt,isStarred --format csv --output lifelogs_contents_rows.csv`

Notes
- Prefer explicit `--fields` for CSV to avoid sparse headers and empty rows; use dot paths for nested values.
- `--explode PATH` duplicates the parent record for each element of an array at `PATH` (e.g., `contents`).
- `--flatten` is most useful for JSONL inspection or when combined with an explicit field list.
- `--strict` fails fast when a requested field is missing.

Typical keys (after `--preset limitless-lifelogs` and `--explode contents`)
- Top-level record
  - `id`, `title`, `startTime`, `endTime`, `updatedAt`, `isStarred`
  - Optional: `markdown`
- Per `contents[]` item
  - `contents.type` — e.g., `heading1|heading2|blockquote`
  - `contents.content` — text content for the item
  - `contents.speakerName` — when present on spoken segments
  - `contents.startTime`, `contents.endTime` — ISO timestamps (when present)
  - `contents.startOffsetMs`, `contents.endOffsetMs` — offsets within the session (when present)

Example field list for CSV
- `id,title,contents.type,contents.content,contents.speakerName,contents.startTime,contents.endTime,contents.startOffsetMs,contents.endOffsetMs,startTime,endTime,updatedAt,isStarred`

Via Zyra API (server)
- Start the API: `poetry run uvicorn zyra.api.server:app --host 127.0.0.1 --port 8000`
- Multipart upload (NDJSON in, CSV out):
  - `curl -s -X POST http://127.0.0.1:8000/v1/process/api-json -F file=@lifelogs.jsonl -F preset=limitless-lifelogs -F explode=contents -F format=csv -o lifelogs_contents_rows.csv`

GRIB2
- Decode: `zyra process decode-grib2 input.grib2`
- Backends: `--backend cfgrib|pygrib|wgrib2`
- Convert: `zyra process convert-format input.grib2 netcdf -o out.nc`

Audio
- Transcode: `zyra process audio-transcode input.ogg --to wav -o out.wav`
- Metadata: `zyra process audio-metadata input.ogg`
