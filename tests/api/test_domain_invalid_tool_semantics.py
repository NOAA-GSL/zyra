from __future__ import annotations

from fastapi.testclient import TestClient
from zyra.api.server import app


def _client(monkeypatch) -> TestClient:
    monkeypatch.setenv("DATAVIZHUB_API_KEY", "k")
    return TestClient(app)


def test_invalid_tool_still_returns_400(monkeypatch) -> None:
    client = _client(monkeypatch)
    for path in ("/v1/process", "/v1/acquire", "/v1/visualize", "/v1/decimate"):
        r = client.post(
            path, json={"tool": "nope", "args": {}}, headers={"X-API-Key": "k"}
        )
        assert r.status_code == 400
        js = r.json()
        assert js.get("status") == "error"
        assert js.get("error", {}).get("type") == "validation_error"
