# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from zyra.api.mcp_tools.audio import download_audio


class _Resp:
    def __init__(self, status=200, headers=None, chunks=None, text=None):
        self.status_code = status
        self.headers = headers or {}
        self._chunks = chunks or []
        self.text = text or ""

    def iter_content(self, chunk_size=1024 * 1024):  # noqa: ARG002
        yield from self._chunks


def test_mcp_download_audio_limitless_since_duration(monkeypatch, tmp_path):
    monkeypatch.setenv("ZYRA_DATA_DIR", str(tmp_path))

    def fake_request(
        method, url, headers=None, params=None, timeout=None, stream=False
    ):  # noqa: ARG001
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

    res = download_audio(
        profile="limitless",
        since="2025-01-01T00:00:00Z",
        duration="PT30M",
        audio_source="pendant",
        output_dir="tests",
    )
    path_rel = res.get("path")
    assert isinstance(path_rel, str) and path_rel.endswith("audio.ogg")
    full = tmp_path / path_rel
    assert full.exists() and full.read_bytes() == b"abcdef"


def test_download_audio_credentials_override(monkeypatch, tmp_path):
    from zyra.api.mcp_tools.audio import download_audio

    monkeypatch.setenv("ZYRA_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("LIMITLESS_API_KEY", raising=False)
    monkeypatch.setenv("MY_LIMITLESS_TOKEN", "override")

    captured = {}

    def fake_request(
        method, url, headers=None, params=None, timeout=None, stream=False
    ):  # noqa: ARG001
        captured["headers"] = dict(headers or {})
        return _Resp(
            200,
            headers={
                "Content-Type": "audio/ogg",
                "Content-Disposition": 'attachment; filename="clip.ogg"',
            },
            chunks=[b"data"],
        )

    import requests

    monkeypatch.setattr(requests, "request", fake_request)

    res = download_audio(
        profile="limitless",
        since="2025-01-01T00:00:00Z",
        duration="PT5M",
        audio_source="pendant",
        output_dir="downloads",
        credentials={"token": "$MY_LIMITLESS_TOKEN"},
    )

    assert res["path"].endswith("clip.ogg")
    assert captured["headers"].get("X-API-Key") == "override"
