from unittest.mock import patch

from zyra.cli import main as cli_main


def test_acquire_http_since_period_list(monkeypatch):
    with patch("zyra.connectors.backends.http.list_files") as m_list:
        m_list.return_value = []
        try:
            cli_main(
                [
                    "acquire",
                    "http",
                    "https://example.com/dir/",
                    "--list",
                    "--since-period",
                    "P1D",
                ]
            )
        except SystemExit as e:
            assert int(getattr(e, "code", 0) or 0) == 0


def test_acquire_ftp_since_period_list(monkeypatch):
    with patch("zyra.connectors.backends.ftp.list_files") as m_list:
        m_list.return_value = []
        try:
            cli_main(
                [
                    "acquire",
                    "ftp",
                    "ftp://host/path",
                    "--list",
                    "--since-period",
                    "P7D",
                    "--date-format",
                    "%Y%m%d",
                ]
            )
        except SystemExit as e:
            assert int(getattr(e, "code", 0) or 0) == 0


def test_acquire_s3_since_period_list(monkeypatch):
    with patch("zyra.connectors.backends.s3.list_files") as m_list:
        m_list.return_value = []
        try:
            cli_main(
                [
                    "acquire",
                    "s3",
                    "--url",
                    "s3://bucket/prefix/",
                    "--list",
                    "--since-period",
                    "P6M",
                ]
            )
        except SystemExit as e:
            assert int(getattr(e, "code", 0) or 0) == 0
