# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from zyra.connectors.discovery import DatasetMetadata
from zyra.transform.enrich import enrich_items


def test_wms_capabilities_extract_bbox_ex_geographic(tmp_path):
    uri = "file:tests/testdata/wms_capabilities_sample.xml"
    item = DatasetMetadata(
        id="w1",
        name="Global SST",
        description=None,
        source="ogc-wms",
        format="WMS",
        uri=uri,
    )
    out = enrich_items(
        [item], level="capabilities", timeout=1.0, workers=1, cache_ttl=10, offline=True
    )
    assert out and out[0].enrichment is not None
    spt = out[0].enrichment.spatial
    assert spt is not None
    assert spt.crs == "EPSG:4326"
    assert spt.bbox == [-180.0, -90.0, 180.0, 90.0]


def test_wms_capabilities_extract_bbox_latlon(tmp_path):
    uri = "file:tests/testdata/wms_capabilities_latlon.xml"
    item = DatasetMetadata(
        id="w2",
        name="Regional Layer",
        description=None,
        source="ogc-wms",
        format="WMS",
        uri=uri,
    )
    out = enrich_items(
        [item], level="capabilities", timeout=1.0, workers=1, cache_ttl=10, offline=True
    )
    assert out and out[0].enrichment is not None
    spt = out[0].enrichment.spatial
    assert spt is not None
    assert spt.crs == "EPSG:4326"
    assert spt.bbox == [10.0, -5.0, 20.0, 15.0]
