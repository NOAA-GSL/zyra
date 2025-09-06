from __future__ import annotations

from fastapi.testclient import TestClient
from zyra.api.server import app


def test_decimate_domain_local_sync(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATAVIZHUB_API_KEY", "k")
    client = TestClient(app)
    out_path = tmp_path / "ok.bin"
    body = {
        "tool": "local",
        "args": {"input": "-", "output": str(out_path)},
        "options": {"mode": "sync"},
    }
    r = client.post("/decimate", json=body, headers={"X-API-Key": "k"})
    assert r.status_code == 200
    js = r.json()
    assert js.get("status") == "ok"
    assert js.get("exit_code") in (0, None)
    assert out_path.exists()


def test_process_domain_invalid_tool(monkeypatch) -> None:
    monkeypatch.setenv("DATAVIZHUB_API_KEY", "k")
    client = TestClient(app)
    r = client.post(
        "/process",
        json={"tool": "nope", "args": {}},
        headers={"X-API-Key": "k"},
    )
    assert r.status_code == 400
    js = r.json()
    assert "error" in js.get("detail", {})


def test_acquire_transform_invalid_tool(monkeypatch) -> None:
    monkeypatch.setenv("DATAVIZHUB_API_KEY", "k")
    client = TestClient(app)
    for path in ("/acquire", "/transform"):
        r = client.post(
            path, json={"tool": "nope", "args": {}}, headers={"X-API-Key": "k"}
        )
        assert r.status_code == 400
        js = r.json()
        assert "error" in js.get("detail", {})
