from __future__ import annotations

from fastapi.testclient import TestClient

from zyra.api.server import app


def test_cli_commands_requires_api_key(monkeypatch) -> None:
    monkeypatch.setenv("DATAVIZHUB_API_KEY", "k")
    client = TestClient(app)
    # Missing header
    r = client.get("/v1/cli/commands")
    assert r.status_code == 401
    # Wrong header
    r = client.get("/v1/cli/commands", headers={"X-API-Key": "wrong"})
    assert r.status_code == 401
    # Correct header
    r = client.get("/v1/cli/commands", headers={"X-API-Key": "k"})
    assert r.status_code == 200
