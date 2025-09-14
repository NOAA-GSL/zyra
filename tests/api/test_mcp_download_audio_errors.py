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


def test_download_audio_content_type_mismatch(monkeypatch):
    client = TestClient(create_app())
    monkeypatch.setenv("ZYRA_ENABLE_MCP", "1")
    monkeypatch.setenv("DATAVIZHUB_API_KEY", "k")

    def fake_request(
        method, url, headers=None, params=None, timeout=None, stream=False
    ):  # noqa: ARG001
        return _Resp(
            200, headers={"Content-Type": "audio/mpeg"}, chunks=[b"x"]
        )  # wrong type

    import requests

    monkeypatch.setattr(requests, "request", fake_request)
    r = client.post(
        "/v1/mcp",
        json={
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "download-audio",
                "arguments": {
                    "profile": "limitless",
                    "since": "2025-01-01T00:00:00Z",
                    "duration": "PT30M",
                },
            },
            "id": 1,
        },
        headers={"X-API-Key": "k"},
    )
    assert r.status_code == 200
    js = r.json()
    assert (
        js.get("error", {}).get("code") == -32603
    )  # internal error from tool exception


def test_download_audio_missing_time_args(monkeypatch):
    client = TestClient(create_app())
    monkeypatch.setenv("ZYRA_ENABLE_MCP", "1")
    monkeypatch.setenv("DATAVIZHUB_API_KEY", "k")

    r = client.post(
        "/v1/mcp",
        json={
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": "download-audio", "arguments": {}},
            "id": 2,
        },
        headers={"X-API-Key": "k"},
    )
    assert r.status_code == 200
    js = r.json()
    assert js.get("error", {}).get("code") == 400


def test_download_audio_duration_exceeded(monkeypatch):
    client = TestClient(create_app())
    monkeypatch.setenv("ZYRA_ENABLE_MCP", "1")
    monkeypatch.setenv("DATAVIZHUB_API_KEY", "k")

    r = client.post(
        "/v1/mcp",
        json={
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "download-audio",
                "arguments": {
                    "profile": "limitless",
                    "since": "2025-01-01T00:00:00Z",
                    "duration": "PT3H",
                },
            },
            "id": 3,
        },
        headers={"X-API-Key": "k"},
    )
    assert r.status_code == 200
    js = r.json()
    assert js.get("error", {}).get("code") == 400
