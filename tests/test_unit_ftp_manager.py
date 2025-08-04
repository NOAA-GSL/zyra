from unittest.mock import patch

import pytest
from datavizhub.datatransfer.FTPManager import FTPManager


@pytest.fixture()
def ftp_manager():
    """Fixture to provide a mocked FTPManager instance."""
    ftp_host = "public.sos.noaa.gov"
    ftp_port = 21
    ftp_username = "anonymous"
    ftp_password = "sosrt@noaa.gov"

    with patch("datavizhub.datatransfer.FTPManager.FTP") as mock_ftp:
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
    mock_ftp.connect.assert_called_once_with("public.sos.noaa.gov", 21)

    # login() should be called with user/pass
    mock_ftp.login.assert_called_once_with(
        user="anonymous", passwd="sosrt@noaa.gov"
    )


@pytest.mark.skip()
def test_disconnect(ftp_manager):
    """Test disconnection from the FTP server."""
    manager, mock_ftp = ftp_manager
    manager.disconnect()
    mock_ftp.return_value.quit.assert_called()


# Additional tests...
