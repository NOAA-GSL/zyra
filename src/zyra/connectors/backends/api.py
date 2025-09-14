"""HTTP backend utilities for generic API ingestion.

Provides single-request helpers with retries as well as iterators for
cursor-, page-, and RFC 5988 Link-based pagination.
"""

# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import contextlib
import json
import time
from collections.abc import Iterator
from typing import Any
from urllib.parse import urljoin

RETRY_STATUS = {429, 500, 502, 503, 504}


_REQUESTS: Any | None = None


def _import_requests():  # pragma: no cover - import guard
    """Import and cache the `requests` module lazily.

    Avoids repeated imports when helpers are called frequently. Keeps this
    backend import-light for environments that don't use HTTP connectors.
    """
    global _REQUESTS
    if _REQUESTS is not None:
        return _REQUESTS
    try:
        import requests as _req  # type: ignore

        _REQUESTS = _req
        return _REQUESTS
    except Exception as exc:  # pragma: no cover - runtime error path
        raise RuntimeError(
            "The 'requests' package is required for 'zyra acquire api'. Install extras: 'pip install \"zyra[connectors]\"'"
        ) from exc


def _parse_retry_after(value: str) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def request_once(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, str] | None = None,
    data: bytes | str | dict[str, object] | None = None,
    timeout: int = 60,
) -> tuple[int, dict[str, str], bytes]:
    requests = _import_requests()
    resp = requests.request(
        method.upper(),
        url,
        headers=headers or {},
        params=params or {},
        data=data,
        timeout=timeout,
    )
    status = resp.status_code
    # Flatten headers to str->str
    headers_out: dict[str, str] = {k: v for k, v in resp.headers.items()}
    content = resp.content or b""
    return status, headers_out, content


def request_with_retries(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, str] | None = None,
    data: bytes | str | dict[str, object] | None = None,
    timeout: int = 60,
    max_retries: int = 3,
    retry_backoff: float = 0.5,
) -> tuple[int, dict[str, str], bytes]:
    attempt = 0
    while True:
        status, resp_headers, content = request_once(
            method, url, headers=headers, params=params, data=data, timeout=timeout
        )
        if status not in RETRY_STATUS or attempt >= max_retries:
            return status, resp_headers, content
        delay = retry_backoff * (2**attempt)
        if "Retry-After" in resp_headers:
            with contextlib.suppress(Exception):
                delay = max(delay, _parse_retry_after(resp_headers["Retry-After"]))
        time.sleep(delay)
        attempt += 1


def _json_loads(data: bytes) -> object:
    try:
        return json.loads(data.decode("utf-8"))
    except Exception:
        return None


def get_by_path(obj: object, path: str) -> object:
    cur = obj
    for part in (path or "").split(".") if path else []:
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def paginate_cursor(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, str] | None = None,
    data: bytes | str | dict[str, object] | None = None,
    timeout: int = 60,
    max_retries: int = 3,
    retry_backoff: float = 0.5,
    cursor_param: str = "cursor",
    next_cursor_json_path: str = "next",
) -> Iterator[tuple[int, dict[str, str], bytes]]:
    next_cursor: str | None = None
    base_params = dict(params or {})
    while True:
        p = dict(base_params)
        if next_cursor:
            p[cursor_param] = next_cursor
        status, resp_headers, content = request_with_retries(
            method,
            url,
            headers=headers,
            params=p,
            data=data,
            timeout=timeout,
            max_retries=max_retries,
            retry_backoff=retry_backoff,
        )
        yield status, resp_headers, content
        body = _json_loads(content)
        if status >= 400:
            break
        if body is None:
            break
        candidate = get_by_path(body, next_cursor_json_path)
        next_cursor = candidate if isinstance(candidate, str) and candidate else None
        if not next_cursor:
            break


def paginate_page(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, str] | None = None,
    data: bytes | str | dict[str, object] | None = None,
    timeout: int = 60,
    max_retries: int = 3,
    retry_backoff: float = 0.5,
    page_param: str = "page",
    page_start: int = 1,
    page_size_param: str | None = None,
    page_size: int | None = None,
    empty_json_path: str | None = None,
    max_pages: int = 1000,
) -> Iterator[tuple[int, dict[str, str], bytes]]:
    page = page_start
    base = dict(params or {})
    pages = 0
    while pages < max_pages:
        p = dict(base)
        p[page_param] = str(page)
        if page_size_param and page_size:
            p[page_size_param] = str(page_size)
        status, resp_headers, content = request_with_retries(
            method,
            url,
            headers=headers,
            params=p,
            data=data,
            timeout=timeout,
            max_retries=max_retries,
            retry_backoff=retry_backoff,
        )
        yield status, resp_headers, content
        if status >= 400:
            break
        obj = _json_loads(content)
        if obj is None:
            break
        seq = obj
        if empty_json_path:
            seq = get_by_path(obj, empty_json_path)
        # Stop when empty list is observed
        if isinstance(seq, list) and len(seq) == 0:
            break
        pages += 1
        page += 1


def _parse_link_header(link_value: str, want_rel: str = "next") -> str | None:
    """Return the URL for a relation in an RFC 5988 Link header.

    Parameters
    - link_value: The raw ``Link`` header value.
    - want_rel: The relation to extract (e.g., ``"next"``, ``"prev"``).

    Returns the URL string when found, else ``None``.

    Example:
        ``Link: <https://api.example/items?page=2>; rel="next", <...>; rel="prev"``
    """
    if not link_value:
        return None
    try:
        parts = [p.strip() for p in link_value.split(",") if p.strip()]
        want = want_rel.strip().lower()
        for p in parts:
            if not p.startswith("<") or ">" not in p:
                continue
            url_part, rest = p.split(">", 1)
            url = url_part.lstrip("<").strip()
            attrs = rest.split(";")
            for a in attrs:
                a = a.strip()
                if not a:
                    continue
                if a.lower().startswith("rel="):
                    rel_val = a.split("=", 1)[1].strip().strip('"')
                    if rel_val.lower() == want:
                        return url
    except Exception:
        return None
    return None


def paginate_link(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, str] | None = None,
    data: bytes | str | dict[str, object] | None = None,
    timeout: int = 60,
    max_retries: int = 3,
    retry_backoff: float = 0.5,
    link_rel: str = "next",
) -> Iterator[tuple[int, dict[str, str], bytes]]:
    """Iterate pages by following RFC 5988 ``Link: ...; rel="next"`` headers.

    - Resolves relative links against the current URL.
    - Sends ``params`` only on the initial request; subsequent requests use the
      URL provided in the Link header unmodified.
    """
    cur_url = url
    send_params: dict[str, str] | None = dict(params or {})
    while True:
        status, resp_headers, content = request_with_retries(
            method,
            cur_url,
            headers=headers,
            params=send_params,
            data=data,
            timeout=timeout,
            max_retries=max_retries,
            retry_backoff=retry_backoff,
        )
        yield status, resp_headers, content
        if status >= 400:
            break
        link_val = resp_headers.get("Link") or resp_headers.get("link") or ""
        next_url = _parse_link_header(link_val, want_rel=link_rel)
        if not next_url:
            break
        # Resolve relative next URL against the current URL
        cur_url = urljoin(cur_url, next_url)
        # After the first page, use the link-provided URL without extra params
        send_params = None
