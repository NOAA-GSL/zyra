This page describes how to enable and use API key authentication, how WebSocket authentication works, and how to configure CORS for browser clients.

## API Key Authentication

- Enable with an environment variable:
  - `ZYRA_API_KEY`: the required API key value
- `ZYRA_API_KEY_HEADER` (optional): header name (default: `X-API-Key` via `API_KEY_HEADER`)
- Legacy envs are recognized: `DATAVIZHUB_API_KEY`, `DATAVIZHUB_API_KEY_HEADER`
- Effect:
  - All HTTP routes in the CLI, Files, and Jobs routers require the API key header
  - OpenAPI docs (`/docs`, `/redoc`) remain readable without a key
  - WebSockets accept the API key as a query string: `?api_key=<key>`

### Examples

- HTTP request with header (default header name):

```bash
curl -H 'X-API-Key: $ZYRA_API_KEY' \
  http://localhost:8000/v1/cli/commands
```

- WebSocket connection (e.g., websocat/wscat) with key and filters:

```bash
npx wscat -c "ws://localhost:8000/ws/jobs/<job_id>?api_key=$ZYRA_API_KEY&stream=progress"
```

- TestClient (Python):

```python
from fastapi.testclient import TestClient
from zyra.api.server import app

client = TestClient(app)
r = client.get('/v1/cli/commands', headers={'X-API-Key': 'your-key'})
assert r.status_code == 200
```

## Gating `/examples` in Production

- To block the interactive examples page in production, set:
  - `ZYRA_REQUIRE_KEY_FOR_EXAMPLES=1`
  - `ZYRA_API_KEY=<your-key>`
- `/examples` then returns 401 unless a valid key is provided via header or `?api_key=` query parameter.
- The examples UI includes an API key field; when present it sends the key in HTTP request headers and as a WS query param.

## WebSocket Authentication Behavior

- If `ZYRA_API_KEY` is defined and the `api_key` query parameter is missing or incorrect:
  - The server closes the connection immediately with code 1008 (policy violation) and does not send any payload.
- When the key is valid, messages stream as JSON; you can filter by keys with `?stream=stdout,stderr,progress`.

## CORS Configuration

CORS is restrictive by default. Enable explicitly via environment variables:

- Allow all (dev only): `ZYRA_CORS_ALLOW_ALL=1`
- Specific origins (recommended for prod):
  - `ZYRA_CORS_ORIGINS="https://app.example.com,https://tools.example.org"`

The server then enables:
- `allow_credentials=True`
- `allow_methods=*`
- `allow_headers=*`

## Reverse Proxy and TLS (Overview)

- Run the API behind Nginx/Caddy for HTTPS termination and WS upgrade support
- Ensure the proxy preserves `Host`, supports WebSocket upgrade headers, and forwards custom headers (e.g., `X-API-Key`)
- When mounting under a subpath, set `API_ROOT_PATH` (e.g., `/zyra`) so links and OpenAPI include the prefix.

## MCP and WebSocket Auth

- MCP HTTP (`POST /v1/mcp`): same header as other HTTP routes (default `X-API-Key`).
- MCP WebSocket (`/v1/ws/mcp`): use `?api_key=<key>` when enabled.
- Jobs WebSocket (`/ws/jobs/{job_id}`): also uses `?api_key=<key>` when enabled; server closes with code 1008 when missing/invalid.

## Throttling Failed Auth Attempts

Tune small in-memory delays and throttling for repeated failures via:

- `ZYRA_AUTH_FAILS_PER_WINDOW` (default 10)
- `ZYRA_AUTH_WINDOW_SECONDS` (default 60)
- `ZYRA_AUTH_FAIL_DELAY_MS` (default 100)

## Future: Rate Limiting and Observability

- Rate limiting (e.g., SlowAPI) can be added later for abuse control
- Structured logs + error reporting (e.g., Sentry) can be enabled with environment-based opt-in
