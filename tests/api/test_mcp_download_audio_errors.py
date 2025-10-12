# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import pytest

from zyra.api.mcp_tools.audio import download_audio


class _Resp:
    def __init__(self, status=200, headers=None, chunks=None, text=None):
        self.status_code = status
        self.headers = headers or {}
        self._chunks = chunks or []
        self.text = text or ""

    def iter_content(self, chunk_size=1024 * 1024):  # noqa: ARG002
        yield from self._chunks


def test_download_audio_content_type_mismatch(monkeypatch):
    monkeypatch.setenv("ZYRA_DATA_DIR", "/tmp")

    def fake_request(
        method, url, headers=None, params=None, timeout=None, stream=False
    ):  # noqa: ARG001
        return _Resp(200, headers={"Content-Type": "audio/mpeg"}, chunks=[b"x"])

    import requests

    monkeypatch.setattr(requests, "request", fake_request)
    with pytest.raises(RuntimeError):
        download_audio(
            profile="limitless",
            since="2025-01-01T00:00:00Z",
            duration="PT30M",
        )


def test_download_audio_missing_time_args(monkeypatch):
    monkeypatch.setenv("ZYRA_DATA_DIR", "/tmp")
    with pytest.raises(ValueError):
        download_audio(profile="limitless")


def test_download_audio_duration_exceeded(monkeypatch):
    monkeypatch.setenv("ZYRA_DATA_DIR", "/tmp")
    with pytest.raises(ValueError):
        download_audio(
            profile="limitless",
            since="2025-01-01T00:00:00Z",
            duration="PT3H",
        )
