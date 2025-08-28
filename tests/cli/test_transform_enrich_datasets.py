from __future__ import annotations

import json

from zyra.cli import main as cli_main
from zyra.connectors.discovery import LocalCatalogBackend


def test_transform_enrich_datasets_shallow_profile_sos(tmp_path):
    items = LocalCatalogBackend().search("tsunami", limit=1)
    items_json = tmp_path / "items.json"
    items_json.write_text(json.dumps([i.__dict__ for i in items]), encoding="utf-8")
    out_path = tmp_path / "enriched.json"
    code = cli_main(
        [
            "transform",
            "enrich-datasets",
            "--items-file",
            str(items_json),
            "--enrich",
            "shallow",
            "--profile",
            "sos",
            "--output",
            str(out_path),
        ]
    )
    assert int(code) == 0
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert isinstance(data, list) and data
    e = data[0].get("enrichment") or {}
    spt = e.get("spatial") or {}
    assert spt.get("crs") == "EPSG:4326"
    assert spt.get("bbox") == [-180.0, -90.0, 180.0, 90.0]
