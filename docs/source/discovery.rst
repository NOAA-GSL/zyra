Discovery Guide
================

Zyra includes a flexible discovery system to find datasets across multiple
sources:

- Packaged SOS catalog (offline, bundled)
- Custom local catalogs (JSON)
- Remote OGC endpoints: WMS (GetCapabilities) and OGC API - Records

Quick Start (CLI)
-----------------

::

  # SOS catalog (bundled profile)
  zyra search "tsunami" --profile sos

  # OGC WMS (remote only by default when remote is provided)
  zyra search "Temperature" \
    --ogc-wms "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi?service=WMS&request=GetCapabilities"

  # OGC Records (pygeoapi demo)
  zyra search "lake" \
    --ogc-records "https://demo.pygeoapi.io/master/collections/lakes/items?limit=100"

  # Include local results alongside remote
  zyra search "Temperature" --profile sos \
    --ogc-wms "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi?service=WMS&request=GetCapabilities" \
    --include-local

Semantic Search (LLM)
---------------------

Use the same LLM provider/model as the Wizard to turn natural language into a search plan:

::

  zyra search --semantic "Find global sea surface temperature layers from NASA" --limit 10 --show-plan

`--show-plan` prints both the raw plan (from the model) and the effective plan (after heuristics). The CLI then executes the plan and prints results.

Profiles
--------

Profiles bundle sources and scoring weights. Use ``--profile`` with a bundled
name, or ``--profile-file`` to load your own JSON. Bundled profiles live under
``zyra.assets.profiles``:

- ``sos`` — packaged SOS catalog
- ``gibs`` — NASA GIBS WMS capabilities
- ``pygeoapi`` — pygeoapi demo collections

See also: :doc:`wiki/Search-API-and-Profiles`.

HTTP API
--------

Endpoint: ``GET /search``

Parameters mirror the CLI flags (``q``, ``limit``, ``profile``, ``catalog_file``,
``ogc_wms``, ``ogc_records``, ``include_local``, ``remote_only``). Try the
interactive page at ``/examples``.

Offline Testing
---------------

OGC sources accept local files to facilitate testing without network access.

::

  # WMS capabilities (XML)
  zyra search "temperature" --ogc-wms file:samples/ogc/sample_wms_capabilities.xml

  # Records items (JSON)
  zyra search "precip" --ogc-records file:samples/ogc/sample_records.json

API Reference
-------------

For module-level API docs, see:

- :doc:`api/zyra.connectors.discovery`
- :doc:`api/zyra.connectors.discovery.ogc`
- :doc:`api/zyra.connectors.discovery.ogc_records`
