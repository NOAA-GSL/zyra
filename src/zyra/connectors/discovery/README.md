# Discovery (search)

CLI: `zyra search`

Local catalog (SOS mirror)
- Basic: `zyra search "tsunami" -l 10`
- Output formats: add `--json`, `--yaml`, or `--table`
- Include local when remote sources provided: `--include-local`
- Use a custom catalog: `--catalog-file path/to/catalog.json`
- Profiles: `--profile sos` or `--profile-file profiles/custom.json`

Remote APIs
- OGC WMS GetCapabilities: `--ogc-wms https://host/wms?service=WMS&request=GetCapabilities`
  - Only remote results: `--remote-only`
- OGC API - Records: `--ogc-records https://host/records/collections/{id}/items`

Generic API search (federated)
- Subcommand: `zyra search api`
- Args: `--url <endpoint>` (repeatable), `--query`, `--limit`, `--timeout`, `--retries`, `--concurrency`
- Headers/params: `--header "K: V"` (repeatable), `--param key=value` (repeatable)
- POST mode: `--post --json-param key=val --json-body @body.json`
- Output shaping: `--fields k1,k2`, `--csv`, `--table`, `--sort`, `--dedupe dataset|link`, `--limit-total`
- OpenAPI diagnostics: `--print-openapi`, `--suggest-flags`

Examples
- `zyra search api --url https://api.example/v1/search --query "wind" --limit 20 --csv`
- `zyra search --ogc-wms https://host/wms?... --remote-only --table -l 15`
