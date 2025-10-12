# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from zyra.cli import main as cli_main


def _invoke_cli(args: list[str]) -> None:
    try:
        cli_main(args)
    except SystemExit as exc:  # CLI exits explicitly
        assert int(getattr(exc, "code", 0) or 0) == 0


def test_decimate_post_headers_and_credentials(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("EXPORT_TOKEN", "secret")
    data_path = tmp_path / "body.json"
    data_path.write_text("{}", encoding="utf-8")

    captured: dict[str, dict[str, str] | None] = {}

    def fake_post(url, data, *, timeout=60, content_type=None, headers=None):  # noqa: ARG001
        captured["headers"] = headers
        assert url == "https://example.com/upload"
        assert content_type == "application/json"
        return 200

    with patch("zyra.connectors.backends.http.post_bytes", side_effect=fake_post):
        _invoke_cli(
            [
                "decimate",
                "post",
                "https://example.com/upload",
                "-i",
                str(data_path),
                "--content-type",
                "application/json",
                "--header",
                "Accept: application/json",
                "--credential",
                "token=$EXPORT_TOKEN",
                "--auth",
                "bearer:$EXPORT_TOKEN",
            ]
        )
    headers = captured["headers"] or {}
    assert headers.get("Authorization") == "Bearer secret"
    assert headers.get("Accept") == "application/json"


def test_decimate_ftp_credentials(monkeypatch, tmp_path: Path):
    data_path = tmp_path / "file.bin"
    data_path.write_bytes(b"payload")
    monkeypatch.setenv("FTP_PASS", "hunter2")

    captured: dict[str, str | None] = {}

    def fake_upload(data, path, *, username=None, password=None):  # noqa: ARG001
        captured["username"] = username
        captured["password"] = password
        assert path == "ftp://example.com/data.bin"
        assert data == b"payload"
        return True

    with patch("zyra.connectors.backends.ftp.upload_bytes", side_effect=fake_upload):
        _invoke_cli(
            [
                "decimate",
                "ftp",
                "ftp://example.com/data.bin",
                "-i",
                str(data_path),
                "--user",
                "demo",
                "--credential",
                "password=$FTP_PASS",
            ]
        )
    assert captured["username"] == "demo"
    assert captured["password"] == "hunter2"


def test_decimate_vimeo_credentials(monkeypatch, tmp_path):
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"video")
    monkeypatch.setenv("VIMEO_TOKEN", "topsecret")

    captured: dict[str, str | None] = {}

    def fake_upload(
        path: str,
        *,
        name: str | None = None,
        description: str | None = None,
        token: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> str:  # noqa: ARG001
        captured["path"] = path
        captured["name"] = name
        captured["token"] = token
        captured["client_id"] = client_id
        captured["client_secret"] = client_secret
        return "https://vimeo.com/123"

    def fake_update_desc(
        uri: str,
        text: str,
        *,
        token: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> str:  # noqa: ARG001
        captured["desc_token"] = token
        return uri

    monkeypatch.setenv("VIMEO_ACCESS_TOKEN", "")
    monkeypatch.setenv("VIMEO_CLIENT_ID", "")
    monkeypatch.setenv("VIMEO_CLIENT_SECRET", "")

    from unittest.mock import patch

    with patch(
        "zyra.connectors.backends.vimeo.upload_path", side_effect=fake_upload
    ), patch(
        "zyra.connectors.backends.vimeo.update_description",
        side_effect=fake_update_desc,
    ):
        _invoke_cli(
            [
                "disseminate",
                "vimeo",
                "-i",
                str(video_path),
                "--name",
                "Demo",
                "--description",
                "Short",
                "--credential",
                "access_token=$VIMEO_TOKEN",
                "--credential",
                "client_id=myid",
                "--credential",
                "client_secret=mysecret",
            ]
        )

    assert captured["path"] == str(video_path)
    assert captured["name"] == "Demo"
    assert captured["token"] == "topsecret"
    assert captured["client_id"] == "myid"
    assert captured["client_secret"] == "mysecret"
