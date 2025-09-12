# Search API and Profiles

Zyra exposes dataset discovery via the CLI and the HTTP API. Searches can be
performed against the packaged SOS catalog, custom local catalogs, and remote
OGC sources (WMS and OGC API - Records). Scoring is field-weighted and can be
customized with profiles.

## CLI

Examples:

- Local SOS (bundled profile):
  - `zyra search --query "tsunami" --profile sos`
- Custom catalog file:
  - `zyra search --query "temperature" --catalog-file pkg:zyra.assets.metadata/sos_dataset_metadata.json --json`
- OGC WMS (remote-only by default when remote endpoints provided):
  - `zyra search --query "Temperature" --ogc-wms "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi?service=WMS&request=GetCapabilities"`
- OGC API - Records:
  - `zyra search --query "lake" --ogc-records "https://demo.pygeoapi.io/master/collections/lakes/items?limit=100" --remote-only`
- Combine sources via profile file:
  - `zyra search --query "temperature" --profile-file ./samples/profiles/sos.json --json`
- Include local alongside remote:
  - `zyra search --query "Temperature" --ogc-wms <cap-url> --include-local`

### Semantic Search (LLM-assisted)

- Natural language → planned `zyra search` execution:
  - `zyra search --semantic "Find global sea surface temperature layers from NASA" --limit 10 --show-plan`
  - Heuristics map common intents to profiles (e.g., NASA/SST → `gibs`). `--show-plan` prints the raw and effective plans.

### Semantic Analysis (LLM ranking)

- Perform a broad search and let the LLM summarize and rank results:
  - `zyra search --semantic-analyze --query "hurricanes that have hit new orleans" --limit 20 --json`
  - Output includes `analysis.summary` and `analysis.picks` (IDs with reasons).

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

## HTTP API

Endpoints:

- `GET /search` — query via URL params; returns items (supports enrichment)
- `POST /search` — JSON body; set `analyze: true` to include LLM-assisted `analysis`

Query params:

- `q`: search string (required)
- `limit`: 1..100
- `catalog_file`: path or `pkg:module/resource`
- `profile`: bundled profile name (e.g., `sos`, `gibs`, `pygeoapi`)
- `profile_file`: external JSON profile path
- `ogc_wms`: comma-separated list of capabilities URLs
- `ogc_records`: comma-separated list of items URLs
- `remote_only`: boolean
- `include_local`: boolean
- Enrichment and guards (optional): `enrich`, `enrich_timeout`, `enrich_workers`, `cache_ttl`, `offline`, `https_only`, `allow_hosts`, `deny_hosts`, `max_probe_bytes`

Response: JSON array of items with fields:

- `id`, `name`, `description`, `source` (`sos-catalog` | `ogc-wms` | `ogc-records`), `format`, `uri`

Examples (search only):

- `GET /search?q=tsunami&profile=sos&limit=5`
- `GET /search?q=Temperature&ogc_wms=https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi?service=WMS%26request=GetCapabilities`
- `GET /search?q=landsat&profile=pygeoapi&limit=5`

POST with enrichment and analysis:

```bash
curl -sS -H "X-API-Key: $API_KEY" -H 'Content-Type: application/json' \
  -X POST http://localhost:8000/search \
  -d '{
        "query": "tsunami history datasets",
        "limit": 20,
        "profile": "sos",
        "enrich": "shallow",
        "analyze": true
      }' | python -m json.tool
```

## Transform: Batch Enrich

Use `transform enrich-datasets` to enrich an items JSON file (list or `{ "items": [...] }`) with the same options available to the API and `zyra search`:

```
zyra transform enrich-datasets \
  --items-file items.json \
  --enrich shallow \
  --profile sos \
  --offline \
  --output enriched.json
```

Each item should contain: `id`, `name`, `description`, `source`, `format`, `uri`.

### Offline testing with local files

When outbound network is unavailable, you can point OGC sources to local files:

- WMS (capabilities XML): `ogc_wms=file:/app/samples/ogc/sample_wms_capabilities.xml`
- Records (items JSON): `ogc_records=file:/app/samples/ogc/sample_records.json`

CLI equivalents:

- `zyra search --query "temperature" --ogc-wms file:samples/ogc/sample_wms_capabilities.xml`
- `zyra search --query "precip" --ogc-records file:samples/ogc/sample_records.json`

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
```
