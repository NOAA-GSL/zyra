# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json

from zyra.connectors.discovery import LocalCatalogBackend


def test_local_catalog_from_file(tmp_path):
    # Minimal catalog with two entries
    data = [
        {
            "url": "https://example.com/datasets/foo/",
            "title": "Foo Dataset",
            "description": "Contains tsunami and earthquake events",
            "keywords": ["tsunami", "earthquake"],
            "ftp_download": None,
        },
        {
            "url": "https://example.com/datasets/bar/",
            "title": "Bar Dataset",
            "description": "Temperature dataset",
            "keywords": ["temperature"],
            "ftp_download": None,
        },
    ]
    p = tmp_path / "catalog.json"
    p.write_text(json.dumps(data), encoding="utf-8")

    b = LocalCatalogBackend(str(p))
    res = b.search("tsunami", limit=5)
    assert any("Foo" in d.name for d in res)
    # Ensure path override worked by checking both items are discoverable via keywords
    res2 = b.search("temperature", limit=5)
    assert any("Bar" in d.name for d in res2)
