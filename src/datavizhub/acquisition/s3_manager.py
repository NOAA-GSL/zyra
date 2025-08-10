"""Amazon S3 data acquisition manager using boto3.

Implements :class:`~datavizhub.acquisition.base.DataAcquirer` for S3 buckets
with listing, fetching, and uploading support.
"""

import logging
from typing import Iterable, Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError

from datavizhub.acquisition.base import DataAcquirer


class S3Manager(DataAcquirer):
    CAPABILITIES = {"fetch", "upload", "list"}
    """Acquire objects from Amazon S3 buckets via boto3.

    This manager wraps :mod:`boto3`'s S3 client to standardize connecting,
    listing, and fetching S3 objects using the acquisition interface.

    Supported Protocols
    -------------------
    - ``s3://`` (buckets and keys)

    Parameters
    ----------
    access_key : str
        AWS access key ID.
    secret_key : str
        AWS secret access key.
    bucket_name : str
        Default S3 bucket to operate on.

    Examples
    --------
    Download a key to a local file::

        from datavizhub.acquisition.s3_manager import S3Manager

        s3 = S3Manager("AKIA...", "SECRET...", "my-bucket")
        s3.connect()
        s3.fetch("path/to/object.nc", "object.nc")
        s3.disconnect()
    """

    def __init__(self, access_key: str, secret_key: str, bucket_name: str) -> None:
        self.access_key = access_key
        self.secret_key = secret_key
        self.bucket_name = bucket_name
        self.s3_client = None

    def connect(self) -> None:
        """Create an S3 client using the provided credentials.

        Raises
        ------
        NoCredentialsError
            When credentials are not available or invalid.
        botocore.exceptions.BotoCoreError, botocore.exceptions.ClientError
            On other client initialization failures.
        """
        try:
            self.s3_client = boto3.client(
                "s3", aws_access_key_id=self.access_key, aws_secret_access_key=self.secret_key
            )
            logging.debug(f"Connection to {self.bucket_name} established.")
        except NoCredentialsError:
            logging.error("Credentials not available for AWS S3.")
            raise
        except (ClientError, BotoCoreError) as e:
            logging.error(f"Failed to connect S3 client: {e}")
            raise
        else:
            self._set_connected(True)

    def fetch(self, remote_path: str, local_filename: Optional[str] = None) -> bool:
        """Download an S3 key to a local file.

        Parameters
        ----------
        remote_path : str
            S3 key to download from ``bucket_name``.
        local_filename : str, optional
            Local destination filename. Defaults to the basename of the key.

        Returns
        -------
        bool
            ``True`` on success, ``False`` on failure.
        """
        if local_filename is None:
            local_filename = self._infer_local_name(remote_path)
        return self.download_file(remote_path, local_filename)

    def list_files(self, remote_path: Optional[str] = None) -> Optional[Iterable[str]]:
        """List object keys under a prefix in the bucket.

        Parameters
        ----------
        remote_path : str, optional
            Prefix to list. Defaults to all keys in the bucket.

        Returns
        -------
        list of str or None
            Keys found under the prefix, or ``None`` on error.
        """
        prefix = remote_path or ""
        try:
            if self.s3_client is None:
                self.connect()
            paginator = self.s3_client.get_paginator("list_objects_v2")
            page_iter = paginator.paginate(Bucket=self.bucket_name, Prefix=prefix)
            results: list[str] = []
            for page in page_iter:
                for obj in page.get("Contents", []):
                    key = obj.get("Key")
                    if key is not None:
                        results.append(key)
            return results
        except NoCredentialsError:
            logging.error("Credentials not available for AWS S3.")
            return None
        except (ClientError, BotoCoreError) as e:
            logging.error(f"Failed to list files in S3: {e}")
            return None

    # Backwards-compatible API
    def download_file(self, file_path: str, local_file_name: str) -> bool:
        """Compatibility method: download an S3 key.

        Parameters
        ----------
        file_path : str
            S3 key to download.
        local_file_name : str
            Local destination path.

        Returns
        -------
        bool
            ``True`` on success, ``False`` on failure.
        """
        try:
            if self.s3_client is None:
                self.connect()
            assert self.s3_client is not None
            self.s3_client.download_file(self.bucket_name, file_path, local_file_name)
            logging.info(f"{local_file_name} downloaded from {self.bucket_name}")
            return True
        except NoCredentialsError:
            logging.error("Credentials not available for AWS S3.")
            return False
        except (ClientError, BotoCoreError) as e:
            logging.error(f"Failed to download file from S3: {e}")
            return False

    def upload_file(self, file_path: str, s3_file_name: str) -> bool:
        """Upload a local file to the configured bucket.

        Parameters
        ----------
        file_path : str
            Local file path.
        s3_file_name : str
            Destination S3 key within ``bucket_name``.

        Returns
        -------
        bool
            ``True`` on success, ``False`` otherwise.
        """
        try:
            if self.s3_client is None:
                self.connect()
            assert self.s3_client is not None
            self.s3_client.upload_file(file_path, self.bucket_name, s3_file_name)
            logging.info(f"{s3_file_name} uploaded to {self.bucket_name}")
            return True
        except NoCredentialsError:
            logging.error("Credentials not available for AWS S3.")
            return False
        except (ClientError, BotoCoreError) as e:
            logging.error(f"Failed to upload file to S3: {e}")
            return False

    def disconnect(self) -> None:
        """Release the client reference.

        Notes
        -----
        boto3 clients do not require explicit shutdown. Setting the reference
        to ``None`` allows the instance to be reused or garbage-collected.
        """
        self.s3_client = None
        self._set_connected(False)

    def upload(self, local_path: str, remote_path: str) -> bool:
        """Standardized upload implementation delegating to :meth:`upload_file`."""
        return self.upload_file(local_path, remote_path)

    # ---- Optional operations -----------------------------------------------------------

    def exists(self, remote_path: str) -> bool:
        """Return True if the object exists in the bucket."""
        try:
            if self.s3_client is None:
                self.connect()
            assert self.s3_client is not None
            self.s3_client.head_object(Bucket=self.bucket_name, Key=remote_path)
            return True
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code")
            if code in ("404", "NoSuchKey", "NotFound"):
                return False
            logging.error(f"Failed to check existence in S3: {e}")
            return False
        except (BotoCoreError, NoCredentialsError) as e:
            logging.error(f"Failed to check existence in S3: {e}")
            return False

    def delete(self, remote_path: str) -> bool:
        """Delete an object from the bucket."""
        try:
            if self.s3_client is None:
                self.connect()
            assert self.s3_client is not None
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=remote_path)
            return True
        except (ClientError, BotoCoreError, NoCredentialsError) as e:
            logging.error(f"Failed to delete object from S3: {e}")
            return False

    def stat(self, remote_path: str):
        """Return basic metadata for an object (size, last modified, etag)."""
        try:
            if self.s3_client is None:
                self.connect()
            assert self.s3_client is not None
            resp = self.s3_client.head_object(Bucket=self.bucket_name, Key=remote_path)
            return {
                "size": int(resp.get("ContentLength", 0)),
                "last_modified": resp.get("LastModified"),
                "etag": resp.get("ETag"),
            }
        except (ClientError, BotoCoreError, NoCredentialsError) as e:
            logging.error(f"Failed to stat object in S3: {e}")
            return None
