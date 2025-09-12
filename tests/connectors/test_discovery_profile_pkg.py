# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from zyra.connectors.discovery import LocalCatalogBackend


def test_local_catalog_pkg_reference_loads_asset():
    b = LocalCatalogBackend("pkg:zyra.assets.metadata/sos_dataset_metadata.json")
    items = b.search("tsunami", limit=3)
    assert isinstance(items, list)
    assert 1 <= len(items) <= 3
