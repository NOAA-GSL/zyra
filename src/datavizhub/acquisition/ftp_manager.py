"""FTP data acquisition manager.

Implements :class:`~datavizhub.acquisition.base.DataAcquirer` for FTP servers
with support for listing, fetching, and uploading files. Adds optional helpers
for GRIB ``.idx`` subsetting and FTP byte-range downloads via ``REST``.

Advanced Features
-----------------
- ``get_size(path)``: use ``SIZE`` to return remote size in bytes.
- ``get_idx_lines(path, *, write_to=None, timeout=30, max_retries=3)``:
  fetch and parse a GRIB ``.idx`` (appends ``.idx`` unless explicit).
- ``idx_to_byteranges(lines, search_regex)``: regex to Range headers.
- ``get_chunks(path, chunk_size=500MB)``: compute contiguous ranges.
- ``download_byteranges(path, byte_ranges, *, max_workers=10, timeout=30)``:
  parallel range downloads using one short-lived FTP connection per range to
  ensure thread safety; concatenates the results in input order.
"""

import logging
import re
from io import BytesIO
from pathlib import Path
from typing import Iterable, Optional, Iterable as _Iterable, Tuple, List, Dict

from ftplib import FTP, error_perm, error_temp

from datavizhub.acquisition.base import DataAcquirer, NotSupportedError
from datavizhub.acquisition.grib_utils import (
    ensure_idx_path,
    parse_idx_lines,
    idx_to_byteranges as _idx_to_byteranges,
    compute_chunks as _compute_chunks,
    parallel_download_byteranges as _parallel_download_byteranges,
)
from datavizhub.utils.date_manager import DateManager


