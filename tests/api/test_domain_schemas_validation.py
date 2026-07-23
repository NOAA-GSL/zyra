# SPDX-License-Identifier: Apache-2.0
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
        "/v1/visualize",
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
        "/v1/visualize",
        json={
            "tool": "compose-video",
            "args": {"output": "/tmp/out.mp4"},
        },
        headers={"X-API-Key": "k"},
    )
    assert r.status_code == 400
    js = r.json()
    assert js.get("error", {}).get("type") == "validation_error"


def test_visualize_compose_video_rejects_bad_preset_and_size(monkeypatch) -> None:
    client = _client(monkeypatch)
    base = {"frames": "./frames", "output": "/tmp/out.mp4"}
    for bad_args in (
        {**base, "preset": "imax"},
        {**base, "size": "4096"},
        {**base, "size": "0x2048"},
    ):
        r = client.post(
            "/v1/visualize",
            json={"tool": "compose-video", "args": bad_args},
            headers={"X-API-Key": "k"},
        )
        assert r.status_code == 400, bad_args
        js = r.json()
        assert js.get("error", {}).get("type") == "validation_error"


def test_process_reproject_rejects_bad_args(monkeypatch) -> None:
    client = _client(monkeypatch)
    base = {"input": "disk.png", "output": "/tmp/out.tif"}
    for bad_args in (
        {"output": "/tmp/out.tif"},  # missing input
        {**base, "resampling": "cubic"},
        {**base, "bounds": [1.0, 2.0, 3.0]},  # not 4 values
        {**base, "dst_bounds": "everything"},  # only 'auto' is a valid string
        {**base, "width": 0},
    ):
        r = client.post(
            "/v1/process",
            json={"tool": "reproject", "args": bad_args},
            headers={"X-API-Key": "k"},
        )
        assert r.status_code == 400, bad_args
        js = r.json()
        assert js.get("error", {}).get("type") == "validation_error"


def test_acquire_http_requires_source(monkeypatch) -> None:
    client = _client(monkeypatch)
    # No url/inputs/manifest/list should fail early via schema
    r = client.post(
        "/v1/acquire",
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
        "/v1/decimate",
        json={"tool": "ftp", "args": {"input": "-"}},
        headers={"X-API-Key": "k"},
    )
    assert r.status_code == 400
    js = r.json()
    assert js.get("error", {}).get("type") == "validation_error"
