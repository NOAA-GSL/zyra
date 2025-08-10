from unittest.mock import patch

import pytest
from datavizhub.acquisition.ftp_manager import FTPManager


@pytest.fixture()
def ftp_manager():
    """Fixture to provide a mocked FTPManager instance."""
    ftp_host = "ftp.example.com"
    ftp_port = 21
    ftp_username = "anonymous"
    ftp_password = "test@test.com"

    with patch("datavizhub.acquisition.ftp_manager.FTP") as mock_ftp:
        manager = FTPManager(ftp_host, ftp_port, ftp_username, ftp_password)
        yield manager, mock_ftp


def test_connect(ftp_manager):
    """Test connection to the FTP server."""
    manager, mock_ftp_class = ftp_manager
    mock_ftp = mock_ftp_class.return_value

    manager.connect()

    # FTP() constructor should be called with no args
    mock_ftp_class.assert_called_once()

    # connect() should be called with host and port
    mock_ftp.connect.assert_called_once_with("ftp.example.com", 21)

    # login() should be called with user/pass
    mock_ftp.login.assert_called_once_with(
        user="anonymous", passwd="test@test.com"
    )


@pytest.mark.skip()
def test_disconnect(ftp_manager):
    """Test disconnection from the FTP server."""
    manager, mock_ftp = ftp_manager
    manager.disconnect()
    mock_ftp.return_value.quit.assert_called()


# Additional tests...


def test_exists_and_stat_and_delete(ftp_manager):
    """Test exists/stat/delete helpers on FTPManager."""
    manager, mock_ftp_class = ftp_manager
    mock_ftp = mock_ftp_class.return_value

    # Simulate directory listing containing the file
    mock_ftp.nlst.return_value = ["file.txt", "other.txt"]
    mock_ftp.size.return_value = 123

    assert manager.exists("dir/file.txt") is True
    mock_ftp.cwd.assert_any_call("dir")

    meta = manager.stat("dir/file.txt")
    assert meta == {"size": 123}

    # Delete should call FTP.delete on the filename only
    assert manager.delete("dir/file.txt") is True
    mock_ftp.delete.assert_called_with("file.txt")

    # Now simulate a missing file
    mock_ftp.nlst.return_value = ["other.txt"]
    assert manager.exists("dir/file.txt") is False
