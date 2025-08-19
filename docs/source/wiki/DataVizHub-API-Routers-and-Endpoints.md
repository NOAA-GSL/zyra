This page maps the FastAPI routers to their endpoints, with brief descriptions and auth notes.

## Routers Overview

- `datavizhub.api.routers.cli`
  - `GET /cli/commands` — Discovery: stages, commands, and argument schemas (with examples)
  - `GET /cli/examples` — Curated example request bodies and pipelines
  - `POST /cli/run` — Execute a CLI command (sync or async)
  - `GET /examples` — Interactive examples page (Upload → Run → Download, WS streaming)
  - Auth: Requires API key header when `DATAVIZHUB_API_KEY` is set (except `/docs` and `/redoc`)

- `datavizhub.api.routers.files`
  - `POST /upload` — Multipart file upload; returns `{file_id, path}`
  - Auth: Requires API key header when enabled
  - Notes: Uploaded files are written under `DATAVIZHUB_UPLOAD_DIR` (default `/tmp/datavizhub_uploads`)

- `datavizhub.api.routers.jobs`
  - `GET /jobs/{job_id}` — Job status (stdout, stderr, exit_code, output_file, resolved_input_paths)
  - `DELETE /jobs/{job_id}` — Cancel a queued job
  - `GET /jobs/{job_id}/manifest` — JSON list of job artifacts (name, path, size, mtime, media_type)
  - `GET /jobs/{job_id}/download` — Download an artifact; supports `?file=NAME` and `?zip=1`
  - Auth: Requires API key header when enabled
  - Notes: Results under `DATAVIZHUB_RESULTS_DIR/{job_id}`; TTL via `DATAVIZHUB_RESULTS_TTL_SECONDS`; periodic prune via cleanup loop

- `datavizhub.api.routers.ws`
  - `WS /ws/jobs/{job_id}` — Live JSON messages for logs/progress/final payload
  - Query params:
    - `api_key` (when `DATAVIZHUB_API_KEY` is set) — required
    - `stream=stdout,stderr,progress` — filter which keys to stream
  - Auth: Fail-fast on bad/missing key (closes with code 1008, no data)
  - Modes: Redis pub/sub or in-memory pub/sub parity

## Auth Recap

- HTTP endpoints (CLI, Files, Jobs) require the API key header when configured
- WebSocket requires `?api_key=` in the URL when configured
- `/examples` page can be gated with `DATAVIZHUB_REQUIRE_KEY_FOR_EXAMPLES=1`
- OpenAPI docs remain readable without a key

## Common Workflows

- Upload → Run → Download
  1. `POST /upload` (store `file_id`)
  2. `POST /cli/run` (use `file_id:<id>` placeholder in args) — async returns `job_id`
  3. Stream: `ws://.../ws/jobs/{job_id}?api_key=<key>&stream=progress`
  4. `GET /jobs/{job_id}` until `status=succeeded`; `GET /jobs/{job_id}/download` to fetch artifact

- Discovery and Examples
  - `GET /cli/commands` for per-command schemas and examples
  - `GET /cli/examples` for curated examples; try them in `/examples`

## Tags in OpenAPI

- `cli` — CLI discovery and execution
- `files` — Uploads
- `jobs` — Job status/manifest/download
- `ws` — WebSocket streaming
- `system` — `GET /health`, `GET /ready`

## Environment Variables (selected)

- Auth: `DATAVIZHUB_API_KEY`, `DATAVIZHUB_API_KEY_HEADER`, `DATAVIZHUB_REQUIRE_KEY_FOR_EXAMPLES`
- CORS: `DATAVIZHUB_CORS_ALLOW_ALL`, `DATAVIZHUB_CORS_ORIGINS`
- Uploads: `DATAVIZHUB_UPLOAD_DIR`
- Results: `DATAVIZHUB_RESULTS_DIR`, `DATAVIZHUB_RESULTS_TTL_SECONDS`, `DATAVIZHUB_RESULTS_CLEAN_INTERVAL_SECONDS`
- Streaming: `DATAVIZHUB_USE_REDIS`, `DATAVIZHUB_REDIS_URL`, `DATAVIZHUB_QUEUE`

