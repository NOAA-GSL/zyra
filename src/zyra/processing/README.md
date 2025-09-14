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

GRIB2
- Decode: `zyra process decode-grib2 input.grib2`
- Backends: `--backend cfgrib|pygrib|wgrib2`
- Convert: `zyra process convert-format input.grib2 netcdf -o out.nc`

Audio
- Transcode: `zyra process audio-transcode input.ogg --to wav -o out.wav`
- Metadata: `zyra process audio-metadata input.ogg`
