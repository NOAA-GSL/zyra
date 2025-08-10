"""HTTP data acquisition handler.

Provides a minimal :class:`~datavizhub.acquisition.base.DataAcquirer` for HTTP
GET downloads, plus optional helpers for content size queries, GRIB ``.idx``
subsetting, byte-range downloads, and best-effort listing via anchor scraping.

Advanced Features
-----------------
- ``get_size(url)``: return ``Content-Length`` from a ``HEAD`` if provided.
- ``get_idx_lines(url, *, write_to=None, timeout=30, max_retries=3)``: fetch
  and parse ``.idx`` (appends ``.idx`` unless explicit).
- ``idx_to_byteranges(lines, search_regex)``: regex-based selection of ranges.
- ``get_chunks(url, chunk_size=500MB)``: compute contiguous ranges.
- ``download_byteranges(url, byte_ranges, *, max_workers=10, timeout=30)``:
  parallel ranged GETs, concatenated in order.
- ``list_files(url, pattern=None)``: scrape anchor tags from directory-style
  index pages (e.g., NOMADS) and filter with regex if provided.
"""

import logging
import re
from pathlib import Path
from typing import Iterable, Optional, Iterable as _Iterable
from urllib.parse import urljoin

import requests

from datavizhub.acquisition.base import DataAcquirer
from datavizhub.acquisition.grib_utils import (
    ensure_idx_path,
    parse_idx_lines,
    idx_to_byteranges as _idx_to_byteranges,
    compute_chunks as _compute_chunks,
    parallel_download_byteranges as _parallel_download_byteranges,
)


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

    def list_files(self, remote_path: Optional[str] = None, pattern: Optional[str] = None) -> Optional[Iterable[str]]:
        """Attempt to list files by scraping anchor tags from an index page.

        This is best-effort and intended for directory-style endpoints such as
        NOMADS listings. If the page is not HTML or contains no anchors, an
        empty list is returned.

        Parameters
        ----------
        remote_path : str
            Page URL to scrape for anchors.
        pattern : str, optional
            Regular expression applied to full URLs (via :func:`re.search`).
        """
        if not remote_path:
            return []
        try:
            resp = requests.get(remote_path, timeout=10)
            resp.raise_for_status()
            text = resp.text
        except requests.exceptions.RequestException:
            return []

        hrefs = re.findall(r'href=["\']([^"\']+)["\']', text, re.IGNORECASE)
        results: list[str] = []
        for href in hrefs:
            if href.startswith("?") or href.startswith("#"):
                continue
            # Build absolute URL for relative anchors
            abs_url = urljoin(remote_path, href)
            results.append(abs_url)
        if pattern:
            rx = re.compile(pattern)
            results = [u for u in results if rx.search(u)]
        return results

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

    # ---- Advanced features: size, ranges, and GRIB helpers -----------------------------

    def get_size(self, url: str) -> Optional[int]:
        """Return the ``Content-Length`` from a ``HEAD`` request if provided."""
        try:
            r = requests.head(url, timeout=10)
            r.raise_for_status()
            value = r.headers.get("Content-Length")
            return int(value) if value is not None else None
        except requests.exceptions.RequestException:
            return None

    def _download(self, url: str, range_header: Optional[str] = None, timeout: int = 30) -> bytes:
        """Internal helper to issue a GET with optional Range header and timeout."""
        headers = {"Range": range_header} if range_header else None
        r = requests.get(url, headers=headers, timeout=timeout)
        r.raise_for_status()
        return r.content

    def get_idx_lines(
        self,
        url: str,
        *,
        write_to: Optional[str] = None,
        timeout: int = 30,
        max_retries: int = 3,
    ) -> Optional[list[str]]:
        """Fetch and parse the GRIB index (``.idx``) for a URL.

        Appends ``.idx`` to ``url`` unless an explicit ``.idx`` path is provided.
        Retries are applied on transient failures.
        """
        idx_url = ensure_idx_path(url)
        attempt = 0
        while attempt < max_retries:
            try:
                payload = self._download(idx_url, timeout=timeout)
                break
            except requests.exceptions.RequestException:
                attempt += 1
                if attempt >= max_retries:
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
        return _idx_to_byteranges(lines, search_str)

    def get_chunks(self, url: str, chunk_size: int = 500 * 1024 * 1024) -> list[str]:
        size = self.get_size(url)
        if size is None:
            return []
        return _compute_chunks(size, chunk_size)

    def download_byteranges(
        self,
        url: str,
        byte_ranges: _Iterable[str],
        *,
        max_workers: int = 10,
        timeout: int = 30,
    ) -> bytes:
        """Parallel ranged downloads concatenated in the order of ``byte_ranges``.

        Parameters
        ----------
        url : str
            Target URL for the ranged GET requests.
        byte_ranges : Iterable[str]
            Iterable of Range header values, e.g., ``"bytes=0-99"``.
        max_workers : int, default=10
            Number of worker threads for parallelism.
        timeout : int, default=30
            Per-request timeout (seconds).
        """
        def _ranged_get(u: str, range_header: str) -> bytes:
            return self._download(u, range_header=range_header, timeout=timeout)

        return _parallel_download_byteranges(_ranged_get, url, byte_ranges, max_workers=max_workers)

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
