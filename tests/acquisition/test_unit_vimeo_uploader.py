from unittest.mock import patch

import pytest
from datavizhub.acquisition.vimeo_manager import VimeoManager


@pytest.fixture()
def vimeo_uploader():
    """Fixture to provide a mocked VimeoUploader instance."""
    client_id = "client_id"
    client_secret = "client_secret"
    access_token = "access_token"

    with patch("vimeo.VimeoClient") as mock_vimeo_client:
        uploader = VimeoManager(client_id, client_secret, access_token)
        yield uploader, mock_vimeo_client


def test_upload_video(vimeo_uploader):
    """Test video upload to Vimeo."""
    uploader, mock_vimeo_client = vimeo_uploader
    file_path = "/path/to/video.mp4"
    video_name = "Test Video"

    mock_vimeo_client.return_value.upload.return_value = {"uri": "/videos/12345"}

    result = uploader.upload_video(file_path, video_name)

    mock_vimeo_client.return_value.upload.assert_called_with(
        file_path, data={"name": video_name}
    )
    assert result == "/videos/12345"

