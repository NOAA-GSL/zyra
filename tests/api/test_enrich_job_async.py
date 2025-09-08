from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient
from zyra.api.server import create_app
from zyra.connectors.discovery import LocalCatalogBackend


@pytest.mark.timeout(10)
def test_post_enrich_async_job_and_ws_progress(monkeypatch):
    # Force in-memory mode for stability in CI
    monkeypatch.setenv("ZYRA_USE_REDIS", "0")
    monkeypatch.setenv("DATAVIZHUB_USE_REDIS", "0")
    client = TestClient(create_app())
    # Prepare items from local SOS
    items = LocalCatalogBackend().search("tsunami", limit=1)
    items_dicts = [i.__dict__ for i in items]
    r = client.post(
        "/enrich",
        json={
            "items": items_dicts,
            "enrich": "shallow",
            "async": True,
        },
    )
    assert r.status_code == 200, r.text
    job_id = r.json().get("job_id")
    assert job_id
    # Connect to WS (no API key expected unless configured)
    with client.websocket_connect(f"/v1/ws/jobs/{job_id}?stream=progress") as ws:
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
    # Poll job status (fresh client to avoid WS portal interference)
    status = None
    poll_client = TestClient(create_app())
    for _ in range(20):
        s = poll_client.get(f"/v1/jobs/{job_id}")
        assert s.status_code == 200
        status = s.json().get("status")
        if status in {"succeeded", "failed", "canceled"}:
            break
        time.sleep(0.1)
    assert status == "succeeded"
