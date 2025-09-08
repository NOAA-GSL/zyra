from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from zyra.api.server import app


def _has_matplotlib() -> bool:
    try:  # pragma: no cover - import guard
        import matplotlib  # noqa: F401

        return True
    except Exception:
        return False


@pytest.mark.skipif(not _has_matplotlib(), reason="Matplotlib not available")
def test_domain_visualize_heatmap_happy(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATAVIZHUB_API_KEY", "k")
    client = TestClient(app)
    out = tmp_path / "heat.png"
    r = client.post(
        "/v1/visualize",
        json={
            "tool": "heatmap",
            "args": {
                "input": "samples/demo.npy",
                "output": str(out),
                "width": 320,
                "height": 160,
            },
            "options": {"sync": True},
        },
        headers={"X-API-Key": "k"},
    )
    assert r.status_code == 200, r.text
    js = r.json()
    assert js.get("status") == "ok"
    assert out.exists() and out.stat().st_size > 0
