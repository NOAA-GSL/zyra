This page maps the FastAPI routers to their endpoints, with brief descriptions and auth notes.

## Routers Overview

- `zyra.api.routers.cli`
  - `GET /v1/cli/commands` — Discovery: stages, commands, and argument schemas (with examples)
  - `GET /v1/cli/examples` — Curated example request bodies and pipelines
  - `POST /v1/cli/run` — Execute a CLI command (sync or async)
  - `GET /examples` — Interactive examples page (Upload → Run → Download, WS streaming)
  - Auth: Requires API key header when `ZYRA_API_KEY` is set (except `/docs` and `/redoc`)

- `zyra.api.routers.search`
  - `GET /v1/search` — Perform discovery across sources (local/profile/OGC); JSON output
  - `GET /v1/search/profiles` — List bundled discovery profiles
  - `POST /search` — Discovery with JSON body; set `analyze: true` for LLM-assisted summary and picks
  - Auth: Requires API key header when enabled

- `zyra.api.routers.files`
  - `POST /upload` — Multipart file upload; returns `{file_id, path}`
  - Auth: Requires API key header when enabled
  - Notes: Uploaded files are written under `ZYRA_UPLOAD_DIR` (default `/tmp/zyra_uploads`)

- `zyra.api.routers.jobs`
  - `GET /jobs/{job_id}` — Job status (stdout, stderr, exit_code, output_file, resolved_input_paths)
  - `DELETE /jobs/{job_id}` — Cancel a queued job
  - `GET /jobs/{job_id}/manifest` — JSON list of job artifacts (name, path, size, mtime, media_type)
  - `GET /jobs/{job_id}/download` — Download an artifact; supports `?file=NAME` and `?zip=1`
  - Auth: Requires API key header when enabled
  - Notes: Results under `ZYRA_RESULTS_DIR/{job_id}`; TTL via `ZYRA_RESULTS_TTL_SECONDS`; periodic prune via cleanup loop

- `zyra.api.routers.ws`
  - `WS /ws/jobs/{job_id}` — Live JSON messages for logs/progress/final payload
  - Query params:
    - `api_key` (when `ZYRA_API_KEY` is set) — required
    - `stream=stdout,stderr,progress` — filter which keys to stream
  - Auth: Fail-fast on bad/missing key (closes with code 1008, no data)
  - Modes: Redis pub/sub or in-memory pub/sub parity

- `zyra.api.routers.mcp`
  - `GET /v1/mcp` (and `OPTIONS /v1/mcp`) — MCP discovery payload for MCP clients
  - `POST /v1/mcp` — JSON-RPC 2.0 endpoint with methods:
    - `initialize`, `statusReport` (alias: `status/report`)
    - `tools/list`, `tools/call` (aliases: `listTools`, `callTool`)
  - `GET /v1/mcp/progress/{job_id}` — Server-Sent Events (SSE) stream for async job progress
  - `WS /v1/ws/mcp` — JSON-RPC frames over WebSocket (progress notifications on the same socket)
  - Auth: Header when enabled (HTTP); `?api_key=` query param for WS when enabled
  - Notes: Body size limit via `MCP_MAX_BODY_BYTES` (bytes). See also `/ws/jobs/{job_id}` for job streaming.

- Domain routers (minimal domain APIs mapping to CLI):
  - `zyra.api.routers.domain_process` — `POST /v1/process`
  - `zyra.api.routers.domain_visualize` — `POST /v1/visualize` (alias: `/v1/render`)
  - `zyra.api.routers.domain_assets` — `POST /v1/assets`
  - `zyra.api.routers.domain_disseminate` — `POST /v1/export` (aliases: `/v1/disseminate`, legacy: `/v1/decimate`)
  - `zyra.api.routers.domain_acquire` — `POST /v1/import` (alias: `/v1/acquire`)
  - `zyra.api.routers.domain_decide` — `POST /v1/decide` (alias: `/v1/optimize`)
  - `zyra.api.routers.domain_simulate` — `POST /v1/simulate`
  - `zyra.api.routers.domain_narrate` — `POST /v1/narrate`
  - `zyra.api.routers.domain_verify` — `POST /v1/verify`
  - `zyra.api.routers.domain_transform` — `POST /v1/transform`
  - Behavior: Validates a domain-specific body (discriminator `tool`), normalizes args using CLI schemas, then delegates to `/cli/run` (sync or async). Async returns `{ status: 'accepted', job_id, poll, download, manifest }`. Errors return a standardized `validation_error` or `execution_error` envelope instead of 422.
  - Limits & logging: Optional `DOMAIN_MAX_BODY_BYTES` limit; structured domain call logs are emitted with timings.

## Auth Recap

- HTTP endpoints (CLI, Files, Jobs) require the API key header when configured
- WebSocket requires `?api_key=` in the URL when configured
- `/examples` page can be gated with `ZYRA_REQUIRE_KEY_FOR_EXAMPLES=1`
- OpenAPI docs remain readable without a key

System & LLM
- `GET /v1/health` — service probe
- `GET /v1/ready` — readiness, includes checks (uploads path, disk, queue, binaries, llm)
- `GET /v1/llm/test` — optional LLM connectivity probe (provider/model resolved from env)

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
- `mcp` — MCP JSON-RPC and progress
- Domain tags — `process`, `visualize`, `assets`, `export` (aliases: `disseminate`, legacy: `decimate`), `import` (alias: `acquire`), `decide` (alias: `optimize`), `simulate`, `narrate`, `verify`, `transform`
- `system` — `GET /health`, `GET /ready`

## Environment Variables (selected)

- Auth: `ZYRA_API_KEY`, `ZYRA_API_KEY_HEADER`, `ZYRA_REQUIRE_KEY_FOR_EXAMPLES`
- CORS: `ZYRA_CORS_ALLOW_ALL`, `ZYRA_CORS_ORIGINS`
- Uploads: `ZYRA_UPLOAD_DIR`
- Results: `ZYRA_RESULTS_DIR`, `ZYRA_RESULTS_TTL_SECONDS`, `ZYRA_RESULTS_CLEAN_INTERVAL_SECONDS`
- Streaming: `ZYRA_USE_REDIS`, `ZYRA_REDIS_URL`, `ZYRA_QUEUE`
- MCP: `ENABLE_MCP` (1/0), `MCP_MAX_BODY_BYTES`
- Domain: `DOMAIN_MAX_BODY_BYTES`
- Root/path behind proxies: `API_ROOT_PATH` (e.g., `/zyra`) — sets FastAPI `root_path`; server uses `root_path_in_servers=True` so OpenAPI and links include the prefix when mounted under a reverse proxy.

## Behind a Proxy (tip)

- Set `API_ROOT_PATH` to the mount path (for example, `/zyra`).
- Ensure the proxy forwards standard headers (`Host`, `X-Forwarded-Proto`).

Example (nginx):

```
# .env for Zyra API
API_ROOT_PATH=/zyra

# nginx
location /zyra/ {
  proxy_pass         http://127.0.0.1:8000/;  # note trailing slash
  proxy_set_header   Host $host;
  proxy_set_header   X-Forwarded-Proto $scheme;
  proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
}
```

Notes
- The server renders links and OpenAPI under the configured root path.
- CORS can be enabled via `CORS_ALLOW_ALL=1` or `CORS_ORIGINS`.
