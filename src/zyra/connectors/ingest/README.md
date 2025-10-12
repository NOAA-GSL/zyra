# Ingest (acquire)

Commands
- `zyra acquire http` — Download via HTTP(S), list/filter directory pages, batch with `--inputs/--manifest`.
- `zyra acquire s3` — Download from S3 by URL (`s3://bucket/key`) or bucket/key.
- `zyra acquire ftp` — Fetch from FTP (single path or list/sync directories).
- `zyra acquire vimeo` — Placeholder for Vimeo fetch by id (not implemented).
- `zyra acquire api` — Generic REST API fetch (headers/params/body, pagination, streaming).

HTTP
- Single file: `zyra acquire http https://host/file.bin -o out.bin`
- Batch: `zyra acquire http --inputs url1 url2 --output-dir downloads/`
- List/filter: `zyra acquire http https://host/dir/ --list --pattern '\\.(grib2|nc)$'`
- Credentials: `--credential token=$EUMETSAT_TOKEN` injects `Authorization: Bearer ...`; combine with `--credential header.X-API-Key=@SERVICE_KEY` or `--auth` helpers as needed.

S3
- Single object: `zyra acquire s3 --url s3://bucket/key -o out.bin`
- Bucket/key: `zyra acquire s3 --bucket my-bucket --key path/file.bin -o out.bin`
- Unsigned: add `--unsigned` for public buckets

FTP
- Fetch: `zyra acquire ftp ftp://host/path/file.bin -o out.bin`
- List/sync directory: `zyra acquire ftp ftp://host/path/ --list` or `--sync-dir local_dir`
- Credentials: `--user demo --credential password=$FTP_PASS` (aliases for `--credential user=...` / `password=...`) apply to fetch, list, and sync operations without embedding secrets in the URL.

Credential helper (all connectors opting in)
- `--credential field=value` (repeatable) resolves secrets via literals, `$ENV`, or `@KEY` (using `CredentialManager` / dotenv). Common slots: `token`, `user`, `password`, and `header.<Name>`.
- `--credential-file path/to/.env` points to a specific dotenv file when using `@KEY` lookups.
- Values are masked in logs; prefer this flow over embedding credentials in URLs or shell history.
- Zyra's API and MCP tooling reuse this helper so REST clients can supply the same credential slots without changing payload schemas.

API (generic REST)
- Common options
  - `--url URL`, `--method`, `--data JSON|@file.json`, `--content-type`, `--header`, `--params`
  - Streaming: `--stream`, `--detect-filename`, `--expect-content-type`, `--resume`, `--head-first`, `--accept`
  - Pagination: `--paginate cursor|page|link` with
    - cursor: `--cursor-param`, `--next-cursor-json-path`
    - page: `--page-param`, `--page-start`, `--page-size-param`, `--page-size`, `--empty-json-path`
    - link: `--link-rel`
  - Output: `--newline-json` (NDJSON) or aggregated JSON array

OpenAPI-aided help and validation
- `--openapi-help` — fetch the service's OpenAPI and print required/optional params and requestBody content-types for the resolved operation.
- `--openapi-validate` — validate provided `--header/--params/--data` against the spec; prints issues.
- `--openapi-strict` — exit non-zero when validation finds issues (use with `--openapi-validate`).

- Examples
  - Single request: `zyra acquire api --url "https://api.example/v1/item" -o item.json`
  - Cursor NDJSON: `zyra acquire api --url "https://api.example/v1/items" --paginate cursor --cursor-param cursor --next-cursor-json-path data.next --newline-json -o items.jsonl`
  - Link NDJSON: `zyra acquire api --url "https://api.example/v1/items" --paginate link --link-rel next --newline-json -o items.jsonl`

Presets (API)
- `--preset limitless-lifelogs` — applies cursor defaults (e.g., `cursor`, `meta.lifelogs.nextCursor`)
- `--preset limitless-audio` — maps `start/end` or `since+duration` to `startMs/endMs`, sets `Accept: audio/ogg`, prefers `--stream`