class FTPManager(DataAcquirer):
    """Acquire files from FTP servers using passive mode.

    This manager wraps Python's :mod:`ftplib` to provide reliable FTP
    interactions including connecting, listing directories, and downloading
    files. It standardizes the acquisition interface via
    :class:`~datavizhub.acquisition.base.DataAcquirer` and preserves the
    original convenience methods used elsewhere in the project.

    Supported Protocols
    -------------------
    - ``ftp://``

    Parameters
    ----------
    host : str
        FTP server hostname or IP address.
    port : int, default=21
        FTP server port.
    username : str, default="anonymous"
        Username for authentication.
    password : str, default="test@test.com"
        Password for authentication.
    timeout : int, default=30
        Socket timeout in seconds.

    Examples
    --------
    Download a file from an FTP directory::

        from datavizhub.acquisition.ftp_manager import FTPManager

        ftp = FTPManager("ftp.example.com")
        ftp.connect()
        ftp.fetch("/pub/some/file.txt", "file.txt")
        ftp.disconnect()
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
        self.ftp: Optional[FTP] = None

    def connect(self) -> None:
        """Connect to the FTP server and enable passive mode.

        Raises
        ------
        Exception
            Propagates any underlying connection or authentication failure.
        """
        try:
            self.ftp = FTP(timeout=self.timeout)
            self.ftp.connect(self.host, self.port)
            self.ftp.login(user=self.username, passwd=self.password)
            self.ftp.set_pasv(True)
            logging.info(f"Connected to FTP server: {self.host}")
        except Exception as e:
            logging.error(f"Error connecting to FTP server: {e}")
            self.ftp = None
            raise
        else:
            self._set_connected(True)

    def list_files(self, remote_path: Optional[str] = None, pattern: Optional[str] = None) -> Optional[Iterable[str]]:
        """List names at the given remote path and optionally filter by regex.

        Parameters
        ----------
        remote_path : str, optional
            Remote directory to list. Defaults to current server directory.
        pattern : str, optional
            Regular expression applied to names returned by ``NLST`` (via
            :func:`re.search`).

        Returns
        -------
        list of str or None
            Filenames present in the directory, or ``None`` on error.
        """
        directory = remote_path or "."
        files: List[str] = []
        try:
            if not self.ftp or not self.ftp.sock:
                logging.info("Reconnecting to FTP server for listing files.")
                self.connect()
            files = self.ftp.nlst(directory)
            if pattern:
                rx = re.compile(pattern)
                files = [f for f in files if rx.search(f)]
            return files
        except (EOFError, error_temp) as e:
            logging.error(f"Network error listing files in {directory}: {e}")
        except error_perm as e:
            logging.error(f"Permission error listing files in {directory}: {e}")
        except Exception as e:
            logging.error(f"Unexpected error listing files in {directory}: {e}")
        return None

    def fetch(self, remote_path: str, local_filename: Optional[str] = None) -> bool:
        """Download a remote file to a local path.

        Parameters
        ----------
        remote_path : str
            Full remote file path (may include directories).
        local_filename : str, optional
            Local destination path. Defaults to basename of ``remote_path``.

        Returns
        -------
        bool
            ``True`` on success, ``False`` otherwise.
        """
        local_file_path = local_filename or Path(remote_path).name
        return self.download_file(remote_path, local_file_path)

    # Backwards-compatible API
    def download_file(self, remote_file_path: str, local_file_path: str) -> bool:
        """Download a single file via FTP with retries.

        Parameters
        ----------
        remote_file_path : str
            Remote file path (may include directories).
        local_file_path : str
            Local destination path including filename.

        Returns
        -------
        bool
            ``True`` if downloaded and non-zero in size; ``False`` otherwise.

        Raises
        ------
        FileNotFoundError
            If the remote file does not exist.
        Exception
            If the final attempt fails for any other reason.
        """
        attempts = 3
        directory = ""
        filename = remote_file_path

        if "/" in remote_file_path:
            directory, filename = remote_file_path.rsplit("/", 1)

        class ZeroSizeError(Exception):
            pass

        def do_download() -> None:
            if not self.ftp or not self.ftp.sock:
                logging.info("Reconnecting to FTP server.")
                self.connect()

            if directory:
                self.ftp.cwd(directory)

            files = self.ftp.nlst()
            if filename not in files:
                raise FileNotFoundError(
                    f"The path does not point to a valid file: {remote_file_path}"
                )

            local_file = Path(local_file_path)
            if not local_file.parent.exists():
                logging.info(f"Creating local directory: {local_file.parent}")
                self._ensure_parent_dir(local_file)

            if local_file.exists() and not local_file.is_file():
                raise NotSupportedError(f"Local path is not a file: {local_file_path}")

            with local_file.open("wb") as lf:
                self.ftp.retrbinary("RETR " + filename, lf.write)

            if local_file.stat().st_size == 0:
                raise ZeroSizeError(
                    f"Downloaded file {remote_file_path} has zero size."
                )

        def on_retry(index: int, exc: BaseException) -> None:
            logging.warning(
                f"Attempt {index + 1} - retrying download of {remote_file_path}: {exc}"
            )
            try:
                lf = Path(local_file_path)
                if lf.exists() and lf.stat().st_size == 0:
                    lf.unlink()
            except Exception:
                pass
            self.ftp = None

        try:
            self._with_retries(
                do_download,
                attempts=attempts,
                exceptions=(EOFError, error_temp, TimeoutError, ZeroSizeError),
                before_retry=on_retry,
            )
            logging.info(
                f"Successfully downloaded {remote_file_path} to {local_file_path}."
            )
            return True
        except FileNotFoundError:
            logging.error(f"The path does not point to a valid file: {remote_file_path}")
            raise
        except Exception as e:
            logging.error(f"Failed to download {remote_file_path}: {e}")
            return False

    def upload_file(self, local_file_path: str, remote_file_path: str) -> None:
        """Upload a local file to the FTP server with retries.

        Parameters
        ----------
        local_file_path : str
            Local file path to upload.
        remote_file_path : str
            Remote path including target filename.

        Raises
        ------
        Exception
            When the final attempt fails to upload the file.
        """
        attempts = 3

        def do_upload() -> None:
            if not self.ftp or not self.ftp.sock:
                logging.info("Reconnecting to FTP server for upload.")
                self.connect()
            with Path(local_file_path).open("rb") as local_file:
                self.ftp.storbinary("STOR " + remote_file_path, local_file)

        def on_retry(index: int, exc: BaseException) -> None:
            logging.warning(
                f"Attempt {index + 1} - retrying upload of {local_file_path}: {exc}"
            )
            self.ftp = None

        self._with_retries(
            do_upload,
            attempts=attempts,
            exceptions=(EOFError, error_temp),
            before_retry=on_retry,
        )
        logging.info(f"Successfully uploaded {local_file_path} to {remote_file_path}.")

    def delete_empty_files(self, dir_path: Path) -> None:
        """Delete zero-byte files in a directory.

        Parameters
        ----------
        dir_path : pathlib.Path
            Directory to scan for empty files.
        """
        for file_path in dir_path.iterdir():
            if file_path.is_file() and file_path.stat().st_size == 0:
                file_path.unlink()
                logging.debug(f"Deleted empty file: {file_path}")

    def sync_ftp_directory(self, remote_dir: str, local_dir: str, dataset_period: str) -> None:
        """Synchronize a remote directory to local storage by date range.

        Parameters
        ----------
        remote_dir : str
            Remote FTP directory to synchronize.
        local_dir : str
            Local directory to mirror files into.
        dataset_period : str
            Period spec parsable by :class:`~datavizhub.utils.DateManager.DateManager`
            (e.g., ``"7d"``, ``"24h"``).

        Notes
        -----
        - Downloads files within the date range not present locally or with size 0.
        - Deletes local files no longer present remotely.
        """
        date_manager = DateManager()
        start_date, end_date = date_manager.get_date_range(dataset_period)

        logging.info(f"start date = {start_date}, end date = {end_date}")

        path = Path(local_dir)
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)

        self.delete_empty_files(Path(local_dir))

        if not self.ftp or not self.ftp.sock:
            self.connect()
        self.ftp.cwd(remote_dir)
        remote_files = [f for f in self.ftp.nlst() if f not in (".", "..")]
        local_files = {file.name for file in Path(local_dir).iterdir() if file.is_file()}

        for file in remote_files:
            if date_manager.is_date_in_range(file, start_date, end_date):
                local_file_path = Path(local_dir) / file
                if file in local_files:
                    local_files.discard(file)
                if not local_file_path.exists() or local_file_path.stat().st_size == 0:
                    self.download_file(file, str(local_file_path))
                    logging.debug(f"Synced: {file} to {local_file_path}")

        for file in local_files:
            local_file_path = Path(local_dir) / file
            local_file_path.unlink()
            logging.debug(
                f"Deleted local file {file} as it no longer exists in the remote directory."
            )

    def upload(self, local_path: str, remote_path: str) -> bool:
        """Standardized upload implementation delegating to :meth:`upload_file`.

        Parameters
        ----------
        local_path : str
            Local file path to upload.
        remote_path : str
            Remote destination path.

        Returns
        -------
        bool
            ``True`` on success.
        """
        self.upload_file(local_path, remote_path)
        return True

    def disconnect(self) -> None:
        """Close the FTP session if connected."""
        if self.ftp:
            try:
                self.ftp.quit()
            except Exception as e:
                logging.error(f"Error disconnecting from FTP: {e}")
            finally:
                self.ftp = None
                self._set_connected(False)

    # ---- Optional operations -----------------------------------------------------------

    def exists(self, remote_path: str) -> bool:
        """Return True if the remote file exists on the FTP server.

        Parameters
        ----------
        remote_path : str
            Path to the remote file (may include directories).
        """
        try:
            if not self.ftp or not self.ftp.sock:
                self.connect()
            directory = ""
            filename = remote_path
            if "/" in remote_path:
                directory, filename = remote_path.rsplit("/", 1)
                if directory:
                    self.ftp.cwd(directory)
            files = self.ftp.nlst()
            return filename in files
        except Exception:
            return False

    def delete(self, remote_path: str) -> bool:
        """Delete a remote file if possible.

        Parameters
        ----------
        remote_path : str
            Path to the remote file (may include directories).
        """
        try:
            if not self.ftp or not self.ftp.sock:
                self.connect()
            directory = ""
            filename = remote_path
            if "/" in remote_path:
                directory, filename = remote_path.rsplit("/", 1)
                if directory:
                    self.ftp.cwd(directory)
            self.ftp.delete(filename)
            return True
        except Exception:
            return False

    def stat(self, remote_path: str):
        """Return minimal metadata for a remote file (size in bytes).

        Parameters
        ----------
        remote_path : str
            Path to the remote file (may include directories).

        Returns
        -------
        dict or None
            A mapping with ``{"size": int}`` if available; ``None`` on error.
        """
        try:
            if not self.ftp or not self.ftp.sock:
                self.connect()
            directory = ""
            filename = remote_path
            if "/" in remote_path:
                directory, filename = remote_path.rsplit("/", 1)
                if directory:
                    self.ftp.cwd(directory)
            size = self.ftp.size(filename)
            return {"size": int(size) if size is not None else None}
        except Exception:
            return None

    # ---- Advanced features: size, ranges, and GRIB helpers -----------------------------

    def get_size(self, remote_path: str) -> Optional[int]:
        """Return the size in bytes for a remote file using ``SIZE``."""
        try:
            if not self.ftp or not self.ftp.sock:
                self.connect()
            directory = ""
            filename = remote_path
            if "/" in remote_path:
                directory, filename = remote_path.rsplit("/", 1)
                if directory:
                    self.ftp.cwd(directory)
            size = self.ftp.size(filename)
            return int(size) if size is not None else None
        except Exception:
            return None

    def _download_range(self, remote_path: str, start: int, end: int, blocksize: int = 8192) -> bytes:
        """Download a byte range using FTP ``REST``. Stops after the requested length.

        Notes
        -----
        - Establishes a binary transfer and uses ``REST`` to seek to ``start``.
        - Reads exactly ``end-start+1`` bytes and aborts the transfer once done.
        """
        if not self.ftp or not self.ftp.sock:
            self.connect()
        ftp = self.ftp
        directory = ""
        filename = remote_path
        if "/" in remote_path:
            directory, filename = remote_path.rsplit("/", 1)
            if directory:
                ftp.cwd(directory)
        remaining = end - start + 1
        buffer = BytesIO()

        class _StopDownload(Exception):
            pass

        def _cb(chunk: bytes) -> None:
            nonlocal remaining
            if remaining <= 0:
                raise _StopDownload()
            take = min(len(chunk), remaining)
            if take:
                buffer.write(chunk[:take])
                remaining -= take
            if remaining <= 0:
                raise _StopDownload()

        try:
            # retrbinary supports 'rest' argument for starting offset
            ftp.retrbinary(f"RETR {filename}", _cb, blocksize=blocksize, rest=start)
        except _StopDownload:
            try:
                ftp.abort()
            except Exception:
                pass
        return buffer.getvalue()

    def get_idx_lines(
        self,
        remote_path: str,
        *,
        write_to: Optional[str] = None,
        timeout: int = 30,
        max_retries: int = 3,
    ) -> Optional[List[str]]:
        """Fetch and parse the GRIB ``.idx`` for a remote path.

        Appends ``.idx`` to ``remote_path`` unless an explicit ``.idx`` is provided.
        """
        idx_path = ensure_idx_path(remote_path)
        attempts = 0
        while attempts < max_retries:
            try:
                if not self.ftp or not self.ftp.sock:
                    self.connect()
                directory = ""
                filename = idx_path
                if "/" in idx_path:
                    directory, filename = idx_path.rsplit("/", 1)
                    if directory:
                        self.ftp.cwd(directory)
                buf = BytesIO()
                self.ftp.retrbinary(f"RETR {filename}", buf.write)
                payload = buf.getvalue()
                break
            except Exception:
                attempts += 1
                if attempts >= max_retries:
                    return None
        lines = parse_idx_lines(payload)
        if write_to:
            try:
                with open(write_to if write_to.endswith(".idx") else f"{write_to}.idx", "w", encoding="utf8") as f:
                    f.write("\n".join(lines))
            except Exception:
                pass
        return lines

    def idx_to_byteranges(self, lines: List[str], search_str: str) -> Dict[str, str]:
        return _idx_to_byteranges(lines, search_str)

    def get_chunks(self, remote_path: str, chunk_size: int = 500 * 1024 * 1024) -> List[str]:
        size = self.get_size(remote_path)
        if size is None:
            return []
        return _compute_chunks(size, chunk_size)

    def download_byteranges(
        self,
        remote_path: str,
        byte_ranges: _Iterable[str],
        *,
        max_workers: int = 10,
        timeout: int = 30,
    ) -> bytes:
        """Download multiple byte ranges using parallel FTP connections.

        Notes
        -----
        - Spawns one short-lived FTP connection per range (per thread) to
          maintain thread safety across requests; this incurs connection
          overhead but avoids shared-socket issues in :mod:`ftplib`.
        - Uses ``REST`` to position the transfer at the desired start byte;
          stops reading after the requested range length. Results are
          concatenated in the input order.
        """
        # Worker that uses a fresh connection to avoid thread-safety issues
        def _worker(_remote: str, _range: str) -> bytes:
            start_end = _range.replace("bytes=", "").split("-")
            start = int(start_end[0]) if start_end[0] else 0
            # If no end provided, read to EOF using single connection
            if start_end[1]:
                end = int(start_end[1])
            else:
                size = self.get_size(_remote) or 0
                end = max(size - 1, start)

            ftp = FTP(timeout=timeout)
            ftp.connect(self.host, self.port)
            ftp.login(user=self.username, passwd=self.password)
            ftp.set_pasv(True)
            # reuse the helper logic with a temporary FTP instance
            remaining = end - start + 1
            buffer = BytesIO()

            class _StopDownload(Exception):
                pass

            def _cb(chunk: bytes) -> None:
                nonlocal remaining
                if remaining <= 0:
                    raise _StopDownload()
                take = min(len(chunk), remaining)
                if take:
                    buffer.write(chunk[:take])
                    remaining -= take
                if remaining <= 0:
                    raise _StopDownload()

            directory = ""
            filename = _remote
            if "/" in _remote:
                directory, filename = _remote.rsplit("/", 1)
                if directory:
                    ftp.cwd(directory)
            try:
                ftp.retrbinary(f"RETR {filename}", _cb, rest=start)
            except _StopDownload:
                try:
                    ftp.abort()
                except Exception:
                    pass
            try:
                ftp.quit()
            except Exception:
                pass
            return buffer.getvalue()

        from concurrent.futures import ThreadPoolExecutor, as_completed
        indexed = list(enumerate(byte_ranges))
        if not indexed:
            return b""
        results: Dict[int, bytes] = {}
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futs = {ex.submit(_worker, remote_path, rng): i for i, rng in indexed}
            for fut in as_completed(futs):
                idx = futs[fut]
                results[idx] = fut.result() or b""
        buf = BytesIO()
        for i, _rng in indexed:
            buf.write(results.get(i, b""))
        return buf.getvalue()
