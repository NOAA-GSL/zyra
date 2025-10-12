# SPDX-License-Identifier: Apache-2.0
import warnings
from unittest.mock import patch

import pytest

from zyra.connectors.backends import ftp as ftp_backend


def test_parse_ftp_path_warns_on_explicit_override():
    with pytest.warns(
        UserWarning, match="username overrides username embedded in the URL"
    ):
        host, path, user, pwd = ftp_backend.parse_ftp_path(
            "ftp://urluser:urlpass@ftp.example.com/path/file.bin",
            username="explicit",
        )
    assert host == "ftp.example.com"
    assert path == "path/file.bin"
    assert user == "explicit"
    assert pwd == "urlpass"


def test_parse_ftp_path_warns_on_password_override():
    with pytest.warns(UserWarning, match="password overrides credentials"):
        host, path, user, pwd = ftp_backend.parse_ftp_path(
            "ftp://urluser:urlpass@ftp.example.com/path/file.bin",
            password="newpass",
        )
    assert pwd == "newpass"
    assert user == "urluser"


def test_parse_ftp_path_uses_url_credentials_when_explicit_missing():
    host, path, user, pwd = ftp_backend.parse_ftp_path(
        "ftp://urluser:urlpass@ftp.example.com/path/file.bin"
    )
    assert (host, path, user, pwd) == (
        "ftp.example.com",
        "path/file.bin",
        "urluser",
        "urlpass",
    )


def test_parse_ftp_path_no_warning_when_values_match():
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        host, path, user, pwd = ftp_backend.parse_ftp_path(
            "ftp://urluser:urlpass@ftp.example.com/path/file.bin",
            username="urluser",
            password="urlpass",
        )
    assert not captured
    assert (user, pwd) == ("urluser", "urlpass")


def test_list_files_with_date_filter_and_credentials(monkeypatch):
    # Mock ftplib FTP.nlst
    class _FTP:
        def __init__(self, timeout=30):
            self.timeout = timeout

        def connect(self, host):
            return None

        def login(self, user=None, passwd=None):
            return None

        def set_pasv(self, flag):
            return None

        def cwd(self, d):
            return None

        def nlst(self):
            return [
                "/SOS/DroughtRisk_Weekly/DroughtRisk_Weekly_20240101.png",
                "/SOS/DroughtRisk_Weekly/DroughtRisk_Weekly_20250101.png",
            ]

    with patch("zyra.connectors.backends.ftp.FTP", _FTP):
        names = ftp_backend.list_files(
            "ftp://anonymous:test%40example.com@ftp.host/SOS/DroughtRisk_Weekly",
            pattern=r"DroughtRisk_Weekly_(\d{8})\.png",
            since="2024-06-01T00:00:00",
            date_format="%Y%m%d",
        )
        assert names and all("2025" in n for n in names)


def test_sync_directory_cleans_zero_byte(tmp_path):
    # Create a zero-byte file and verify it gets removed with clean_zero_bytes
    d = tmp_path / "frames"
    d.mkdir()
    fz = d / "z.png"
    fz.write_bytes(b"")

    class _FTP2:
        def __init__(self, timeout=30):
            pass

        def connect(self, host):
            return None

        def login(self, user=None, passwd=None):
            return None

        def set_pasv(self, flag):
            return None

        def cwd(self, d):
            return None

        def nlst(self):
            return ["a.png"]

        def retrbinary(self, cmd, cb):
            cb(b"x")

        def quit(self):
            return None

    with patch("zyra.connectors.backends.ftp.FTP", _FTP2):
        ftp_backend.sync_directory("ftp://host/dir", str(d), clean_zero_bytes=True)
        assert not fz.exists()
