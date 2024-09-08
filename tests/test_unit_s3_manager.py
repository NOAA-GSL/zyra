from unittest.mock import patch

import pytest
from datavizhub.data_transfer.S3Manager import S3Manager


@pytest.fixture()
def s3_manager():
    access_key = "ACCESS_KEY"
    secret_key = "SECRET_KEY"
    bucket_name = "test-bucket"
    with patch("boto3.client") as mock_boto3_client:
        manager = S3Manager(access_key, secret_key, bucket_name)
        yield manager, mock_boto3_client


def test_upload_file(s3_manager):
    """Test file upload to S3."""
    manager, mock_boto3_client = s3_manager
    local_file_path = "/path/to/local/file.txt"
    remote_file_path = "remote/file.txt"

    manager.upload_file(local_file_path, remote_file_path)

    mock_boto3_client.return_value.upload_file.assert_called_with(
        local_file_path, manager.bucket_name, remote_file_path
    )


def test_download_file(s3_manager):
    """Test file download from S3."""
    manager, mock_boto3_client = s3_manager
    local_file_path = "/path/to/local/file.txt"
    remote_file_path = "remote/file.txt"

    manager.download_file(remote_file_path, local_file_path)

    mock_boto3_client.return_value.download_file.assert_called_with(
        manager.bucket_name, remote_file_path, local_file_path
    )


# Add more tests for other methods...
