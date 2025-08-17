"""Base interface for data acquisition in DataVizHub.

Defines :class:`DataAcquirer` plus common exceptions. Concrete managers (FTP,
HTTP, S3, Vimeo) implement the acquisition lifecycle: connect, fetch/list,
optional upload, and disconnect.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable, Iterable, Optional, Sequence, Tuple, List, Set


class DataAcquirer(ABC):
    """Abstract interface for acquiring data from remote sources.

    This abstract base class defines the minimal contract that any remote
    data source manager must implement to interoperate with the rest of the
    library. It standardizes how to connect to a source, fetch a resource to a
    local destination, enumerate available resources, and cleanly disconnect.

    Parameters
    ----------
    source : str
        Conceptual identifier of the remote source. Concrete implementations
        interpret this as needed (e.g., FTP host, S3 bucket, base URL, API).
        The value is typically provided through the concrete class constructor.
    destination : str
        Conceptual identifier for the local destination (e.g., local file
        path) used by :meth:`fetch`. This is usually supplied per call via
        ``local_filename`` and not stored on the instance.

    Notes
    -----
    - Implementations are responsible for their own connection client
      lifecycle (initialize in :meth:`connect`, cleanup in :meth:`disconnect`).
    - :meth:`list_files` may return ``None`` for sources that do not support
      listing (e.g., generic HTTP URLs).

    Examples
    --------
    Basic pipeline using a concrete manager::

        from datavizhub.acquisition.ftp_manager import FTPManager

        acq = FTPManager(host="ftp.example.com", username="anonymous", password="test@test.com")
        acq.connect()
        # Optional: enumerate files under a directory on the server
        for name in (acq.list_files("/pub") or []):
            print(name)
        # Fetch a file to the current working directory
        acq.fetch("/pub/data/file.txt", local_filename="file.txt")
        acq.disconnect()

    Selecting a manager dynamically by source type::

        def get_manager(config):
            if config["type"] == "s3":
                from datavizhub.acquisition.s3_manager import S3Manager
                return S3Manager(config["access_key"], config["secret_key"], config["bucket"])
            elif config["type"] == "ftp":
                from datavizhub.acquisition.ftp_manager import FTPManager
                return FTPManager(config["host"], config.get("port", 21), config["user"], config["pass"]) 
            else:
                from datavizhub.acquisition.http_manager import HTTPHandler
                return HTTPHandler()
        
        mgr = get_manager(cfg)
        mgr.connect()
        mgr.fetch(cfg["remote"], cfg.get("local"))
        mgr.disconnect()

    Using as a context manager::

        from datavizhub.acquisition.ftp_manager import FTPManager

        with FTPManager(host="ftp.example.com") as mgr:
            mgr.fetch("/pub/data/file.txt", local_filename="file.txt")
    """

    @abstractmethod
    def connect(self) -> None:
        """Establish a connection or initialize the client as needed.

        Notes
        -----
        Implementations should set up any underlying network clients or
        authenticate to remote services. This method should be idempotent and
        safe to call multiple times.
        """

    @abstractmethod
    def fetch(self, remote_path: str, local_filename: Optional[str] = None) -> bool:
        """Fetch a remote resource to a local file.

        Parameters
        ----------
        remote_path : str
            Remote identifier (e.g., URL, S3 key, FTP path) of the resource
            to download.
        local_filename : str, optional
            Local destination filename or path. If omitted, implementations
            may infer a name from ``remote_path``.

        Returns
        -------
        bool
            ``True`` on successful fetch, ``False`` on failure.
        """

    @abstractmethod
    def list_files(self, remote_path: Optional[str] = None) -> Optional[Iterable[str]]:
        """List files or resources available at the remote path.

        Parameters
        ----------
        remote_path : str, optional
            Remote path, prefix, or locator to enumerate. If omitted, the
            implementation may list a default location (e.g., current
            directory for FTP or entire bucket/prefix for S3).

        Returns
        -------
        Iterable of str or None
            Iterable of resource names/keys/paths. May return ``None`` if the
            operation is not supported by the source (e.g., HTTP URLs).
        """

    @abstractmethod
    def disconnect(self) -> None:
        """Tear down the connection or client resources if applicable.

        Notes
        -----
        Implementations should release sockets/clients and clear references so
        that instances are reusable or can be garbage-collected cleanly.
        """

    # ---- Extended standardized interface -------------------------------------------------

    @abstractmethod
    def upload(self, local_path: str, remote_path: str) -> bool:
        """Upload a local resource to the remote destination.

        Parameters
        ----------
        local_path : str
            Local filesystem path of the resource to upload.
        remote_path : str
            Remote destination identifier (e.g., FTP path, S3 key).

        Returns
        -------
        bool
            ``True`` on success, ``False`` on failure.
        """

    def fetch_many(self, items: Iterable[str], dest_dir: str) -> List[Tuple[str, bool]]:
        """Fetch multiple remote resources to a destination directory.

        Parameters
        ----------
        items : Iterable[str]
            Collection of remote paths/identifiers to fetch.
        dest_dir : str
            Local directory where files will be written.

        Returns
        -------
        list of (str, bool)
            A list of ``(remote_path, success)`` tuples.
        """
        results: List[Tuple[str, bool]] = []
        dest = Path(dest_dir)
        dest.mkdir(parents=True, exist_ok=True)
        for remote in items:
            local = dest / self._infer_local_name(remote)
            ok = self.fetch(remote, str(local))
            results.append((remote, ok))
        return results

    def exists(self, remote_path: str) -> bool:
        """Check whether a remote path exists.

        Notes
        -----
        Default implementation is not supported. Subclasses may override.

        Raises
        ------
        NotSupportedError
            Always raised for the default implementation.
        """
        raise NotSupportedError("exists() not supported for this source")

    def delete(self, remote_path: str) -> bool:
        """Delete a remote resource if supported.

        Notes
        -----
        Default implementation is not supported. Subclasses may override.

        Raises
        ------
        NotSupportedError
            Always raised for the default implementation.
        """
        raise NotSupportedError("delete() not supported for this source")

    def stat(self, remote_path: str):
        """Return remote metadata if supported.

        Notes
        -----
        Default implementation is not supported. Subclasses may override.

        Raises
        ------
        NotSupportedError
            Always raised for the default implementation.
        """
        raise NotSupportedError("stat() not supported for this source")

    # ---- Context manager ---------------------------------------------------------------

    def __enter__(self):  # pragma: no cover - simple convenience
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb):  # pragma: no cover - simple convenience
        self.disconnect()
        return False

    # ---- Introspection ----------------------------------------------------------------

    @property
    def connected(self) -> bool:
        """Whether the manager considers itself connected."""
        return getattr(self, "_connected", False)

    def _set_connected(self, value: bool) -> None:
        self._connected = bool(value)

    @property
    def capabilities(self) -> Set[str]:
        """Set of capability strings (e.g., {'fetch','upload','list'})."""
        caps = getattr(type(self), "CAPABILITIES", None)
        return set(caps) if caps else set()

    # ---- Protected helpers -------------------------------------------------------------

    @staticmethod
    def _infer_local_name(remote_path: str) -> str:
        """Infer a local filename from a remote path/URL/key."""
        return Path(remote_path).name

    @staticmethod
    def _ensure_parent_dir(pathlike: str | Path) -> None:
        """Ensure parent directory for a path exists."""
        p = Path(pathlike)
        if p.parent:
            p.parent.mkdir(parents=True, exist_ok=True)

    def _with_retries(
        self,
        func: Callable[[], None],
        attempts: int = 3,
        exceptions: Sequence[type[BaseException]] = (Exception,),
        before_retry: Optional[Callable[[int, BaseException], None]] = None,
    ) -> None:
        """Execute a callable with simple retry semantics.

        Parameters
        ----------
        func : Callable
            Function to call. If it raises one of ``exceptions`` the call
            will be retried up to ``attempts`` times.
        attempts : int, default=3
            Maximum number of attempts.
        exceptions : Sequence[type[BaseException]]
            Exception types that should trigger a retry.
        before_retry : Callable[[int, BaseException], None], optional
            Hook called before each retry with ``(attempt_index, exception)``.
        """
        last_exc: Optional[BaseException] = None
        for i in range(attempts):
            try:
                func()
                return
            except exceptions as e:  # type: ignore[misc]
                last_exc = e
                if i == attempts - 1:
                    raise
                if before_retry:
                    before_retry(i, e)
        if last_exc:
            raise last_exc


class AcquisitionError(Exception):
    """Base exception for acquisition-related errors."""


class NotSupportedError(AcquisitionError):
    """Raised when an operation is not supported by a manager."""
