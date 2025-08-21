"""HTTP connector backend.

Provides functional helpers to fetch and list resources over HTTP(S), as well
as convenience utilities for GRIB workflows (``.idx`` parsing and byte-range
downloads) and Content-Length probing.

Functions are intentionally small and dependency-light so they can be used by
the CLI, pipelines, or higher-level wrappers without imposing heavy imports.
"""

from __future__ import annotations

import re
from typing import Iterable
from urllib.parse import urljoin

# Make a module-level "requests" attribute patchable in tests even when the
# optional dependency is not installed in the environment.
try:  # pragma: no cover - env dependent
    import requests as requests  # type: ignore
except Exception:  # pragma: no cover

    class _RequestsProxy:
        pass

    requests = _RequestsProxy()  # type: ignore


def fetch_bytes(url: str, *, timeout: int = 60) -> bytes:
    """Return the raw response body for a GET request.

    Parameters
    - url: HTTP(S) URL to fetch.
    - timeout: request timeout in seconds.
    """
    try:
        import requests  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError("HTTP backend requires the 'requests' extra") from exc

    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    return r.content


def fetch_text(url: str, *, timeout: int = 60) -> str:
    """Return the response body as text for a GET request."""
    try:
        import requests  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError("HTTP backend requires the 'requests' extra") from exc

    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    return r.text


def fetch_json(url: str, *, timeout: int = 60):
    """Return the parsed JSON body for a GET request."""
    try:
        import requests  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError("HTTP backend requires the 'requests' extra") from exc

    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    return r.json()


def post_data(
    url: str, data: bytes, *, timeout: int = 60, content_type: str | None = None
) -> int:
    """POST raw bytes to a URL and return the HTTP status code."""
    try:
        import requests  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError("HTTP backend requires the 'requests' extra") from exc

    headers = {"Content-Type": content_type} if content_type else None
    r = requests.post(url, data=data, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r.status_code


def post_bytes(
    url: str, data: bytes, *, timeout: int = 60, content_type: str | None = None
) -> int:
    """Backward-compat wrapper for ``post_data``."""
    return post_data(url, data, timeout=timeout, content_type=content_type)


def list_files(url: str, pattern: str | None = None, *, timeout: int = 60) -> list[str]:
    """Best-effort directory listing by scraping anchor tags on index pages.

    Returns absolute URLs; optionally filters them via regex ``pattern``.
    """
    try:
        import requests  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError("HTTP backend requires the 'requests' extra") from exc

    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    text = r.text
    hrefs = re.findall(r'href=["\']([^"\']+)["\']', text, re.IGNORECASE)
    results: list[str] = []
    for href in hrefs:
        if href.startswith("?") or href.startswith("#"):
            continue
        results.append(urljoin(url, href))
    if pattern:
        rx = re.compile(pattern)
        results = [u for u in results if rx.search(u)]
    return results


def get_idx_lines(url: str, *, timeout: int = 60, max_retries: int = 3) -> list[str]:
    """Fetch and parse the GRIB ``.idx`` file for a URL."""
    try:
        import requests  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError("HTTP backend requires the 'requests' extra") from exc

    from zyra.utils.grib import ensure_idx_path, parse_idx_lines

    idx_url = ensure_idx_path(url)
    attempt = 0
    last_exc = None
    while attempt < max_retries:
        try:
            r = requests.get(idx_url, timeout=timeout)
            r.raise_for_status()
            return parse_idx_lines(r.content)
        except Exception as e:  # pragma: no cover - simple retry wrapper
            last_exc = e
            attempt += 1
    if last_exc:
        raise last_exc
    return []


def download_byteranges(
    url: str, byte_ranges: Iterable[str], *, max_workers: int = 10, timeout: int = 60
) -> bytes:
    """Download multiple byte ranges and concatenate in the input order."""
    try:
        import requests  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError("HTTP backend requires the 'requests' extra") from exc

    def _ranged_get(u: str, range_header: str) -> bytes:
        headers = {"Range": range_header}
        r = requests.get(u, headers=headers, timeout=timeout)
        r.raise_for_status()
        return r.content

    from zyra.utils.grib import parallel_download_byteranges

    return parallel_download_byteranges(
        _ranged_get, url, byte_ranges, max_workers=max_workers
    )


def get_size(url: str, *, timeout: int = 60) -> int | None:
    """Return Content-Length for a URL via HTTP HEAD when provided."""
    try:
        import requests  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError("HTTP backend requires the 'requests' extra") from exc

    try:
        r = requests.head(url, timeout=timeout)
        r.raise_for_status()
        val = r.headers.get("Content-Length")
        return int(val) if val is not None else None
    except Exception:
        return None
