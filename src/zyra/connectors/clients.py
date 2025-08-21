"""Optional OO connector clients.

These thin wrappers provide a small amount of state (e.g., host or bucket)
and delegate to the functional backends for each operation. They are useful
when you want to reuse configuration across several calls in a script while
keeping the core API functional and composable.
"""

from __future__ import annotations

from typing import Iterable

from zyra.connectors.backends import ftp as ftp_backend
from zyra.connectors.backends import s3 as s3_backend

from .base import Connector


class FTPConnector(Connector):
    """Thin OO wrapper around the FTP backend for convenience.

    Stores host/credentials and exposes methods that accept path-only inputs.
    All methods delegate to functional backends.
    """

    CAPABILITIES = {"fetch", "upload", "list"}

    def __init__(
        self,
        host: str,
        port: int = 21,
        username: str = "anonymous",
        password: str = "test@test.com",
        timeout: int = 30,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.timeout = timeout

    def _url(self, path: str) -> str:
        s = path.lstrip("/")
        return f"ftp://{self.host}/{s}"

    # ---- Simple operations -----------------------------------------------------------

    def fetch_bytes(self, path: str) -> bytes:
        """Fetch a remote file from this FTP host as bytes."""
        return ftp_backend.fetch_bytes(self._url(path))

    def upload_bytes(self, data: bytes, path: str) -> bool:
        """Upload bytes to a remote path on this FTP host."""
        return ftp_backend.upload_bytes(data, self._url(path))

    def list_files(
        self,
        remote_dir: str,
        pattern: str | None = None,
        *,
        since: str | None = None,
        until: str | None = None,
        date_format: str | None = None,
    ) -> list[str] | None:
        """List files under a remote directory with optional filters."""
        return ftp_backend.list_files(
            self._url(remote_dir),
            pattern=pattern,
            since=since,
            until=until,
            date_format=date_format,
        )

    def exists(self, path: str) -> bool:
        """Return True if the path exists on this FTP host."""
        return ftp_backend.exists(self._url(path))

    def delete(self, path: str) -> bool:
        """Delete a remote path on this FTP host."""
        return ftp_backend.delete(self._url(path))

    def stat(self, path: str):
        """Return minimal metadata mapping for a remote path."""
        return ftp_backend.stat(self._url(path))

    def sync_directory(
        self,
        remote_dir: str,
        local_dir: str,
        *,
        pattern: str | None = None,
        since: str | None = None,
        until: str | None = None,
        date_format: str | None = None,
    ) -> None:
        """Mirror a remote directory on this FTP host to a local directory."""
        return ftp_backend.sync_directory(
            self._url(remote_dir),
            local_dir,
            pattern=pattern,
            since=since,
            until=until,
            date_format=date_format,
        )


class S3Connector(Connector):
    """Thin OO wrapper around the S3 backend for convenience.

    Stores bucket configuration and exposes familiar object operations.
    """

    CAPABILITIES = {"fetch", "upload", "list"}

    def __init__(self, bucket: str, *, unsigned: bool = False) -> None:
        self.bucket = bucket
        self.unsigned = bool(unsigned)

    def _url(self, key: str) -> str:
        s = key.lstrip("/")
        return f"s3://{self.bucket}/{s}"

    def fetch_bytes(self, key: str) -> bytes:
        """Fetch object bytes from the configured bucket."""
        return s3_backend.fetch_bytes(self._url(key), unsigned=self.unsigned)

    def upload_bytes(self, data: bytes, key: str) -> bool:
        """Upload bytes as an object to the configured bucket."""
        return s3_backend.upload_bytes(data, self._url(key))

    def list_files(
        self,
        prefix: str | None = None,
        *,
        pattern: str | None = None,
        since: str | None = None,
        until: str | None = None,
        date_format: str | None = None,
    ) -> list[str] | None:
        """List keys under an optional prefix with optional filters."""
        url = self._url(prefix) if prefix else f"s3://{self.bucket}/"
        return s3_backend.list_files(
            url,
            pattern=pattern,
            since=since,
            until=until,
            date_format=date_format,
        )

    def exists(self, key: str) -> bool:
        """Return True if the object exists in the configured bucket."""
        return s3_backend.exists(self._url(key))

    def delete(self, key: str) -> bool:
        """Delete an object from the configured bucket."""
        return s3_backend.delete(self._url(key))

    def stat(self, key: str):
        """Return basic metadata mapping for an object in the bucket."""
        return s3_backend.stat(self._url(key))

    # GRIB helpers
    def get_idx_lines(self, key: str) -> list[str]:
        """Fetch and parse the GRIB ``.idx`` for an object in the bucket."""
        return s3_backend.get_idx_lines(self._url(key), unsigned=self.unsigned)

    def download_byteranges(
        self, key: str, byte_ranges: Iterable[str], *, max_workers: int = 10
    ) -> bytes:
        """Download multiple byte ranges and concatenate them in order."""
        return s3_backend.download_byteranges(
            self._url(key),
            None,
            byte_ranges,
            unsigned=self.unsigned,
            max_workers=max_workers,
        )
