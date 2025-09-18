# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from fastapi.testclient import TestClient

from zyra.api.server import app


def test_narrate_swarm_domain_sync(monkeypatch) -> None:
    monkeypatch.setenv("DATAVIZHUB_API_KEY", "k")
    client = TestClient(app)
    body = {
        "tool": "swarm",
        "args": {"preset": "kids_policy_basic", "provider": "mock", "pack": "-"},
        "options": {"mode": "sync"},
    }
    r = client.post("/v1/narrate", json=body, headers={"X-API-Key": "k"})
    assert r.status_code == 200
    js = r.json()
    assert js.get("status") == "ok"
    assert js.get("exit_code") in (0, None)
    # stdout should contain a narrative_pack YAML
    assert isinstance(js.get("stdout"), str) and "narrative_pack:" in js.get("stdout")
