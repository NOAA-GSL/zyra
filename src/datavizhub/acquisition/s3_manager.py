"""Amazon S3 data acquisition manager using boto3.

Implements :class:`~datavizhub.acquisition.base.DataAcquirer` for S3 buckets
with listing, fetching, and uploading support. Includes optional advanced
helpers for GRIB workflows and large file transfers.

Advanced Features
-----------------
- ``get_size(key)``: return object size (bytes) via ``head_object``.
- ``get_idx_lines(key, *, write_to=None, timeout=30, max_retries=3)``:
  fetch and parse a GRIB ``.idx`` file. Appends ``.idx`` to ``key`` unless an
  explicit ``.idx`` path is provided. Optionally writes the idx to disk.
- ``idx_to_byteranges(lines, search_regex)``: build HTTP Range strings from
  ``.idx`` content using a regex filter.
- ``get_chunks(key, chunk_size=500MB)``: compute contiguous byte ranges, using
  an inclusive final end byte (NODD style).
- ``download_byteranges(key, byte_ranges, *, max_workers=10, timeout=30)``:
  download multiple ranges in parallel and return concatenated bytes.
- ``list_files(prefix=None, pattern=None)``: list keys with optional regex
  filtering applied to full keys.
"""

import logging
from typing import Iterable, Optional, Iterable as _Iterable

import boto3
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError

from botocore import config as _botocore_config
from botocore.handlers import disable_signing as _disable_signing  # pragma: no cover - reference

