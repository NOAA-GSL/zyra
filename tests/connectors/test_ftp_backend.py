from unittest.mock import patch

from datavizhub.connectors.backends import ftp as ftp_backend


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

    with patch("datavizhub.connectors.backends.ftp.FTP", _FTP):
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

    with patch("datavizhub.connectors.backends.ftp.FTP", _FTP2):
        ftp_backend.sync_directory("ftp://host/dir", str(d), clean_zero_bytes=True)
        assert not fz.exists()
