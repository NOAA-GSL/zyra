# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from fastapi.testclient import TestClient

from zyra.api.server import app


def _client(monkeypatch) -> TestClient:
    monkeypatch.setenv("DATAVIZHUB_API_KEY", "k")
    return TestClient(app)


def test_assets_in_visualize_batch_dir(monkeypatch, tmp_path) -> None:
    # Use animate with output_dir (no frames generated without heavy libs),
    # but verify the output_dir itself is surfaced as an asset when it exists.
    client = _client(monkeypatch)
    outdir = tmp_path / "frames"
    outdir.mkdir(parents=True, exist_ok=True)
    r = client.post(
        "/v1/visualize",
        json={
            "tool": "animate",
            "args": {"input": "samples/demo.npy", "output_dir": str(outdir)},
            "options": {"sync": True},
        },
        headers={"X-API-Key": "k"},
    )
    # Command may fail if backend deps missing, but assets should include directory when present
    js = r.json()
    assets = js.get("assets") or []
    assert any(a.get("uri") == str(outdir) for a in assets)
