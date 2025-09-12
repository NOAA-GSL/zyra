# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from zyra.connectors.discovery import DatasetMetadata
from zyra.transform.enrich import enrich_items


def test_stac_capabilities_collection_offline():
    item = DatasetMetadata(
        id="stac-sample",
        name="Sample Collection",
        description=None,
        source="ogc-records",
        format="OGC",
        uri="file:tests/testdata/stac_collection.json",
    )
    out = enrich_items(
        [item], level="capabilities", timeout=1.0, workers=1, cache_ttl=10, offline=True
    )
    assert out and out[0].enrichment is not None
    spt = out[0].enrichment.spatial
    assert spt is not None and spt.bbox == [-10.0, -5.0, 20.0, 15.0]
    t = out[0].enrichment.time
    assert (
        t is not None
        and t.start == "2020-01-01T00:00:00Z"
        and t.end == "2021-01-01T00:00:00Z"
    )
    vars = out[0].enrichment.variables
    assert any(v.name in {"B1", "blue"} for v in vars)
