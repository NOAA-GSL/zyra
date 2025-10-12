# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import base64
from pathlib import Path
from unittest.mock import patch

from zyra.cli import main as cli_main


def _invoke_cli(args: list[str]) -> None:
    try:
        cli_main(args)
    except SystemExit as exc:  # CLI exits explicitly on success/failure
        assert int(getattr(exc, "code", 0) or 0) == 0


def test_acquire_http_token_via_env(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("EUMETSAT_TOKEN", "superSecretToken")

    captured: dict[str, dict[str, str] | None] = {}

    def fake_fetch(
        url: str, *, timeout: int = 60, headers: dict[str, str] | None = None
    ):
        captured["headers"] = headers
        return b"payload"

    with patch("zyra.connectors.backends.http.fetch_bytes", side_effect=fake_fetch):
        outfile = tmp_path / "out.bin"
        _invoke_cli(
            [
                "acquire",
                "http",
                "https://example.com/data.bin",
                "--header",
                "Accept: application/octet-stream",
                "--credential",
                "token=$EUMETSAT_TOKEN",
                "-o",
                str(outfile),
            ]
        )
    headers = captured["headers"] or {}
    assert headers.get("Authorization") == "Bearer superSecretToken"
    assert headers.get("Accept") == "application/octet-stream"
    assert (tmp_path / "out.bin").read_bytes() == b"payload"


def test_acquire_http_basic_auth_via_credentials(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("HTTP_PASSWORD", "p@ssWord")

    captured: dict[str, dict[str, str] | None] = {}

    def fake_fetch(
        url: str, *, timeout: int = 60, headers: dict[str, str] | None = None
    ):
        captured["headers"] = headers
        return b"ok"

    with patch("zyra.connectors.backends.http.fetch_bytes", side_effect=fake_fetch):
        outfile = tmp_path / "basic.bin"
        _invoke_cli(
            [
                "acquire",
                "http",
                "https://example.com/secure.bin",
                "--credential",
                "user=demo",
                "--credential",
                "password=$HTTP_PASSWORD",
                "-o",
                str(outfile),
            ]
        )
    headers = captured["headers"] or {}
    expected = base64.b64encode(b"demo:p@ssWord").decode("ascii")
    assert headers.get("Authorization") == f"Basic {expected}"
    assert (tmp_path / "basic.bin").read_bytes() == b"ok"


def test_acquire_ftp_credentials_aliases(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("FTP_PASS", "hunter2")

    captured: dict[str, str | None] = {}

    def fake_fetch(
        path: str,
        *,
        username: str | None = None,
        password: str | None = None,
    ) -> bytes:
        captured["username"] = username
        captured["password"] = password
        return b"ftp"

    with patch("zyra.connectors.backends.ftp.fetch_bytes", side_effect=fake_fetch):
        outfile = tmp_path / "ftp.bin"
        _invoke_cli(
            [
                "acquire",
                "ftp",
                "ftp://example.com/data.bin",
                "--user",
                "ftp-user",
                "--credential",
                "password=$FTP_PASS",
                "-o",
                str(outfile),
            ]
        )
    assert captured["username"] == "ftp-user"
    assert captured["password"] == "hunter2"
    assert (tmp_path / "ftp.bin").read_bytes() == b"ftp"


def test_acquire_ftp_list_uses_credentials(monkeypatch):
    monkeypatch.setenv("FTP_PASS", "hunter2")

    def fake_list(
        path: str,
        pattern=None,
        *,
        since=None,
        until=None,
        date_format=None,
        username=None,
        password=None,
    ):
        assert username == "ftp-user"
        assert password == "hunter2"
        return []

    with patch("zyra.connectors.backends.ftp.list_files", side_effect=fake_list):
        _invoke_cli(
            [
                "acquire",
                "ftp",
                "ftp://example.com/dir",
                "--list",
                "--user",
                "ftp-user",
                "--credential",
                "password=$FTP_PASS",
            ]
        )