Notes
- Do not hard-code secrets; pass headers via env/credential helper, e.g., `--credential token=$LIMITLESS_API_KEY`.
- For large transfers, prefer `--stream` and `--resume`.

Auth helper
- `--auth bearer:$TOKEN` — expands to `Authorization: Bearer <value>` with `$TOKEN` read from the environment.
- `--auth basic:user:pass` — expands to `Authorization: Basic <base64(user:pass)>`. You may also use `basic:$ENV` where `$ENV` contains `user:pass`.
- `--auth header:Name:Value` — injects a custom header when not already present. `Value` may be `$ENV`.

## Limitless API examples

Auth
- Use `--header "X-API-Key: $LIMITLESS_API_KEY"` (verify with `echo ${LIMITLESS_API_KEY:0:6}`).

OpenAPI assist
- Show required/optional fields using the published spec:
  - `zyra acquire api --url "https://api.limitless.ai/v1/download-audio" --openapi-url https://www.limitless.ai/openapi.yml --openapi-help`

Download audio (preset)
- Pendant/app audio with automatic ms conversion and streaming to file:
  - `zyra acquire api --preset limitless-audio --since 2025-09-14T18:33:25Z --duration PT11M --audio-source pendant --header "X-API-Key: $LIMITLESS_API_KEY" --stream --output out.ogg`

Download audio (explicit URL/params)
- Compute epoch ms and pass required params (`startMs`, `endMs`), plus optional `audioSource`:
  - `start="2025-09-14T18:33:25Z"; end="2025-09-14T18:44:32Z"`
  - `startMs=$(date -u -d "$start" +%s)000; endMs=$(date -u -d "$end" +%s)000`
  - `zyra acquire api --url "https://api.limitless.ai/v1/download-audio" --header "X-API-Key: $LIMITLESS_API_KEY" --accept audio/ogg --params "startMs=$startMs&endMs=$endMs&audioSource=pendant" --stream --output out.ogg`

Troubleshooting
- 401: check that the API key is present; prefer `X-API-Key` for this endpoint.
- 400: validate window (`startMs < endMs`, ≤ 2h) and try switching/removing `audioSource`.
- To inspect server JSON, temporarily disable the content-type guard and allow non-2xx:
  - `... --allow-non-2xx --expect-content-type "" --stream --output - | head -c 1200`

### Import transcripts (JSON/NDJSON)

Fetch lifelog transcript pages as NDJSON using the preset (cursor pagination):
- `zyra acquire api --preset limitless-lifelogs --url "https://api.limitless.ai/v1/lifelogs" --header "X-API-Key: $LIMITLESS_API_KEY" --since 2025-09-01T00:00:00Z --newline-json --output lifelogs.jsonl`

Notes
- The preset sets `--paginate cursor`, `--cursor-param cursor`, and `--next-cursor-json-path meta.lifelogs.nextCursor`.
- Use `--since` to seed the range (maps to the provider’s `start` query parameter).

### Using the Zyra API instead of CLI

- Start the API: `poetry run uvicorn zyra.api.server:app --host 127.0.0.1 --port 8000`
- Stream audio via API (explicit params):
  - `curl -s -X POST http://127.0.0.1:8000/v1/acquire/api \`
    `-H 'Content-Type: application/json' \`
    `-d '{"url":"https://api.limitless.ai/v1/download-audio","method":"GET","accept":"audio/ogg","headers":{"X-API-Key":"'"$LIMITLESS_API_KEY"'"},"params":{"startMs":"1757874805000","endMs":"1757875472000","audioSource":"pendant"},"stream":true}' \`
    `-o out.ogg`
- Or use the preset endpoint (server maps ISO to ms):
  - `curl -s -X POST http://127.0.0.1:8000/v1/presets/limitless/audio -H 'Content-Type: application/json' -d '{"since":"2025-09-14T18:33:25Z","duration":"PT11M","audio_source":"pendant"}' -o out.ogg`
