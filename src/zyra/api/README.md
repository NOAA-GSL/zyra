# API — Generic Endpoints

Endpoints
- POST `/v1/acquire/api`
  - Body mirrors CLI (url, method, headers, params, data, paginate options).
  - Pagination modes: `page`, `cursor`, `link`.
  - NDJSON: set `newline_json=true` to stream `application/x-ndjson`.
  - Streaming: set `stream=true` to stream bytes with upstream Content-Type and optional Content-Disposition.
  - OpenAPI: set `openapi_validate=true` (and optional `openapi_strict`) to validate the request before issuing it.
  - Auth helper: set `auth` to `bearer:<token>` (or `bearer:$ENV`) to inject an `Authorization: Bearer <token>` header when not present.
  - Basic auth: set `auth` to `basic:user:pass` (or `basic:$ENV` with `$ENV`=`user:pass`) to inject a `Basic` Authorization header.
  - Custom header: set `auth` to `header:Name:Value` (or `header:Name:$ENV`) to add a custom header when not present.

- POST `/v1/process/api-json`
  - Accepts file upload or `file_or_url` (path or URL).
  - Options: `records_path`, `fields`, `flatten`, `explode`, `derived`, `format`.
  - Returns CSV (`text/csv`) or JSONL (`application/x-ndjson`).

Presets
- POST `/v1/presets/limitless/audio`
  - Maps `start`/`end` or `since`+`duration` to `startMs`/`endMs` and streams audio (Ogg Opus) with upstream headers.
  - Enforces maximum duration of 2 hours when using `since`+`duration`.

Notes
- Respect environment variables for secrets and configuration (e.g., `LIMITLESS_API_KEY`, `DATA_DIR`).
- For large responses, prefer streaming and consider downstream consumers for NDJSON vs aggregated JSON.

## Examples

Run the API locally
- `poetry run uvicorn zyra.api.server:app --host 127.0.0.1 --port 8000`

Process lifelogs (JSON/NDJSON → CSV)
- Multipart upload with preset + explode array and CSV output:
  - `curl -s -X POST http://127.0.0.1:8000/v1/process/api-json -F file=@lifelogs.jsonl -F preset=limitless-lifelogs -F explode=contents -F format=csv -o lifelogs_contents_rows.csv`

Acquire Limitless audio (direct endpoint)
- Stream Ogg Opus audio for a time range (milliseconds) with `X-API-Key`:
  - `curl -s -X POST http://127.0.0.1:8000/v1/acquire/api \`
    `-H 'Content-Type: application/json' \`
    `-d '{"url":"https://api.limitless.ai/v1/download-audio","method":"GET","accept":"audio/ogg","headers":{"X-API-Key":"'"$LIMITLESS_API_KEY"'"},"params":{"startMs":"1757874805000","endMs":"1757875472000","audioSource":"pendant"},"stream":true}' \`
    `-o out.ogg`

Acquire Limitless audio (preset endpoint)
- Server maps `since` + `duration` (ISO) to milliseconds and streams audio:
  - `curl -s -X POST http://127.0.0.1:8000/v1/presets/limitless/audio -H 'Content-Type: application/json' -d '{"since":"2025-09-14T18:33:25Z","duration":"PT11M","audio_source":"pendant"}' -o out.ogg`

CLI wrapper for /cli/run
- `poetry run python -m zyra.api_cli run --base-url http://127.0.0.1:8000 --stage process --command api-json --mode sync --args '{"file_or_url":"lifelogs.jsonl","preset":"limitless-lifelogs","explode":["contents"],"format":"csv"}' > lifelogs_contents_rows.csv`
