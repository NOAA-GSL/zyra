This page captures the unified credential workflow. It summarizes how CLI, API, and MCP surfaces resolve secrets, the aliasing rules that keep behavior consistent, and concrete examples you can copy into your own smoke tests.

## Key Concepts

- **Single entry point** – Every surface funnels through `zyra.connectors.credentials.resolve_credentials`, so literals, environment variables, and manager lookups all behave the same way.
- **Safe logging** – `ResolvedCredentials.masked` keeps audit trails redacted, while `apply_http_credentials` and related helpers never emit plaintext in validation traces.
- **Alias aware** – Username/password slots honor `user`, `username`, `basic_user` (and `password`/`basic_password`) through `resolve_basic_auth_credentials`, so older flags like `--user` continue to work.
- **Header injection** – Any credential key prefixed with `header.`, `header:` or `header_` is converted into an HTTP header. Keys with neither prefix remain structured data for downstream tools.

## Resolution Flow

1. **Literal values** – `--credential api_key=abc123` uses the value as-is.
2. **Environment variables** – Prefix with `$`: `--credential token=$API_TOKEN`.
3. **Credential manager entries** – Prefix with `@`: `--credential password=@FTP_PASSWORD`. When the manager is not preloaded, pass `--credential-file secrets.env` or configure the default manager namespace.
4. **Validation** – Missing or empty secrets raise `CredentialResolutionError` before any network calls run.

## CLI Usage Patterns

### Acquire over HTTP(S)

```bash
# Bearer token supplied via environment variable and expanded into headers
export API_TOKEN="abc123"
zyra acquire http https://httpbin.org/headers \
  --credential token=$API_TOKEN \
  --credential header.Authorization="Bearer $API_TOKEN" \
  --output headers.json
```

### Acquire over FTP

```bash
# Credentials can come from a dotenv file for repeatable jobs
zyra acquire ftp ftp://dataserver.example.com/public/report.txt \
  --credential-file secrets.env \
  --credential user=@FTP_USER \
  --credential password=@FTP_PASS \
  --output report.txt
```

### Disseminate via HTTP POST (legacy `decimate`/`post`)

```bash
# Header aliases keep structured JSON clean while still sending auth headers
zyra disseminate post results.json https://api.example.com/upload \
  --credential header.Authorization=@ANALYTICS_BEARER \
  --credential header.Content-Type="application/json"
```

### Disseminate over FTP

```bash
zyra disseminate ftp -i artifact.bin ftp://dataserver.example.com/outbox/artifact.bin \
  --credential-file secrets.env \
  --credential user=@FTP_USER \
  --credential password=@FTP_PASS
```

### Discovery Search APIs

```bash
# Query an authenticated search endpoint with the same credential semantics
zyra search api --url https://catalog.example/api \
  --query "hrrr" \
  --credential token=$CATALOG_TOKEN \
  --auth bearer:$CATALOG_TOKEN

# Override credentials for a specific endpoint while keeping global defaults
zyra search api \
  --url https://catalog.example/api \
  --url https://staging.example/api \
  --query "wind" \
  --credential token=$GLOBAL_TOKEN \
  --url-credential https://staging.example/api token=$STAGING_TOKEN

# Echo a header end-to-end (httpbin)
zyra acquire api \
  --url https://httpbin.org/anything \
  --method GET \
  --auth bearer:demo-token \
  --output - | head

# Authenticated discovery against GitHub
export GITHUB_USER="your-username"
export GITHUB_TOKEN="ghp_yourtoken"
zyra search api \
  --url https://api.github.com \
  --query placeholder \
  --endpoint search/repositories \
  --qp q \
  --param q=language:python \
  --result-key items \
  --auth basic:$GITHUB_USER:$GITHUB_TOKEN \
  --limit 3 \
  --json
```

## API & MCP Integration

- **Domain args normalization** – REST clients can POST either `{"headers": {"X-Api-Key": "..."}}` or the CLI-style list `{"header": ["X-Api-Key: ..."]}`. The API layer flattens both into the same list before invoking the worker, so credentials resolve exactly like the CLI.
- **Credential echo suppression** – OpenAPI validation, MCP capability manifests, and FastAPI responses operate on sanitized header maps, ensuring bearer tokens never appear in logs or schema dumps.
- **Example JSON payload**

```json
{
  "stage": "acquire",
  "tool": "http",
  "args": {
    "url": "https://httpbin.org/basic-auth/demo/secret",
    "credentials": {
      "basic_user": "demo",
      "basic_password": "secret"
    },
    "headers": {
      "X-Request-ID": "{{$uuid}}"
    }
  }
}
```

## Testing Tips

1. Use `poetry run pytest -q tests/connectors/test_acquire_api_auth.py` to cover HTTP credential combinations.
2. FTP flows are covered by `tests/connectors/test_ftp_backend.py`; add cases there when introducing new aliases.
3. Regenerate the wizard manifest (`poetry run python -m zyra.utils.generate_capabilities`) after adding CLI flags that expose new credential slots.

## Troubleshooting

- **Missing env vars** – The helper raises `CredentialResolutionError` with the variable name when `$ENV` lookup fails.
- **Unexpected headers** – Run `poetry run zyra acquire http ... --trace` to see sanitized headers, or add `ZYRA_VERBOSITY=debug` for extra logging.
- **Credential manager scope** – Pass `--credential-file` explicitly during smoke tests so `@KEY` references resolve without relying on host configuration.

This page should evolve alongside connector work—update it whenever you add a new credential alias or surface (e.g., discovery connectors) so downstream teams can rely on a single source of truth.
