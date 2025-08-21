from unittest.mock import patch

import pytest
from zyra.connectors.backends import ftp as ftp_backend


@pytest.fixture
def ftp_env():
    """Provide patched FTP class for backend functions."""
    with patch("zyra.connectors.backends.ftp.FTP") as mock_ftp:
        yield mock_ftp


def test_exists_and_stat_and_delete(ftp_env):
    mock_ftp_class = ftp_env
    mock_ftp = mock_ftp_class.return_value

    mock_ftp.nlst.return_value = ["file.txt", "other.txt"]
    mock_ftp.size.return_value = 123

    assert ftp_backend.exists("ftp://ftp.example.com/dir/file.txt") is True
    meta = ftp_backend.stat("ftp://ftp.example.com/dir/file.txt")
    assert meta == {"size": 123}

    assert ftp_backend.delete("ftp://ftp.example.com/dir/file.txt") is True
    mock_ftp.delete.assert_called_with("file.txt")

    mock_ftp.nlst.return_value = ["other.txt"]
    assert ftp_backend.exists("ftp://ftp.example.com/dir/file.txt") is False
