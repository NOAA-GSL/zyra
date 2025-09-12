# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from fastapi.testclient import TestClient

from zyra.api.server import app


def test_search_endpoint_basic():
    client = TestClient(app)
    r = client.get("/v1/search", params={"q": "tsunami", "limit": 3})
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert 1 <= len(data) <= 3
    for d in data:
        assert set(["id", "name", "source", "format", "uri"]).issubset(d.keys())
