# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from fastapi.testclient import TestClient

from zyra.api.server import create_app


class _Resp:
    def __init__(self, status=200, headers=None, chunks=None, text=None):
        self.status_code = status
        self.headers = headers or {}
        self._chunks = chunks or []
        self.text = text or ""

    def iter_content(self, chunk_size=1024 * 1024):  # noqa: ARG002
        yield from self._chunks


def test_mcp_download_audio_limitless_since_duration(monkeypatch, tmp_path):
    # Use a fresh app with MCP enabled
    monkeypatch.setenv("ZYRA_ENABLE_MCP", "1")
    monkeypatch.setenv("DATAVIZHUB_API_KEY", "k")
    # Point DATA_DIR to temp dir for file writes
    monkeypatch.setenv("ZYRA_DATA_DIR", str(tmp_path))
    client = TestClient(create_app())

    # Mock outbound requests streaming
    def fake_request(
        method, url, headers=None, params=None, timeout=None, stream=False
    ):  # noqa: ARG001
        # Return an Ogg file with a content-disposition
        return _Resp(
            200,
            headers={
                "Content-Type": "audio/ogg",
                "Content-Disposition": 'attachment; filename="audio.ogg"',
            },
            chunks=[b"abc", b"def"],
        )

    import requests

    monkeypatch.setattr(requests, "request", fake_request)

    payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": "download-audio",
            "arguments": {
                "profile": "limitless",
                "since": "2025-01-01T00:00:00Z",
                "duration": "PT30M",
                "audio_source": "pendant",
                "output_dir": "tests",
            },
        },
        "id": 1,
    }
    r = client.post("/v1/mcp", json=payload, headers={"X-API-Key": "k"})
    assert r.status_code == 200
    js = r.json()
    res = js.get("result", {})
    path = res.get("path")
    assert isinstance(path, str) and path.endswith("audio.ogg")
    full = tmp_path / path
    assert full.exists() and full.read_bytes() == b"abcdef"
