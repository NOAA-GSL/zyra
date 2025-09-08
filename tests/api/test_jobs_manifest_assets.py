from __future__ import annotations

import time

from fastapi.testclient import TestClient
from zyra.api.server import app


def _client(monkeypatch) -> TestClient:
    monkeypatch.setenv("DATAVIZHUB_API_KEY", "k")
    return TestClient(app)


def test_async_decimate_local_manifest(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch)
    out = tmp_path / "artifact.bin"
    # Submit async job: write '-' to local path
    payload = {
        "stage": "decimate",
        "command": "local",
        "mode": "async",
        "args": {"input": "-", "path": str(out)},
    }
    r = client.post("/v1/cli/run", json=payload, headers={"X-API-Key": "k"})
    assert r.status_code == 200
    js = r.json()
    job_id = js.get("job_id")
    assert job_id
    # Poll job status until terminal
    for _ in range(30):
        s = client.get(f"/v1/jobs/{job_id}", headers={"X-API-Key": "k"})
        assert s.status_code == 200
        body = s.json()
        if body.get("status") in {"succeeded", "failed", "canceled"}:
            break
        time.sleep(0.1)
    # Manifest should exist and include artifact entries
    m = client.get(f"/v1/jobs/{job_id}/manifest", headers={"X-API-Key": "k"})
    assert m.status_code == 200
    manifest = m.json()
    arts = manifest.get("artifacts") or []
    assert isinstance(arts, list)
    # Entries contain name + media_type
    assert all("name" in a for a in arts)
    assert all("media_type" in a for a in arts)
