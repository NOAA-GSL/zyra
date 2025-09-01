## Phase 1: Module Scaffolding
- [ ] Create `src/zyra/connectors/discovery/` for discovery logic.
- [ ] Define a **`DiscoveryBackend` interface** (similar to connector backends) with methods like:
  ```python
  class DiscoveryBackend:
      def search(self, query: str, **kwargs) -> List[DatasetMetadata]:
          ...
  ```
- [ ] Add `DatasetMetadata` model (name, description, source, format, URI).

---

## Phase 2: Backends for Discovery
- [ ] Implement a **Local Catalog Backend**: reads from a JSON/YAML index of datasets stored in `assets/catalog.json`.
- [ ] Implement a **Remote API Backend**: queries NOAA, Pangeo, or CKAN catalogs.
- [ ] Register backends in `connectors.discovery.backends`.

---

## Phase 3: Integration with CLI
- [ ] Extend CLI (`cli.py`) with a new command:
  ```bash
  zyra search "NOAA GFS forecast"
  ```
- [ ] CLI should call discovery backends, print results as a table:
  ```
  ID   Name                  Format   URI
  1    GFS 2025-08-17 00z    NetCDF   s3://noaa/gfs/...
  2    HRRR Surface Temp     GRIB2    s3://noaa/hrrr/...
  ```
- [ ] Add option to export search results (`--json`, `--yaml`).

---

## Phase 4: API Integration
- [ ] Add `/search` endpoint in `api/` that accepts `query` and returns `DatasetMetadata[]`.
- [ ] Ensure API reuses the discovery module (don’t re-implement logic).

---

## Phase 5: Connectors Integration
- [ ] Allow direct ingestion from search results:
  ```bash
  zyra search "GFS" --select 1 | zyra ingest -
  ```
- [ ] Support programmatic chaining:
  ```python
  results = discovery.search("GFS")
  connectors.ingest(results[0].uri)
  ```

---

## Phase 6: Documentation & Examples
- [ ] Add documentation in `docs/source/discovery.rst`.
- [ ] Provide sample catalog (`assets/catalog.json`) with 3–5 NOAA datasets.
- [ ] Create CLI walkthrough: search → select → ingest → visualize.

---

## Stretch Goals
- Semantic search (LLM-assisted descriptions).
- Multi-backend search aggregation.
- Metadata enrichment (units, time ranges, variables available).
