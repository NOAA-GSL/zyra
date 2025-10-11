# Processing

Commands
- `api-json` — Transform JSON/NDJSON to CSV/JSONL (select/flatten/explode/derive).
- `decode-grib2` — Decode GRIB2 and print metadata (supports cfgrib/pygrib/wgrib2 backends).
- `extract-variable` — Extract a variable from a dataset and write to NetCDF.
- `convert-format` — Convert decoded data to NetCDF/GeoTIFF (when supported).
- `pad-missing` — Generate placeholder frames for missing timestamps using transform metadata.
- `audio-transcode` — Transcode audio (wav/mp3/ogg) via ffmpeg.
- `audio-metadata` — Print audio metadata via ffprobe.
- `video-transcode` — Re-encode videos or JPG stacks via ffmpeg (modern + SOS presets).

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

pad-missing
- Metadata: `--frames-meta frames_meta.json` (from `transform scan-frames`)
- Stdin metadata: `--read-frames-meta-stdin` (pipe JSON from `transform scan-frames`)
- Output: `--output-dir data/padded_frames`
- Modes: `--fill-mode blank|solid|basemap|nearest`
- Basemap/color: `--basemap pkg:zyra.assets/images/earth_vegetation.jpg` or `--basemap "#202020"`
- Indicators: `--indicator watermark:MISSING` or `--indicator badge:pkg:zyra.assets/images/nearest.png`
- Reports: `--json-report _work/images/${DATASET_NAME}/metadata/pad-missing-report.json`

Examples
- Basemap placeholders: `zyra process pad-missing --frames-meta frames_meta.json --fill-mode basemap --basemap pkg:zyra.assets/images/earth_vegetation.jpg --output-dir data/padded`
- Nearest copy with watermark + report: `zyra process pad-missing --frames-meta frames_meta.json --fill-mode nearest --indicator watermark:ESTIMATED --json-report data/padded/pad-missing-report.json --output-dir data/padded`
- Pipeline piping example: `zyra transform scan-frames --frames-dir frames -o - | zyra process pad-missing --read-frames-meta-stdin --output-dir frames_padded`

Audio
- Transcode: `zyra process audio-transcode input.ogg --to wav -o out.wav`
- Metadata: `zyra process audio-metadata input.ogg`

Video
- Modern re-encode: `zyra process video-transcode input.mpg --to mp4 --codec h264 -o out.mp4`
- Batch directory (mirrors structure): `zyra process video-transcode data/raw_videos --output data/modernized --to mp4 --extra-args "-movflags +faststart"`
- Globbed JPG stack → MP4: `zyra process video-transcode "frames/*/*.jpg" --fps 30 --pix-fmt yuv420p --output data/renders`
- SOS preset (JPG stack): `zyra process video-transcode frames/frame%04d.jpg --sos-legacy -o legacy.mp4`
- SOS preset notes: Legacy SOS playlists typically ship `.mp4` files even when encoded with `libxvid`; reach for `--to mpg` only when you knowingly need MPEG-2 playback (the CLI will warn and default to `mpeg2video` to keep the container honest).
- Metadata JSON: `zyra process video-transcode input.mpg --write-metadata --metadata-out meta.json`
