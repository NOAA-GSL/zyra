from __future__ import annotations

from fastapi.testclient import TestClient

from zyra.api.server import app


def test_search_enrich_shallow_auto_sos_defaults():
    client = TestClient(app)
    # No explicit profile; local SOS included by default
    r = client.get(
        "/search",
        params={
            "q": "tsunami",
            "limit": 2,
            "enrich": "shallow",
            "enrich_timeout": 1.0,
        },
    )
    assert r.status_code == 200
    items = r.json()
    assert isinstance(items, list) and items
    # At least one item should be from sos-catalog and include spatial defaults
    sos = [i for i in items if i.get("source") == "sos-catalog"]
    assert sos, "Expected at least one sos-catalog item"
    e = sos[0].get("enrichment") or {}
    spt = e.get("spatial") or {}
    assert spt.get("crs") == "EPSG:4326"
    assert spt.get("bbox") == [-180.0, -90.0, 180.0, 90.0]
