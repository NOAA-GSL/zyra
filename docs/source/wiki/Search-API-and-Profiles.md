# Search API and Profiles

Zyra exposes dataset discovery via the CLI and the HTTP API. Searches can be performed against the packaged SOS catalog, custom local catalogs, and remote OGC sources (WMS and OGC API - Records). Scoring is field‑weighted and can be customized with profiles.

## CLI

Examples:

- Local SOS (bundled profile):
  - `zyra search --query "tsunami" --profile sos`
- Custom catalog file:
  - `zyra search --query "temperature" --catalog-file pkg:zyra.assets.metadata/sos_dataset_metadata.json`
- OGC WMS (remote-only by default when remote endpoints provided):
  - `zyra search --query "Temperature" --ogc-wms "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi?service=WMS&request=GetCapabilities"`
- OGC API - Records:
  - `zyra search --query "lake" --ogc-records "https://demo.pygeoapi.io/master/collections/lakes/items?limit=100" --remote-only`
- Combine sources via profile file:
  - `zyra search --query "temperature" --profile-file ./samples/profiles/sos.json`
- Include local alongside remote:
  - `zyra search --query "Temperature" --ogc-wms <cap-url> --include-local`
- Optional enrichment:
  - `zyra search --query "sst" --profile gibs --enrich shallow`

## HTTP API

Endpoints:

- `GET /v1/search` — Basic search with optional enrichment. Returns a JSON array of items: `{ id, name, description, source, format, uri }`.
- `GET /v1/search/profiles` — Bundled profiles metadata: `{ profiles: [...], entries: [{ id, name, description, keywords }] }`.
- `POST /v1/search` — JSON body variant. When `analyze: true`, returns `{ items, analysis }` (see Analysis below).

GET /search query params:

- Required: `q` (query string)
- Optional (discovery): `limit`, `catalog_file`, `profile`, `profile_file`, `ogc_wms`, `ogc_records`, `remote_only`, `include_local`
- Optional (enrichment): `enrich=shallow|capabilities|probe`, `enrich_timeout`, `enrich_workers`, `cache_ttl`, `offline`, `https_only`, `allow_hosts`, `deny_hosts`, `max_probe_bytes`

POST /search body keys:

- Discovery keys mirror GET. Use `query`, `limit`, `catalog_file`, `profile`, `profile_file`, `ogc_wms`, `ogc_records`, `remote_only`, `include_local`.
- Analysis: `analyze: true` adds an `analysis` block derived from LLM prompts. You can also provide `analysis_limit` to cap items included in analysis.

### Analysis (LLM ranking)

- POST `/v1/search` with `analyze: true` performs LLM-assisted summarization and ranking.
- Response includes `analysis.summary` and `analysis.picks`.

Flags:

- `--query`, `-q`: search string (alternative to the positional `query`)
- `--catalog-file`: path or `pkg:module/resource`
- `--profile`: bundled name under `zyra.assets.profiles` (e.g., `sos`, `gibs`, `pygeoapi`)
- `--profile-file`: external JSON profile
- `--ogc-wms`: WMS GetCapabilities URL
- `--ogc-records`: Records items URL
- `--remote-only`: skip local catalog
- `--include-local`: include local when remote is specified
- Output: table (default), `--json`, `--yaml`

## Enrichment (CLI and API)

Zyra supports optional metadata enrichment at three levels: `shallow`, `capabilities`, and `probe`.

- Shallow: heuristics from existing fields (fast, offline-friendly).
- Capabilities: parse remote descriptors (WMS, OGC Records, STAC; supports local files when offline).
- Probe: inspect data assets (NetCDF/GeoTIFF) with strict size and time guards; requires optional libs (`xarray`, `rasterio`).

Flags (CLI and API):

- `enrich`: `shallow|capabilities|probe`
- `enrich_timeout`, `enrich_workers`, `cache_ttl`
- Guards: `offline`, `https_only`, `allow_hosts`, `deny_hosts`, `max_probe_bytes`

Profiles can provide defaults (e.g., spatial bbox/CRS) and license policies. When no profile is provided and the local SOS catalog is included, Zyra auto-applies the SOS defaults to `sos-catalog` items only.

Response: JSON array of items with fields:

- `id`, `name`, `description`, `source` (`sos-catalog` | `ogc-wms` | `ogc-records`), `format`, `uri`

Examples (search only):

- `GET /search?q=tsunami&profile=sos&limit=5`
- `GET /search?q=Temperature&ogc_wms=https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi?service=WMS%26request=GetCapabilities`
- `GET /search?q=landsat&profile=pygeoapi&limit=5`

POST with enrichment and analysis:

```bash
curl -sS -H "X-API-Key: $API_KEY" -H 'Content-Type: application/json' \
  -X POST http://localhost:8000/v1/search \
  -d '{
        "query": "tsunami history datasets",
        "limit": 20,
        "profile": "sos",
        "enrich": "shallow",
        "analyze": true
      }' | python -m json.tool
```

## Enrichment (Overview)

Search supports optional metadata enrichment (shallow|capabilities|probe). For larger batch workflows, prefer using the transform enrichment utilities and CLI.

- API: set `enrich=...` on `GET /v1/search` or include `enrich` keys in `POST /v1/search`.
- Transform CLI: see Dataset-Enrichment.md for `transform enrich-datasets` and policies.

Offline testing with local files:

- WMS (capabilities XML): `ogc_wms=file:/app/samples/ogc/sample_wms_capabilities.xml`
- Records (items JSON): `ogc_records=file:/app/samples/ogc/sample_records.json`

## Profiles

Profiles combine source lists and scoring weights. Bundled profiles live under
`zyra.assets.profiles`:

- `sos`: packaged SOS dataset catalog
- `gibs`: NASA GIBS WMS capabilities
- `pygeoapi`: pygeoapi demo collections (Records)

Example profile JSON:

```json
{
  "sources": {
    "local": { "catalog_file": "pkg:zyra.assets.metadata/sos_dataset_metadata.json" },
    "ogc_wms": [
      "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi?service=WMS&request=GetCapabilities"
    ],
    "ogc_records": [
      "https://demo.pygeoapi.io/master/collections/lakes/items?limit=100"
    ]
  },
  "weights": { "title": 3, "description": 2, "keywords": 1 }
}

## Security & Allowed Paths

When using file paths for `catalog_file` or `profile_file`, the server enforces allowlists:

- Catalogs must be under `ZYRA_CATALOG_DIR` or `DATA_DIR`.
- Profiles must be under `ZYRA_PROFILE_DIR` or `DATA_DIR`.
- Packaged references are allowed with `pkg:module/resource`.

This policy protects against path traversal and SSRF‑like issues during enrichment.
```
