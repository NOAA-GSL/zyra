# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from fastapi.testclient import TestClient

from zyra.api.server import app


def test_disseminate_post_validation_error(monkeypatch) -> None:
    monkeypatch.setenv("DATAVIZHUB_API_KEY", "k")
    client = TestClient(app)
    r = client.post(
        "/v1/disseminate",
        json={"tool": "post", "args": {"input": "-"}},
        headers={"X-API-Key": "k"},
    )
    assert r.status_code == 400
    js = r.json()
    assert js.get("status") == "error"
    assert js.get("error", {}).get("type") == "validation_error"


def test_export_post_validation_error(monkeypatch) -> None:
    monkeypatch.setenv("DATAVIZHUB_API_KEY", "k")
    client = TestClient(app)
    r = client.post(
        "/v1/export",
        json={"tool": "post", "args": {"input": "-"}},
        headers={"X-API-Key": "k"},
    )
    assert r.status_code == 400
    js = r.json()
    assert js.get("status") == "error"
    assert js.get("error", {}).get("type") == "validation_error"
