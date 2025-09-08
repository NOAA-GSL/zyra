from __future__ import annotations

import io
import json
import time

import pytest
from fastapi.testclient import TestClient
from zyra.api.server import app


@pytest.mark.anyio
def test_http_ws_e2e_with_api_key(monkeypatch) -> None:
    monkeypatch.setenv("DATAVIZHUB_API_KEY", "k")
    client = TestClient(app)

    # 1) Upload
    file_content = b"hello-e2e"
    files = {"file": ("sample.txt", io.BytesIO(file_content), "text/plain")}
    r = client.post("/v1/upload", files=files, headers={"X-API-Key": "k"})
    assert r.status_code == 200, r.text
    file_id = r.json()["file_id"]

    # 2) Run async job (decimate local using file_id placeholder)
    body = {
        "stage": "decimate",
        "command": "local",
        "mode": "async",
        "args": {"input": f"file_id:{file_id}", "path": f"/tmp/e2e_{file_id}.bin"},
    }
    r2 = client.post("/v1/cli/run", json=body, headers={"X-API-Key": "k"})
    assert r2.status_code == 200, r2.text
    job_id = r2.json()["job_id"]

    # 3) WS stream progress (with api_key)
    with client.websocket_connect(
        f"/v1/ws/jobs/{job_id}?api_key=k&stream=progress"
    ) as ws:
        # Read messages until we get final one (exit_code present) or timeout
        got_progress = False
        end = time.time() + 5.0
        while time.time() < end:
            try:
                msg = ws.receive_text()
            except Exception:
                break
            try:
                data = json.loads(msg)
            except Exception:
                continue
            if "progress" in data:
                got_progress = True
            if "exit_code" in data:
                break
        assert got_progress

    # 4) Poll status and download
    for _ in range(10):
        s = client.get(f"/v1/jobs/{job_id}", headers={"X-API-Key": "k"})
        assert s.status_code == 200
        st = s.json()["status"]
        if st in {"succeeded", "failed", "canceled"}:
            break
        time.sleep(0.2)
    assert st == "succeeded"
    d = client.get(f"/v1/jobs/{job_id}/download", headers={"X-API-Key": "k"})
    assert d.status_code == 200

    # Negative path: missing key should yield 401
    r3 = client.get("/v1/cli/commands")
    assert r3.status_code == 401
    # WS unauthorized closes immediately (handshake raises on enter)
    with pytest.raises(Exception):
        with client.websocket_connect(f"/v1/ws/jobs/{job_id}?stream=progress"):
            pass
