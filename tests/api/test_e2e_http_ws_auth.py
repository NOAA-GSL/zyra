# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import io
import json
import os
import time

import pytest
from fastapi.testclient import TestClient

from zyra.api.server import create_app


@pytest.mark.skipif(
    os.environ.get("CI") == "true",
    reason="Skip WS e2e in CI: flake with TestClient portal races",
)
@pytest.mark.timeout(10)
def test_http_ws_e2e_with_api_key(monkeypatch) -> None:
    monkeypatch.setenv("DATAVIZHUB_API_KEY", "k")
    client = TestClient(create_app())

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
        end = time.time() + 10.0
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

    # 4) Poll status and download — use a fresh client to avoid WS queue interference
    time.sleep(0.05)
    poll_client = TestClient(create_app())
    for _ in range(20):
        s = poll_client.get(f"/v1/jobs/{job_id}", headers={"X-API-Key": "k"})
        assert s.status_code == 200
        st = s.json()["status"]
        if st in {"succeeded", "failed", "canceled"}:
            break
        time.sleep(0.2)
    assert st == "succeeded"
    d = poll_client.get(f"/v1/jobs/{job_id}/download", headers={"X-API-Key": "k"})
    assert d.status_code == 200

    # Negative path: missing key should yield 401. Use a fresh client to avoid
    # any lingering WS state in the test client event loop.
    client2 = TestClient(create_app())
    r3 = client2.get("/v1/cli/commands")
    assert r3.status_code == 401
    # WS unauthorized closes immediately (handshake raises on enter)
    with pytest.raises(Exception):
        with client2.websocket_connect("/v1/ws/jobs/dummy?stream=progress"):
            pass


def test_http_ws_auth_negative(monkeypatch) -> None:
    """Negative auth checks isolated in a fresh app/client to avoid WS interference."""
    monkeypatch.setenv("DATAVIZHUB_API_KEY", "k")
    c = TestClient(create_app())
    # Unauthorized HTTP should return 401
    r = c.get("/v1/cli/commands")
    assert r.status_code == 401
    # Unauthorized WS should fail handshake
    with pytest.raises(Exception):
        with c.websocket_connect("/v1/ws/jobs/dummy?stream=progress"):
            pass
