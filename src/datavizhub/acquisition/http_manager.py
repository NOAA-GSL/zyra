"""HTTP data acquisition handler.

Provides a minimal :class:`~datavizhub.acquisition.base.DataAcquirer` for HTTP
GET downloads. Upload and listing are intentionally unsupported.
"""

import logging
from pathlib import Path
from typing import Iterable, Optional

import requests

from datavizhub.acquisition.base import DataAcquirer


class HTTPHandler(DataAcquirer):
    CAPABILITIES = {"fetch"}
    """Acquire files over HTTP/HTTPS.

    This lightweight manager performs simple HTTP(S) GETs to fetch remote
    resources to the local filesystem. Because HTTP is stateless for these
    operations, :meth:`connect` and :meth:`disconnect` are no-ops.

    Supported Protocols
    -------------------
    - ``http://``
    - ``https://``

    Examples
    --------
    Download a file via HTTPS::

        from datavizhub.acquisition.http_manager import HTTPHandler

        http = HTTPHandler()
        http.connect()  # no-op
        http.fetch("https://example.com/data.json", "data.json")
        http.disconnect()  # no-op
    """

    def connect(self) -> None:
        """Initialize the handler (no persistent connection).

        Notes
        -----
        Provided for API parity; does nothing for basic HTTP GETs.
        """
        return None

    def fetch(self, remote_path: str, local_filename: Optional[str] = None) -> bool:
        """Download content at ``remote_path`` to ``local_filename``.

        Parameters
        ----------
        remote_path : str
            Full HTTP(S) URL to download.
        local_filename : str, optional
            Local destination path. Defaults to the basename of the URL.

        Returns
        -------
        bool
            ``True`` on success, ``False`` if request fails.
        """
        filename = local_filename or Path(remote_path).name
        try:
            response = requests.get(remote_path, timeout=10)
            response.raise_for_status()
            with Path(filename).open("wb") as f:
                f.write(response.content)
            logging.info(f"Successfully downloaded {remote_path}")
            return True
        except requests.exceptions.HTTPError as http_err:
            logging.error(
                f"HTTP error occurred while downloading {remote_path}: {http_err}"
            )
        except requests.exceptions.ConnectionError as conn_err:
            logging.error(
                f"Connection error occurred while downloading {remote_path}: {conn_err}"
            )
        except requests.exceptions.Timeout as timeout_err:
            logging.error(
                f"Timeout occurred while downloading {remote_path}: {timeout_err}"
            )
        except requests.exceptions.RequestException as req_err:
            logging.error(f"Error occurred while downloading {remote_path}: {req_err}")
        except Exception as e:
            logging.error(f"An error occurred while downloading {remote_path}: {e}")
        return False

    def list_files(self, remote_path: Optional[str] = None) -> Optional[Iterable[str]]:
        """Listing is not supported for generic HTTP sources.

        Returns
        -------
        None
            Always returns ``None``.
        """
        return None

    def disconnect(self) -> None:
        """No persistent connection to tear down."""
        return None

    def upload(self, local_path: str, remote_path: str) -> bool:
        """Uploading is not supported for HTTPHandler.

        Raises
        ------
        NotSupportedError
            Always raised to indicate upload is unsupported.
        """
        from datavizhub.acquisition.base import NotSupportedError

        raise NotSupportedError("upload() is not supported for HTTPHandler")

    # Backwards-compatible helpers
    @staticmethod
    def download_file(url: str, filename: str) -> None:
        """Compatibility helper that downloads a file.

        Parameters
        ----------
        url : str
            File URL to download.
        filename : str
            Local destination path.
        """
        HTTPHandler().fetch(url, filename)

    @staticmethod
    def fetch_data(url: str):
        """Fetch binary payload via GET.

        Parameters
        ----------
        url : str
            URL to request.

        Returns
        -------
        bytes or None
            Raw response body on success, otherwise ``None``.
        """
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return response.content
        except requests.exceptions.RequestException as e:
            logging.error(f"Error occurred while fetching data from {url}: {e}")
        except Exception as e:
            logging.error(f"An error occurred while fetching data from {url}: {e}")
        return None

    @staticmethod
    def fetch_text(url: str):
        """Fetch text content via GET.

        Parameters
        ----------
        url : str
            URL to request.

        Returns
        -------
        str or None
            Text response on success, otherwise ``None``.
        """
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return response.text
        except requests.exceptions.RequestException as e:
            logging.error(f"Request failed: {e}")
            return None

    @staticmethod
    def fetch_json(url: str):
        """Fetch JSON content via GET and parse it.

        Parameters
        ----------
        url : str
            URL to request.

        Returns
        -------
        dict or list or None
            Parsed JSON object on success, otherwise ``None``.
        """
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logging.error(f"Request failed: {e}")
            return None

    @staticmethod
    def post_data(url: str, data, headers=None):
        """Send a POST request and return the body.

        Parameters
        ----------
        url : str
            URL to post to.
        data : Any
            Request payload.
        headers : dict, optional
            Optional request headers.

        Returns
        -------
        str or None
            Response text on success, otherwise ``None``.
        """
        try:
            response = requests.post(url, data=data, headers=headers, timeout=10)
            response.raise_for_status()
            return response.text
        except requests.exceptions.RequestException as e:
            logging.error(f"Post request failed: {e}")
            return None

    @staticmethod
    def fetch_headers(url: str):
        """Perform a HEAD request and return headers.

        Parameters
        ----------
        url : str
            URL to request.

        Returns
        -------
        Mapping or None
            Response headers on success, otherwise ``None``.
        """
        try:
            response = requests.head(url, timeout=10)
            response.raise_for_status()
            return response.headers
        except requests.exceptions.RequestException as e:
            logging.error(f"HEAD request failed: {e}")
            return None
