"""FTP data acquisition manager.

Implements :class:`~datavizhub.acquisition.base.DataAcquirer` for FTP servers
with support for listing, fetching, and uploading files.
"""

import logging
from pathlib import Path
from typing import Iterable, Optional

from ftplib import FTP, error_perm, error_temp

from datavizhub.acquisition.base import DataAcquirer, NotSupportedError
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

    def list_files(self, remote_path: Optional[str] = None) -> Optional[Iterable[str]]:
        """List names at the given remote path.

        Parameters
        ----------
        remote_path : str, optional
            Remote directory to list. Defaults to current server directory.

        Returns
        -------
        list of str or None
            Filenames present in the directory, or ``None`` on error.
        """
        directory = remote_path or "."
        files: list[str] = []
        try:
            if not self.ftp or not self.ftp.sock:
                logging.info("Reconnecting to FTP server for listing files.")
                self.connect()
            files = self.ftp.nlst(directory)
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
