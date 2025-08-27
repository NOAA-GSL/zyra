from __future__ import annotations

import json

from zyra.connectors.discovery import LocalCatalogBackend
from zyra.transform.enrich import enrich_items


def test_profile_defaults_applied_to_sos_items():
    items = LocalCatalogBackend().search("tsunami", limit=1)
    # Load bundled sos profile defaults
    from importlib import resources as importlib_resources

    pkg = "zyra.assets.profiles"
    path = importlib_resources.files(pkg).joinpath("sos.json")
    with importlib_resources.as_file(path) as p:
        prof = json.loads(p.read_text(encoding="utf-8"))
    defaults = (prof.get("enrichment") or {}).get("defaults") or {}
    out = enrich_items(
        items,
        level="shallow",
        profile_defaults=defaults,
        defaults_sources=["sos-catalog"],
    )
    assert out and out[0].enrichment is not None
    s = out[0].enrichment.spatial
    assert (
        s is not None
        and s.crs == "EPSG:4326"
        and s.bbox == [-180.0, -90.0, 180.0, 90.0]
    )
