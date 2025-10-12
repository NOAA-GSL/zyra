# MCP Tools

download-audio (profile-driven)
- Arguments:
  - `profile`: provider profile (default `limitless`)
  - `start`, `end`: ISO-8601 datetimes (mutually exclusive with `since`/`duration`)
  - `since`, `duration`: ISO-8601 (e.g., `PT30M`), used together; enforces ≤ 2 hours
  - `audio_source`: `pendant` (default) or `app` (profile-dependent)
  - `output_dir`: relative directory under `DATA_DIR`
  - `credentials` / `credential`: optional credential mapping/list (uses the shared resolver; e.g., `{ "token": "$LIMITLESS_API_KEY" }`)
- Returns: `{ path, content_type, size_bytes }`

Example JSON-RPC
```
{"jsonrpc":"2.0","method":"tools/call","params":{"name":"download-audio","arguments":{"profile":"limitless","since":"2025-01-01T00:00:00Z","duration":"PT30M","audio_source":"pendant"}},"id":1}
```

Notes
- Secrets (e.g., `LIMITLESS_API_KEY`) are read from the environment; not persisted.
- Files are written under `DATA_DIR`.

api-fetch (generic)
- Fetch a REST endpoint and save the response under `DATA_DIR`.
- Args: `url` (required), `method`, `headers` (object), `header` (array of `Name: Value`), `params` (object), `data` (object), `output_dir`, `credentials` / `credential` (same resolver as CLI), `credential_file`, `auth` (e.g., `bearer:$TOKEN`).
- Returns: `{ path, content_type, size_bytes, status_code }`

api-process-json (generic)
- Transform JSON/NDJSON to CSV/JSONL via the CLI path and save under `DATA_DIR`.
- Args: `file_or_url` (required), `records_path`, `fields`, `flatten`, `explode`, `derived`, `format`, `output_dir`, `output_name`.
- Returns: `{ path, size_bytes, format }`
