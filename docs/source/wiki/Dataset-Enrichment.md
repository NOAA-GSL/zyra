# Dataset Enrichment

Zyra can enrich search results or standalone item lists with additional metadata (variables, time bounds, spatial hints, size info, license defaults). Use this to quickly assess datasets before building pipelines.

## Levels
- `shallow`: heuristics from names/descriptions; cheap and offline‑friendly.
- `capabilities`: parse remote descriptors (e.g., WMS GetCapabilities, OGC Records); respects offline/HTTPS/allow/deny guards.
- `probe`: cautiously inspect referenced data (e.g., NetCDF/GeoTIFF) within size/time limits. Requires relevant extras.

## API (with Search)
- GET `/v1/search?...&enrich=shallow|capabilities|probe` (see Search-API-and-Profiles.md)
- POST `/v1/search` with `enrich` keys mirrors GET.

Common options (query params or POST keys)
- `enrich_timeout` (seconds), `enrich_workers` (concurrency), `cache_ttl` (seconds)
- Guards: `offline`, `https_only`, `allow_hosts`, `deny_hosts`, `max_probe_bytes`
- Profile‑scoped defaults/policies are applied when a `profile` or `profile_file` is provided.

## Transform CLI (batch)

Enrich a saved items JSON (either a bare list or `{ "items": [...] }`).

```bash
zyra transform enrich-datasets \
  --items-file items.json \
  --enrich shallow \
  --profile sos \
  --offline \
  --output enriched.json
```

Each item should include: `id`, `name`, `description`, `source`, `format`, `uri`.

## Security & Allowed Paths

When using files in `catalog_file` or `profile_file` contexts:
- Catalogs must be under `ZYRA_CATALOG_DIR` or `DATA_DIR`.
- Profiles must be under `ZYRA_PROFILE_DIR` or `DATA_DIR`.
- Packaged references are allowed with `pkg:module/resource`.

## Requirements
- Extras: install `processing` and `visualization` as needed for certain probes.
- Network: disable with `offline` or require TLS with `https_only`.

## See Also
- Search-API-and-Profiles.md
- Workflow-Stages.md (import/process/visualize/export)
