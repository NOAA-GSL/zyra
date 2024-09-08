import logging
from ftplib import FTP, error_perm, error_temp
from pathlib import Path

from datavizhub.utils.DateManager import DateManager


class FTPManager:
    """
    FTPManager is a class designed to simplify interactions with an FTP server.
    It encapsulates common FTP operations such as connecting to an FTP server,
    listing files in a directory, uploading and downloading files, and disconnecting
    from the server.

    This class uses Python's built-in `ftplib` library and provides a user-friendly
    interface for handling FTP tasks. It manages the FTP connection lifecycle and
    ensures that file transfers are handled efficiently and securely.

    The FTPManager class is ideal for applications that require regular interactions
    with an FTP server, such synchronizing files between a local directory and an FTP
    site.

    Usage:
    Initialize the class with FTP server details (host, username, password), and then
    use its methods to perform desired FTP operations. The class methods handle the
    complexities of FTP commands and connection management, making it easy to integrate
    FTP functionalities into your applications.

    Example:
    ```python
    ftp_manager = FTPManager('ftp.example.com', 21, 'username', 'password')
    ftp_manager.connect()
    ftp_manager.upload_file('local_file.txt', 'remote_file.txt')
    ftp_manager.disconnect()
    ```
    """

    def __init__(
        self, host, port=21, username="anonymous", password="test@test.com", timeout=30
    ):
        """
        Initialize the FTPManager with FTP server details.

        Args:
            host (str): Hostname or IP address of the FTP server.
            port (int): Port number used by the FTP server.
            username (str): Username for the FTP server.
            password (str): Password for the FTP server.
            timeout (int): Timeout in seconds for the FTP connection.
        """
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.timeout = timeout
        self.ftp = None

    def connect(self):
        """
        Connect to the FTP server. Sets FTP to None if it fails to connect.
        """
        try:
            self.ftp = FTP(timeout=self.timeout)
            self.ftp.connect(self.host, self.port)
            self.ftp.login(user=self.username, passwd=self.password)
            self.ftp.set_pasv(True)
            logging.info(f"Connected to FTP server: {self.host}")
        except Exception as e:
            logging.error(f"Error connecting to FTP server: {e}")
            self.ftp = None  # Set ftp to None to signify connection failure
            raise

    def list_files(self, directory):
        """
        List files in a specified directory on the FTP server with improved error handling.

        Args:
            directory (str): Directory path to list files from.

        Returns:
            list: A list of filenames, or None if an error occurs.
        """
        files = []
        try:
            if not self.ftp or not self.ftp.sock:
                logging.info("Reconnecting to FTP server for listing files.")
                self.connect()

            files = self.ftp.nlst(directory)
            return files
        except (EOFError, error_temp) as e:
            logging.error(f"Network error listing files in {directory}: {e}")
            # You might want to reconnect or take other actions here
        except error_perm as e:
            # This handles permissions errors, such as when the directory does not exist
            logging.error(f"Permission error listing files in {directory}: {e}")
        except Exception as e:
            logging.error(f"Unexpected error listing files in {directory}: {e}")
        return None  # Returning None to indicate failure

    def download_file(self, remote_file_path, local_file_path):
        """
        Download a file from the FTP server.

        This method attempts to download a file from the FTP server to the local file system.
        If the initial download is unsuccessful or results in a zero-size file, it retries
        the download a specified number of times. It checks for an active FTP connection
        before starting the download and reconnects if necessary.

        Args:
            remote_file_path (str): The path of the file on the FTP server.
            local_file_path (str): The local path where the file will be saved.

        Raises:
            FileNotFoundError: If the file does not exist on the FTP server.
            Exception: If the file cannot be downloaded after the specified number of attempts,
                    or if the file remains zero-sized after downloading.
        """
        attempts = 3
        directory = ""
        filename = remote_file_path

        # Separate directory and filename if there's a directory in the path
        if "/" in remote_file_path:
            directory, filename = remote_file_path.rsplit("/", 1)

        for attempt in range(attempts):
            try:
                if not self.ftp or not self.ftp.sock:
                    logging.info("Reconnecting to FTP server.")
                    self.connect()

                # Change to the directory after reconnecting
                if directory:
                    self.ftp.cwd(directory)

                # List files in the directory to check for existence
                files = self.ftp.nlst()
                #logging.debug(f"Files in directory '{directory}': {files}")

                if filename not in files:
                    raise FileNotFoundError(
                        f"The path does not point to a valid file: {remote_file_path}"
                    )

                local_file = Path(local_file_path)
                # Check if the local directory exists
                if not local_file.parent.exists():
                    logging.info(f"Creating local directory: {local_file.parent}")
                    local_file.parent.mkdir(parents=True, exist_ok=True)

                # Check if the local path is valid and points to a file
                if local_file.exists() and not local_file.is_file():
                    logging.error(f"The local path is not a file: {local_file_path}")
                    return False

                with local_file.open("wb") as lf:
                    self.ftp.retrbinary("RETR " + filename, lf.write)

                if local_file.stat().st_size == 0:
                    logging.warning(
                        f"Downloaded file {remote_file_path} has zero size, attempting to re-download."
                    )
                    continue

                logging.info(
                    f"Successfully downloaded {remote_file_path} to {local_file_path}."
                )
                return True
            except FileNotFoundError as e:
                logging.error(f"Attempt {attempt + 1} - {e}")
                raise  # Raise immediately since the file doesn't exist
            except (EOFError, error_temp, TimeoutError) as e:
                logging.error(
                    f"Attempt {attempt + 1} - Network error downloading {remote_file_path}: {e}"
                )

                self.delete_empty_files(
                    local_file_path
                )  # Clean up zero-size files before starting the sync

                self.ftp = None  # Force reconnection on next attempt
            except Exception as e:
                logging.error(
                    f"Attempt {attempt + 1} - Error downloading {remote_file_path}: {e}"
                )
                if attempt == attempts - 1:
                    raise
                else:
                    self.ftp = None

        return False

    def upload_file(self, local_file_path, remote_file_path):
        """
        Upload a file to the FTP server.

        This method attempts to upload a file from the local file system to the specified
        location on the FTP server. It includes error handling and retry mechanisms to
        manage common issues such as broken connections. The function will attempt to
        reconnect and retry the upload a specified number of times before failing.

        Args:
            local_file_path (str): The local path of the file to upload. This should be
                                a complete path including the filename.
            remote_file_path (str): The destination path on the FTP server. This should
                                    include the filename under which the file will be
                                    stored on the server.
        """
        attempts = 3
        for attempt in range(attempts):
            try:
                if not self.ftp or not self.ftp.sock:
                    logging.info("Reconnecting to FTP server for upload.")
                    self.connect()

                with Path(local_file_path).open("rb") as local_file:
                    self.ftp.storbinary("STOR " + remote_file_path, local_file)

                logging.info(
                    f"Successfully uploaded {local_file_path} to {remote_file_path}."
                )
                break
            except (EOFError, error_temp) as e:
                logging.error(
                    f"Attempt {attempt + 1} - Network error uploading {local_file_path}: {e}"
                )
                self.ftp = None  # Force reconnection on next attempt
            except error_perm as e:
                logging.error(
                    f"Attempt {attempt + 1} - Permission error uploading {local_file_path}: {e}"
                )
                if (
                    attempt == attempts - 1
                ):  # Consider whether retrying makes sense based on the error
                    raise
                else:
                    self.ftp = None
            except Exception as e:
                logging.error(
                    f"Attempt {attempt + 1} - Error uploading {local_file_path}: {e}"
                )
                if attempt == attempts - 1:
                    raise
                else:
                    self.ftp = None  # Reset connection in case of unexpected errors

    def delete_empty_files(self, local_file_path):
        # Create a Path object for the directory
        dir_path = Path(local_file_path)
        # Iterate through each item in the directory
        for file_path in dir_path.iterdir():
            # Check if the item is a file and its size is 0 using a single if statement
            if file_path.is_file() and file_path.stat().st_size == 0:
                # Delete the file
                file_path.unlink()
                logging.debug(f"Deleted empty file: {file_path}")

    def sync_ftp_directory(self, remote_dir, local_dir, dataset_period):
        """
        Sync a directory from the FTP server.

        Args:
            remote_dir (str): The directory to sync from FTP.
            local_dir (str): The local directory to sync to.
            dataset_period (str): The period of time backwards from present to sync from FTP.
        """

        # Parse the start and end dates
        date_manager = DateManager()
        start_date, end_date = date_manager.get_date_range(dataset_period)

        logging.info(f"start date = {start_date}, end date = {end_date}")

        # Check if the local directory exists, create it if it doesn't.
        path = Path(local_dir)
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)

        self.delete_empty_files(
            local_dir
        )  # Clean up zero-size files before starting the sync

        # Change the current directory on the FTP server to the specified remote directory.
        self.ftp.cwd(remote_dir)

        # Get the list of files in the remote directory.
        remote_files = self.ftp.nlst()

        # Filter out '.' and '..' from the list
        remote_files = [file for file in remote_files if file not in (".", "..")]

        # Get a list of all files currently in the local directory.
        local_files = {
            file.name for file in Path(local_dir).iterdir() if file.is_file()
        }

        for file in remote_files:
            # Check if the file is within the date range
            if date_manager.is_date_in_range(file, start_date, end_date):
                local_file_path = Path(local_dir) / file

                # Remove the file from the local_files set since it exists in the remote directory
                local_files.discard(file)

                # Download the file if it doesn't exist locally or if it's a zero-size file
                if not local_file_path.exists() or local_file_path.stat().st_size == 0:
                    self.download_file(file, str(local_file_path))
                    logging.debug(f"Synced: {file} to {local_file_path}")

        # Delete files that are no longer present in the remote directory but exist locally
        for file in local_files:
            local_file_path = Path(local_dir) / file
            local_file_path.unlink()
            logging.debug(
                f"Deleted local file {file} as it no longer exists in the remote directory."
            )

    def disconnect(self):
        """
        Disconnect from the FTP server.
        """
        if self.ftp:
            try:
                self.ftp.quit()
            except Exception as e:
                logging.error(f"Error disconnecting from FTP: {e}")
            finally:
                self.ftp = None
