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

S3
- Single object: `zyra acquire s3 --url s3://bucket/key -o out.bin`
- Bucket/key: `zyra acquire s3 --bucket my-bucket --key path/file.bin -o out.bin`
- Unsigned: add `--unsigned` for public buckets

FTP
- Fetch: `zyra acquire ftp ftp://host/path/file.bin -o out.bin`
- List/sync directory: `zyra acquire ftp ftp://host/path/ --list` or `--sync-dir local_dir`

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
- Do not hard-code secrets; pass headers via env, e.g., `--header "X-API-Key: $LIMITLESS_API_KEY"`.
- For large transfers, prefer `--stream` and `--resume`.

Auth helper
- `--auth bearer:$TOKEN` — expands to `Authorization: Bearer <value>` with `$TOKEN` read from the environment.
- `--auth basic:user:pass` — expands to `Authorization: Basic <base64(user:pass)>`. You may also use `basic:$ENV` where `$ENV` contains `user:pass`.
- `--auth header:Name:Value` — injects a custom header when not already present. `Value` may be `$ENV`.
