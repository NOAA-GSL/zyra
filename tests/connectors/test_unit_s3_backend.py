from unittest.mock import Mock, patch

import pytest
from zyra.connectors.backends import s3 as s3_backend


@pytest.fixture
def s3_client():
    with patch("zyra.connectors.backends.s3.boto3.client") as mock_boto3_client:
        yield mock_boto3_client


def test_upload_bytes(s3_client):
    """Test byte upload to S3 via upload_bytes."""
    mock_boto3_client = s3_client
    assert s3_backend.upload_bytes(b"data", "s3://test-bucket/remote/file.txt") is True
    # Ensure upload_file called with any temp path
    args, kwargs = mock_boto3_client.return_value.upload_file.call_args
    assert args[1] == "test-bucket"
    assert args[2] == "remote/file.txt"


def test_fetch_bytes(s3_client):
    """Test fetch bytes from S3 via get_object."""
    mock_boto3_client = s3_client
    body = Mock()
    body.read = lambda: b"hello"
    mock_boto3_client.return_value.get_object.return_value = {"Body": body}
    out = s3_backend.fetch_bytes("s3://test-bucket/remote/file.txt")
    assert out == b"hello"
