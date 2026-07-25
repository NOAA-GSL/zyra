# SPDX-License-Identifier: Apache-2.0
"""HTTP connector backend.

Provides functional helpers to fetch and list resources over HTTP(S), as well
as convenience utilities for GRIB workflows (``.idx`` parsing and byte-range
downloads) and Content-Length probing.

Functions are intentionally small and dependency-light so they can be used by
the CLI, pipelines, or higher-level wrappers without imposing heavy imports.
"""

from __future__ import annotations

import re
from typing import Any, Iterable
from urllib.parse import urljoin

from zyra.connectors.backends._retry import (
    DEFAULT_BASE_DELAY,
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_MAX_DELAY,
    with_retries,
)


def _retry_opts() -> dict[str, Any]:
    """Retry knobs, overridable per deployment without a code change."""
    from zyra.utils.env import env_int

    return {
        "max_attempts": env_int("HTTP_MAX_ATTEMPTS", DEFAULT_MAX_ATTEMPTS),
        "base_delay": DEFAULT_BASE_DELAY,
        "max_delay": DEFAULT_MAX_DELAY,
    }


def default_max_workers() -> int:
    """Concurrent ranged GETs per file.

    Ten per file is a lot of pressure on one prefix when a batch walks
    many files; lower it via ``ZYRA_HTTP_MAX_WORKERS`` where a source
    throttles aggressively.
    """
    from zyra.utils.env import env_int

    return max(1, env_int("HTTP_MAX_WORKERS", 10))


# Make a module-level "requests" attribute patchable in tests even when the
# optional dependency is not installed in the environment.
try:  # pragma: no cover - env dependent
    import requests as requests  # type: ignore
except Exception:  # pragma: no cover

    class _RequestsProxy:
        pass

    requests = _RequestsProxy()  # type: ignore


def fetch_bytes(
    url: str, *, timeout: int = 60, headers: dict[str, str] | None = None
) -> bytes:
    """Return the raw response body for a GET request.

    Parameters
    - url: HTTP(S) URL to fetch.
    - timeout: request timeout in seconds.
    """
    try:
        import requests  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError("HTTP backend requires the 'requests' extra") from exc

    def _get() -> bytes:
        r = requests.get(url, timeout=timeout, headers=headers)
        r.raise_for_status()
        return r.content

    return with_retries(_get, **_retry_opts())


def fetch_text(
    url: str, *, timeout: int = 60, headers: dict[str, str] | None = None
) -> str:
    """Return the response body as text for a GET request."""
    try:
        import requests  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError("HTTP backend requires the 'requests' extra") from exc

    r = requests.get(url, timeout=timeout, headers=headers)
    r.raise_for_status()
    return r.text


def fetch_json(url: str, *, timeout: int = 60, headers: dict[str, str] | None = None):
    """Return the parsed JSON body for a GET request."""
    try:
        import requests  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError("HTTP backend requires the 'requests' extra") from exc

    r = requests.get(url, timeout=timeout, headers=headers)
    r.raise_for_status()
    return r.json()


def post_data(
    url: str,
    data: bytes,
    *,
    timeout: int = 60,
    content_type: str | None = None,
    headers: dict[str, str] | None = None,
) -> int:
    """POST raw bytes to a URL and return the HTTP status code."""
    try:
        import requests  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError("HTTP backend requires the 'requests' extra") from exc

    final_headers = dict(headers or {})
    if content_type and "Content-Type" not in final_headers:
        final_headers["Content-Type"] = content_type
    r = requests.post(
        url,
        data=data,
        headers=final_headers or None,
        timeout=timeout,
    )
    r.raise_for_status()
    return r.status_code


def post_bytes(
    url: str,
    data: bytes,
    *,
    timeout: int = 60,
    content_type: str | None = None,
    headers: dict[str, str] | None = None,
) -> int:
    """Backward-compat wrapper for ``post_data``."""
    return post_data(
        url,
        data,
        timeout=timeout,
        content_type=content_type,
        headers=headers,
    )


def list_files(
    url: str,
    pattern: str | None = None,
    *,
    timeout: int = 60,
    headers: dict[str, str] | None = None,
) -> list[str]:
    """Best-effort directory listing by scraping anchor tags on index pages.

    Returns absolute URLs; optionally filters them via regex ``pattern``.
    """
    try:
        import requests  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError("HTTP backend requires the 'requests' extra") from exc

    r = requests.get(url, timeout=timeout, headers=headers)
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


def get_idx_lines(
    url: str,
    *,
    timeout: int = 60,
    max_retries: int = 3,
    headers: dict[str, str] | None = None,
) -> list[str]:
    """Fetch and parse the GRIB ``.idx`` file for a URL."""
    try:
        import requests  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError("HTTP backend requires the 'requests' extra") from exc

    from zyra.utils.grib import ensure_idx_path, parse_idx_lines

    idx_url = ensure_idx_path(url)

    def _get() -> list[str]:
        r = requests.get(idx_url, timeout=timeout, headers=headers)
        r.raise_for_status()
        return parse_idx_lines(r.content)

    # max_retries is retained as the public knob; it previously meant
    # "attempts with no delay between them", which made throttling worse.
    opts = _retry_opts()
    opts["max_attempts"] = max(1, int(max_retries))
    return with_retries(_get, **opts)


def download_byteranges(
    url: str,
    byte_ranges: Iterable[str],
    *,
    max_workers: int | None = None,
    timeout: int = 60,
    headers: dict[str, str] | None = None,
) -> bytes:
    """Download multiple byte ranges and concatenate in the input order."""
    try:
        import requests  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError("HTTP backend requires the 'requests' extra") from exc

    base_headers = dict(headers or {})

    def _ranged_get(u: str, range_header: str) -> bytes:
        request_headers = dict(base_headers)
        request_headers["Range"] = range_header

        def _get() -> bytes:
            r = requests.get(u, headers=request_headers, timeout=timeout)
            r.raise_for_status()
            return r.content

        return with_retries(_get, **_retry_opts())

    from zyra.utils.grib import parallel_download_byteranges

    return parallel_download_byteranges(
        _ranged_get,
        url,
        byte_ranges,
        max_workers=default_max_workers() if max_workers is None else max_workers,
    )


def get_size(
    url: str, *, timeout: int = 60, headers: dict[str, str] | None = None
) -> int | None:
    """Return Content-Length for a URL via HTTP HEAD when provided."""
    try:
        import requests  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError("HTTP backend requires the 'requests' extra") from exc

    try:
        r = requests.head(url, timeout=timeout, headers=headers)
        r.raise_for_status()
        val = r.headers.get("Content-Length")
        return int(val) if val is not None else None
    except (requests.RequestException, ValueError, TypeError):
        return None