from datavizhub.acquisition.base import DataAcquirer
from datavizhub.acquisition.grib_utils import (
    ensure_idx_path,
    parse_idx_lines,
    idx_to_byteranges as _idx_to_byteranges,
    compute_chunks as _compute_chunks,
    parallel_download_byteranges as _parallel_download_byteranges,
)


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
    access_key : str, optional
        AWS access key ID. Optional for public buckets or when using IAM roles.
    secret_key : str, optional
        AWS secret access key.
    bucket_name : str
        Default S3 bucket to operate on.
    unsigned : bool, default=False
        Disable request signing for public buckets using
        ``botocore.config.Config(signature_version=UNSIGNED)``.
    region_name : str, optional
        AWS region for the client. If omitted, botocore defaults apply.

    Examples
    --------
    Download a key to a local file::

        from datavizhub.acquisition.s3_manager import S3Manager

        s3 = S3Manager("AKIA...", "SECRET...", "my-bucket")
        s3.connect()
        s3.fetch("path/to/object.nc", "object.nc")
        s3.disconnect()

    Public bucket access (unsigned)::

        from datavizhub.acquisition.s3_manager import S3Manager
        s3 = S3Manager(None, None, bucket_name="noaa-hrrr-bdp-pds", unsigned=True)
        lines = s3.get_idx_lines("hrrr.20230801/conus/hrrr.t00z.wrfsfcf00.grib2")
        ranges = s3.idx_to_byteranges(lines, r"(:TMP:surface|:PRATE:surface)")
        blob = s3.download_byteranges("hrrr.20230801/conus/hrrr.t00z.wrfsfcf00.grib2", ranges.keys())
    """

    def __init__(
        self,
        access_key: Optional[str],
        secret_key: Optional[str],
        bucket_name: str,
        unsigned: bool = False,
        region_name: Optional[str] = None,
    ) -> None:
        """Initialize the S3 manager.

        Parameters
        ----------
        access_key : str, optional
            AWS access key ID. Optional for public buckets or when using IAM roles.
        secret_key : str, optional
            AWS secret access key.
        bucket_name : str
            Default S3 bucket to operate on.
        unsigned : bool, default=False
            When True, disable request signing for public buckets using
            ``botocore.config.Config(signature_version=UNSIGNED)``.
        region_name : str, optional
            AWS region for the client. If omitted, botocore's default resolution is used.
        """
        self.access_key = access_key
        self.secret_key = secret_key
        self.bucket_name = bucket_name
        self.unsigned = bool(unsigned)
        self.region_name = region_name
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
            client_kwargs = {}
            if self.region_name:
                client_kwargs["region_name"] = self.region_name
            if self.unsigned:
                # Use UNSIGNED config rather than event-hook based disabling
                from botocore import UNSIGNED

                client_kwargs["config"] = _botocore_config.Config(signature_version=UNSIGNED)
            else:
                # Provide credentials if explicitly supplied; otherwise rely on
                # environment/instance metadata resolution.
                if self.access_key:
                    client_kwargs["aws_access_key_id"] = self.access_key
                if self.secret_key:
                    client_kwargs["aws_secret_access_key"] = self.secret_key

            self.s3_client = boto3.client("s3", **client_kwargs)
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

    def list_files(self, remote_path: Optional[str] = None, pattern: Optional[str] = None) -> Optional[Iterable[str]]:
        """List object keys under a prefix in the bucket with optional regex filter.

        Parameters
        ----------
        remote_path : str, optional
            Prefix to list. Defaults to all keys in the bucket.
        pattern : str, optional
            Regular expression applied to full keys using :func:`re.search`.
            If provided, only matching keys are returned.

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
            if pattern:
                import re

                rx = re.compile(pattern)
                results = [k for k in results if rx.search(k)]
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

    # ---- Advanced features: GRIB and ranged downloads ---------------------------------

    def get_size(self, key: str) -> Optional[int]:
        """Return the size in bytes for a given S3 object key.

        Returns
        -------
        int or None
            Content length if available, else ``None``.
        """
        try:
            if self.s3_client is None:
                self.connect()
            assert self.s3_client is not None
            resp = self.s3_client.head_object(Bucket=self.bucket_name, Key=key)
            return int(resp.get("ContentLength"))
        except (ClientError, BotoCoreError, NoCredentialsError):
            return None

    def get_idx_lines(
        self,
        key: str,
        *,
        timeout: int = 30,
        max_retries: int = 3,
        write_to: Optional[str] = None,
    ) -> Optional[list[str]]:
        """Fetch and parse the GRIB index (.idx) for ``key``.

        Parameters
        ----------
        key : str
            GRIB object key, or an explicit ``.idx`` path.
        write_to : str, optional
            If provided, write the idx text to ``write_to`` (appends ``.idx``
            if not present).
        timeout : int, default=30
            Per-request timeout (seconds). Included for API consistency.
        max_retries : int, default=3
            Simple retry count on transient errors.

        Notes
        -----
        Appends ``.idx`` to ``key`` unless an explicit ``.idx`` path is provided.
        """
        idx_key = ensure_idx_path(key)

        def _fetch(k: str) -> bytes:
            attempts = {"count": 0}

            def _do():
                if self.s3_client is None:
                    self.connect()
                assert self.s3_client is not None
                resp = self.s3_client.get_object(Bucket=self.bucket_name, Key=k)
                return resp["Body"].read()

            # simple retry
            while attempts["count"] < max_retries:
                try:
                    return _do()
                except Exception:
                    attempts["count"] += 1
            raise

        try:
            payload = _fetch(idx_key)
        except Exception:
            return None
        lines = parse_idx_lines(payload)
        if write_to:
            try:
                with open(write_to if write_to.endswith(".idx") else f"{write_to}.idx", "w", encoding="utf8") as f:
                    f.write("\n".join(lines))
            except Exception:
                pass
        return lines

    def idx_to_byteranges(self, lines: list[str], search_str: str) -> dict[str, str]:
        """Wrapper for :func:`grib_utils.idx_to_byteranges` using regex filtering."""
        return _idx_to_byteranges(lines, search_str)

    def get_chunks(self, key: str, chunk_size: int = 500 * 1024 * 1024) -> list[str]:
        """Compute contiguous chunk ranges for an S3 object.

        The final range uses the file size as the inclusive end byte.
        """
        size = self.get_size(key)
        if size is None:
            return []
        return _compute_chunks(size, chunk_size)

    def download_byteranges(
        self,
        key: str,
        byte_ranges: _Iterable[str],
        *,
        max_workers: int = 10,
        timeout: int = 30,
    ) -> bytes:
        """Download multiple byte ranges from an object and concatenate results.

        Parameters
        ----------
        key : str
            Object key within the configured bucket.
        byte_ranges : Iterable[str]
            Iterable of Range header values (e.g., ``"bytes=0-99"``).
        max_workers : int, default=10
            Maximum parallel workers for ranged requests.
        timeout : int, default=30
            Timeout per ranged request (seconds).
        Returns
        -------
        bytes
            Concatenated payload of the requested ranges, preserving the order
            of the input ``byte_ranges``.
        """

        def _ranged_get(k: str, range_header: str) -> bytes:
            if self.s3_client is None:
                self.connect()
            assert self.s3_client is not None
            resp = self.s3_client.get_object(Bucket=self.bucket_name, Key=k, Range=range_header)
            return resp["Body"].read()

        return _parallel_download_byteranges(_ranged_get, key, byte_ranges, max_workers=max_workers)

    def list_files_filtered(self, prefix: Optional[str] = None, pattern: Optional[str] = None) -> list[str]:
        """Deprecated alias for ``list_files(prefix, pattern)``."""
        return list(self.list_files(prefix, pattern) or [])

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
