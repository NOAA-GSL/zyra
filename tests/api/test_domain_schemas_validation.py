from __future__ import annotations

from fastapi.testclient import TestClient
from zyra.api.server import app


def _client(monkeypatch) -> TestClient:
    monkeypatch.setenv("DATAVIZHUB_API_KEY", "k")
    return TestClient(app)


def test_visualize_vector_density_validation(monkeypatch) -> None:
    client = _client(monkeypatch)
    # density must be in (0,1]
    r = client.post(
        "/visualize",
        json={
            "tool": "vector",
            "args": {
                "input": "samples/demo.nc",
                "uvar": "u",
                "vvar": "v",
                "output": "/tmp/out.png",
                "density": 1.5,
            },
        },
        headers={"X-API-Key": "k"},
    )
    assert r.status_code == 400
    js = r.json()
    assert js.get("error", {}).get("type") == "validation_error"


def test_visualize_compose_video_requires_frames(monkeypatch) -> None:
    client = _client(monkeypatch)
    # Missing required 'frames' should trigger validation_error
    r = client.post(
        "/visualize",
        json={
            "tool": "compose-video",
            "args": {"output": "/tmp/out.mp4"},
        },
        headers={"X-API-Key": "k"},
    )
    assert r.status_code == 400
    js = r.json()
    assert js.get("error", {}).get("type") == "validation_error"


def test_acquire_http_requires_source(monkeypatch) -> None:
    client = _client(monkeypatch)
    # No url/inputs/manifest/list should fail early via schema
    r = client.post(
        "/acquire",
        json={"tool": "http", "args": {}},
        headers={"X-API-Key": "k"},
    )
    assert r.status_code == 400
    js = r.json()
    assert js.get("error", {}).get("type") == "validation_error"


def test_decimate_ftp_requires_path(monkeypatch) -> None:
    client = _client(monkeypatch)
    # Missing 'path' should fail validation in schema
    r = client.post(
        "/decimate",
        json={"tool": "ftp", "args": {"input": "-"}},
        headers={"X-API-Key": "k"},
    )
    assert r.status_code == 400
    js = r.json()
    assert js.get("error", {}).get("type") == "validation_error"
