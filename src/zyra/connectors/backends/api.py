"""HTTP backend utilities for generic API ingestion.

Provides single-request helpers with retries as well as iterators for
cursor-, page-, and RFC 5988 Link-based pagination.
"""

# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations  # noqa: I001

import contextlib
import json
import time
from collections.abc import Iterator
from functools import lru_cache
from urllib.parse import urljoin, urlparse
from zyra.utils.json_tools import get_by_path

# Retry policy
# - 429 (Too Many Requests): back off when rate limited (honor Retry-After when present)
# - 500/502/503/504: transient server or gateway errors likely to succeed on retry
# Retries use exponential backoff with optional floor from "Retry-After" header.
RETRY_STATUS = {429, 500, 502, 503, 504}


@lru_cache(maxsize=1)
def _get_requests():  # pragma: no cover - import guard
    """Thread-safe, lazy import of the `requests` module.

    Uses an LRU cache (with internal locking) to safely memoize the import
    across threads, avoiding a mutable global.
    """
    try:
        import requests as _req  # type: ignore

        return _req
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
    # Defensive SSRF validation at backend layer (covers non-router callers)
    try:
        from zyra.utils.env import env as _env, env_bool as _env_bool  # noqa: I001

        def _cfg(name: str, default: str | None = None) -> str | None:
            return _env(
                name,
                _env(name.replace("API_", "MCP_"))
                if name.startswith("API_")
                else default,
            )

        def _https_only() -> bool:
            return bool(_env_bool("API_FETCH_HTTPS_ONLY", True))

        def _allowed_ports() -> set[int]:
            raw = (_cfg("API_FETCH_ALLOW_PORTS", "80,443") or "80,443").strip()
            out: set[int] = set()
            for p in raw.split(","):
                p = p.strip()
                if not p:
                    continue
                try:
                    out.add(int(p))
                except Exception:
                    continue
            return out or {80, 443}

        def _host_list(name: str) -> list[str]:
            raw = (_cfg(name) or "").strip()
            return [s.strip().lower() for s in raw.split(",") if s.strip()]

        def _is_public_ip(ip_str: str) -> bool:
            try:
                import ipaddress as _ip

                ip = _ip.ip_address(ip_str)
                bad = (
                    ip.is_private
                    or ip.is_loopback
                    or ip.is_link_local
                    or ip.is_multicast
                    or ip.is_reserved
                    or ip.is_unspecified
                )
                if ip.version == 4 and ip.exploded.startswith("169.254.169.254"):
                    bad = True
                return not bad
            except Exception:
                return False

        def _all_resolved_public(host: str, port: int | None) -> bool:
            try:
                import socket as _socket

                infos = _socket.getaddrinfo(host, port or 0)
                addrs: set[str] = set()
                for _family, _type, _proto, _canon, sockaddr in infos:
                    try:
                        if len(sockaddr) >= 1:
                            addrs.add(str(sockaddr[0]))
                    except Exception:
                        continue
                return bool(addrs) and all(_is_public_ip(a) for a in addrs)
            except Exception:
                return False

        def _host_allowed(host: str) -> bool:
            h = (host or "").lower()
            deny = _host_list("API_FETCH_DENY_HOSTS")
            if any(h.endswith(d) for d in deny):
                return False
            allow = _host_list("API_FETCH_ALLOW_HOSTS")
            return True if not allow else any(h.endswith(a) for a in allow)

        pr = urlparse(url)
        scheme = (pr.scheme or "").lower()
        if scheme not in {"http", "https"}:
            raise ValueError("Only http/https URLs are allowed")
        if _https_only() and scheme != "https":
            raise ValueError("HTTPS is required")
        if pr.username or pr.password:
            raise ValueError("Credentials in URL are not allowed")
        host = pr.hostname or ""
        if not host:
            raise ValueError("URL host is required")
        h_l = host.lower()
        is_example = h_l.endswith(".example") or h_l in {
            "example.com",
            "example.org",
            "example.net",
        }
        port = pr.port or (443 if scheme == "https" else 80)
        if port not in _allowed_ports():
            raise ValueError(f"Port {port} not permitted")
        if not _host_allowed(host):
            raise ValueError("Host is not permitted")
        if not is_example:
            try:
                import ipaddress as _ip

                _ip.ip_address(host)
                if not _is_public_ip(host):
                    raise ValueError("IP address is not publicly routable")
            except ValueError:
                if not _all_resolved_public(host, port):
                    raise ValueError(
                        "Destination resolves to a private network"
                    ) from None
    except Exception:
        # Propagate validation failures to caller
        raise

    # URL has been validated above; use the validated `url` directly below.

    requests = _get_requests()
    # Strip hop-by-hop headers to avoid header-based SSRF tricks
    from zyra.utils.http import strip_hop_headers as _strip

    _h = _strip(headers or {})
    # lgtm [py/ssrf]: URL has been validated against public networks,
    # allowed hosts/ports, credentials stripped, and redirects disabled above.
    resp = requests.request(  # codeql[py/ssrf]
        method.upper(),
        url,
        headers=_h,
        params=params or {},
        data=data,
        timeout=timeout,
        allow_redirects=False,
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
    # Enforce same-host pagination by default for Link headers
    base_host = (urlparse(url).hostname or "").lower()
    allow_cross = False
    try:
        from zyra.utils.env import env_bool as _env_bool  # defer import

        allow_cross = bool(_env_bool("API_FETCH_ALLOW_CROSS_HOST_LINKS", False))
    except Exception:
        allow_cross = False
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
        if not allow_cross:
            try:
                nh = (urlparse(cur_url).hostname or "").lower()
                if nh != base_host:
                    break
            except Exception:
                break
        # After the first page, use the link-provided URL without extra params
        send_params = None
