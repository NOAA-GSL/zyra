from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from zyra.api.server import app
from zyra.api.workers import jobs as jb


def test_ws_api_key_enforcement(monkeypatch) -> None:
    monkeypatch.setenv("DATAVIZHUB_API_KEY", "sekret")
    client = TestClient(app)
    jid = jb.submit_job("process", "convert-format", {})
    # Wrong key: expect unauthorized message then close
    with client.websocket_connect(
        f"/ws/jobs/{jid}?api_key=wrong&stream=progress"
    ) as ws:
        msg = ws.receive_text()
        data = json.loads(msg)
        assert data.get("error") == "Unauthorized"
        # Next receive should fail due to close
        with pytest.raises(Exception):
            ws.receive_text()
    # Correct key: connect and publish a progress message, expect to receive it
    with client.websocket_connect(
        f"/ws/jobs/{jid}?api_key=sekret&stream=progress"
    ) as ws:
        jb._pub(f"jobs.{jid}.progress", {"progress": 0.7})
        # Drain until we see our published progress value (tolerate initial frames)
        got = None
        for _ in range(3):
            msg = ws.receive_text()
            data = json.loads(msg)
            if "progress" in data:
                got = data["progress"]
                if abs(float(got) - 0.7) < 1e-9:
                    break
        assert abs(float(got) - 0.7) < 1e-9
