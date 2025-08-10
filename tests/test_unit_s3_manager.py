from unittest.mock import patch

import pytest
from datavizhub.acquisition.s3_manager import S3Manager
from botocore.exceptions import ClientError


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


def test_exists_delete_stat(s3_manager):
    """Test exists/delete/stat on S3Manager using mocked boto3 client."""
    manager, mock_boto3_client = s3_manager
    client = mock_boto3_client.return_value

    # exists True
    client.head_object.return_value = {"ContentLength": 10}
    assert manager.exists("key.txt") is True
    client.head_object.assert_called_with(Bucket=manager.bucket_name, Key="key.txt")

    # exists False via ClientError 404
    error_response = {"Error": {"Code": "404", "Message": "Not Found"}}
    client.head_object.side_effect = ClientError(error_response, "HeadObject")
    assert manager.exists("missing.txt") is False

    # delete
    client.delete_object.return_value = {}
    assert manager.delete("key.txt") is True
    client.delete_object.assert_called_with(Bucket=manager.bucket_name, Key="key.txt")

    # stat
    client.head_object.side_effect = None
    client.head_object.return_value = {
        "ContentLength": 42,
        "LastModified": "ts",
        "ETag": "etag",
    }
    meta = manager.stat("key.txt")
    assert meta == {"size": 42, "last_modified": "ts", "etag": "etag"}
