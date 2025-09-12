# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import re

from zyra.connectors.discovery import LocalCatalogBackend


def test_local_catalog_search_basic_results():
    backend = LocalCatalogBackend()
    items = backend.search("tsunami", limit=5)
    assert 1 <= len(items) <= 5
    for d in items:
        assert d.id and isinstance(d.id, str)
        assert d.name and isinstance(d.name, str)
        assert d.source == "sos-catalog"
        assert d.uri.startswith("ftp://") or d.uri.startswith("http")


def test_local_catalog_search_limit_and_matching():
    backend = LocalCatalogBackend()
    items = backend.search("earthquake", limit=2)
    assert len(items) <= 2
    # Ensure the term appears in at least one of the fields used for scoring
    rx = re.compile("earthquake", re.IGNORECASE)
    assert any(
        rx.search(d.name) or (d.description and rx.search(d.description)) for d in items
    )
