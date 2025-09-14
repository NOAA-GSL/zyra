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
