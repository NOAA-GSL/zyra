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


def test_preset_limitless_audio_streams(monkeypatch):
    client = TestClient(create_app())

    def fake_request(
        method, url, headers=None, params=None, timeout=None, stream=False
    ):  # noqa: ARG001
        return _Resp(
            200,
            headers={
                "Content-Type": "audio/ogg",
                "Content-Disposition": 'attachment; filename="a.ogg"',
            },
            chunks=[b"abc", b"def"],
        )

    import requests

    monkeypatch.setattr(requests, "request", fake_request)
    r = client.post(
        "/v1/presets/limitless/audio",
        json={
            "since": "2025-01-01T00:00:00Z",
            "duration": "PT30M",
            "audio_source": "pendant",
        },
    )
    assert r.status_code == 200
    assert r.headers.get("content-type") == "audio/ogg"
    assert "filename=" in (r.headers.get("content-disposition") or "")
    assert r.content == b"abcdef"


def test_preset_limitless_audio_duration_limit(monkeypatch):
    client = TestClient(create_app())

    # No network call needed; failure is preflight
    r = client.post(
        "/v1/presets/limitless/audio",
        json={"since": "2025-01-01T00:00:00Z", "duration": "PT3H"},
    )
    assert r.status_code == 400
