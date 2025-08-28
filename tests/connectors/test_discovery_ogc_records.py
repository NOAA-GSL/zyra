from __future__ import annotations

from zyra.connectors.discovery.ogc_records import OGCRecordsBackend

SAMPLE_RECORDS = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "id": "temp-1",
            "properties": {
                "title": "Global Temperature Tiles",
                "description": "OGC tiles of global temperature",
            },
            "links": [
                {
                    "rel": "self",
                    "href": "https://example.com/collections/temp/items?f=json",
                },
                {"rel": "data", "href": "https://example.com/collections/temp"},
            ],
        },
        {
            "type": "Feature",
            "id": "precip-1",
            "properties": {
                "title": "Precipitation",
                "description": "Accumulated precipitation",
            },
            "links": [
                {
                    "rel": "items",
                    "href": "https://example.com/collections/precip/items",
                },
            ],
        },
    ],
}


def test_ogc_records_search_matches_properties():
    import json

    backend = OGCRecordsBackend(
        endpoint="https://example.com/collections/temp/items",
        items_json=json.dumps(SAMPLE_RECORDS),
    )
    items = backend.search("temperature", limit=5)
    assert any("Temperature" in d.name for d in items)
    assert all(d.source == "ogc-records" for d in items)
    assert any(
        d.uri.endswith("/collections/temp/items") or "items" in d.uri for d in items
    )
