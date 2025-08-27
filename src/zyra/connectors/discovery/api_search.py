"""Federated API search helpers used by ``zyra search api``.

Overview
- Discovers a remote API's search endpoint via OpenAPI when available and
  falls back to ``/search``. Supports overriding endpoint/param names.
- Issues GET or POST requests, passes additional query params/headers,
  applies retries and parallelizes across sources.
- Normalizes heterogeneous responses to a unified row schema for aggregation.

Normalized row schema
- ``source``: host of the API base URL (e.g., ``zyra.noaa.gov``)
- ``dataset``: dataset title or name
- ``description``: short description if available
- ``link``: canonical link/URI to the dataset/service

Key entry points
- :func:`query_single_api` — query one API base URL.
- :func:`federated_api_search` — aggregate across multiple base URLs with
  concurrency and retries.
- :func:`print_openapi_info` — show discovered endpoint and query parameters.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable
from urllib.parse import urljoin, urlparse

from zyra.connectors.backends import http as http_backend


def _ensure_requests() -> None:
    import importlib.util as _ilu

    if _ilu.find_spec("requests") is None:  # pragma: no cover - env dependent
        raise RuntimeError(
            "HTTP client requires the 'requests' extra. Install with: "
            "poetry install -E connectors"
        )


@dataclass
class APISearchSpec:
    path: str  # e.g., /search
    query_param: str = "q"  # prefer `q`, fallback to `query`


def _load_openapi(base_url: str) -> dict[str, Any] | None:
    """Load an OpenAPI spec from common locations.

    Attempts ``{base}/openapi.json`` and ``{base}/docs/openapi.json`` and
    returns the first successful document that looks like an OpenAPI spec.
    Returns ``None`` when not available.
    """
    bases = [
        base_url.rstrip("/") + "/openapi.json",
        base_url.rstrip("/") + "/docs/openapi.json",
    ]
    for u in bases:
        try:
            spec = http_backend.fetch_json(u)
            if isinstance(spec, dict) and spec.get("paths"):
                return spec  # type: ignore[return-value]
        except Exception:
            continue
    return None


def _discover_search_spec(base_url: str) -> APISearchSpec:
    """Infer search endpoint and query parameter name from OpenAPI.

    - Prefers the shortest path containing ``/search`` that exposes a GET
      operation; picks the query parameter named ``q`` or ``query`` when
      present (prefers ``q``).
    - Falls back to ``/search`` with ``q`` when OpenAPI is absent.
    """
    spec = _load_openapi(base_url)
    if spec and isinstance(spec.get("paths"), dict):
        paths: dict[str, Any] = spec["paths"]
        candidates: list[tuple[str, dict[str, Any]]] = []
        for path, ops in paths.items():
            if not isinstance(path, str) or not isinstance(ops, dict):
                continue
            if "search" in path.lower() and any(str(k).lower() == "get" for k in ops):
                candidates.append((path, ops))
        # Prefer the shortest path containing /search
        candidates.sort(key=lambda t: len(t[0]))
        for path, ops in candidates:
            get = None
            for k, v in ops.items():
                if str(k).lower() == "get" and isinstance(v, dict):
                    get = v
                    break
            if not get:
                continue
            params = get.get("parameters") or []
            q_name = None
            if isinstance(params, list):
                names = [str(p.get("name")) for p in params if isinstance(p, dict)]
                if "q" in names:
                    q_name = "q"
                elif "query" in names:
                    q_name = "query"
            return APISearchSpec(path=path, query_param=q_name or "q")
    # Fallback
    return APISearchSpec(path="/search", query_param="q")


def print_openapi_info(
    base_url: str, *, suggest: bool = False, verbose: bool = False
) -> None:
    """Print discovered endpoint/param; optionally suggest query flags.

    Parameters
    - base_url: API base URL, e.g., ``https://host/api``.
    - suggest: when True, list simple query parameter names from the GET op.
    - verbose: when True, logs errors to stderr.
    """
    try:
        host = urlparse(base_url).netloc or base_url
        spec = _load_openapi(base_url)
        if not spec:
            print(f"[zyra.search.api] {host} openapi: not found")
            return
        s = _discover_search_spec(base_url)
        print(f"[zyra.search.api] {host} endpoint={s.path} query_param={s.query_param}")
        if suggest:
            paths = spec.get("paths") or {}
            ops = paths.get(s.path) or {}
            get = None
            for k, v in ops.items():
                if str(k).lower() == "get" and isinstance(v, dict):
                    get = v
                    break
            names: list[str] = []
            if get and isinstance(get.get("parameters"), list):
                for p in get["parameters"]:
                    if isinstance(p, dict) and p.get("in") == "query" and p.get("name"):
                        names.append(str(p.get("name")))
            if names:
                print(
                    f"[zyra.search.api] {host} suggest --param for: " + ",".join(names)
                )
    except Exception:
        if verbose:
            try:
                import sys

                print(f"[zyra.search.api] {base_url} openapi: error", file=sys.stderr)
            except Exception:
                pass


def _parse_kv_list(items: Iterable[str] | None) -> dict[str, str]:
    """Parse ``k=v`` items into a dictionary, ignoring malformed entries."""
    out: dict[str, str] = {}
    if not items:
        return out
    for raw in items:
        if raw is None:
            continue
        s = str(raw)
        if "=" in s:
            k, v = s.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def _parse_json_body(arg: str | None) -> Any | None:
    """Parse JSON body from raw string or ``@/path.json`` reference.

    Returns the parsed object or ``None`` on failure.
    """
    if not arg:
        return None
    try:
        if arg.startswith("@"):
            from pathlib import Path

            return __import__("json").loads(Path(arg[1:]).read_text(encoding="utf-8"))
        return __import__("json").loads(arg)
    except Exception:
        return None


def _normalize_item(item: dict[str, Any], source_host: str) -> dict[str, Any]:
    """Map remote item to unified row schema.

    Attempts common fields used by Zyra and similar APIs; uses best-effort
    heuristics for generic sources.
    """
    # Preferred keys (Zyra API shape)
    name = (
        item.get("name") or item.get("title") or item.get("dataset") or item.get("id")
    )
    desc = item.get("description") or item.get("abstract") or None
    link = item.get("uri") or item.get("link") or item.get("url") or None
    # Strings only
    name_s = str(name) if name is not None else None
    desc_s = str(desc) if desc is not None else None
    link_s = str(link) if link is not None else None
    return {
        "source": source_host,
        "dataset": name_s or "",
        "description": desc_s,
        "link": link_s or "",
    }


def query_single_api(
    base_url: str,
    query: str,
    *,
    limit: int = 10,
    verbose: bool = False,
    params: Iterable[str] | None = None,
    headers: Iterable[str] | None = None,
    timeout: float = 30.0,
    retries: int = 0,
    no_openapi: bool = False,
    endpoint: str | None = None,
    qp_name: str | None = None,
    result_key: str | None = None,
    use_post: bool = False,
    json_params: Iterable[str] | None = None,
    json_body: str | None = None,
) -> list[dict[str, Any]]:
    """Query a single API and return normalized rows."""
    host = urlparse(base_url).netloc or base_url
    spec = (
        APISearchSpec(path="/search", query_param="q")
        if no_openapi
        else _discover_search_spec(base_url)
    )
    _ensure_requests()
    # Attempt via discovered or overridden endpoint with params first
    url = urljoin(base_url.rstrip("/") + "/", (endpoint or spec.path).lstrip("/"))
    qp = qp_name or spec.query_param
    qparams = {qp: query, "limit": int(limit)}
    qparams.update(_parse_kv_list(params))
    hdrs = _parse_kv_list(headers)
    data = None
    attempts = max(1, int(retries or 0) + 1)
    for _ in range(attempts):
        try:
            import requests  # type: ignore

            if use_post:
                body = _parse_json_body(json_body)
                if body is None:
                    body = _parse_kv_list(json_params)
                if not isinstance(body, dict):
                    body = {"query": query, "limit": int(limit)}
                r = requests.post(url, json=body, headers=hdrs or None, timeout=timeout)
            else:
                r = requests.get(
                    url, params=qparams, headers=hdrs or None, timeout=timeout
                )
            r.raise_for_status()
            data = r.json()
            break
        except Exception:
            data = None

    # If response shape is not directly consumable, try common fallbacks
    def _coerce_seq(payload: Any) -> list[Any] | None:
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            for key in ((result_key,) if result_key else tuple()) + (
                "items",
                "results",
                "data",
            ):
                v = payload.get(key)
                if isinstance(v, list):
                    return v
        return None

    seq_any = _coerce_seq(data) if data is not None else None
    if verbose:
        try:
            import sys

            print(
                f"[zyra.search.api] {host} -> {url} params={qparams} shape={type(data).__name__}",
                file=sys.stderr,
            )
        except Exception:
            pass

    if seq_any is None:
        # Fallback tries: alternate param name and default /search path
        for qp_eff in (qp, "q", "query"):
            try:
                import requests  # type: ignore

                r = requests.get(
                    base_url.rstrip("/") + "/search",
                    params={qp_eff: query, "limit": int(limit)},
                    headers=hdrs or None,
                    timeout=timeout,
                )
                r.raise_for_status()
                payload = r.json()
                seq_any = _coerce_seq(payload)
                if verbose:
                    try:
                        import sys

                        print(
                            f"[zyra.search.api] {host} fallback /search qp={qp_eff} shape={type(payload).__name__}",
                            file=sys.stderr,
                        )
                    except Exception:
                        pass
                if seq_any is not None:
                    break
            except Exception:
                continue
    items: list[dict[str, Any]] = []
    # Use coerced sequence if available, else empty
    seq = seq_any if isinstance(seq_any, list) else []
    for it in seq[: max(0, int(limit)) or None]:
        if isinstance(it, dict):
            items.append(_normalize_item(it, host))
    return items


def federated_api_search(
    urls: list[str],
    query: str,
    *,
    limit: int = 10,
    verbose: bool = False,
    params: Iterable[str] | None = None,
    headers: Iterable[str] | None = None,
    timeout: float = 30.0,
    retries: int = 0,
    concurrency: int = 4,
    no_openapi: bool = False,
    endpoint: str | None = None,
    qp_name: str | None = None,
    result_key: str | None = None,
    use_post: bool = False,
    json_params: Iterable[str] | None = None,
    json_body: str | None = None,
) -> list[dict[str, Any]]:
    """Aggregate normalized rows across multiple base URLs.

    Issues requests in parallel using a bounded thread pool and merges results.
    See :func:`query_single_api` for parameter semantics.
    """
    # Ensure HTTP client available up front to avoid silent empties
    _ensure_requests()
    rows: list[dict[str, Any]] = []
    from concurrent.futures import ThreadPoolExecutor, as_completed

    max_workers = max(1, int(concurrency or 1))
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {
            ex.submit(
                query_single_api,
                u,
                query,
                limit=limit,
                verbose=verbose,
                params=params,
                headers=headers,
                timeout=timeout,
                retries=retries,
                no_openapi=no_openapi,
                endpoint=endpoint,
                qp_name=qp_name,
                result_key=result_key,
                use_post=use_post,
                json_params=json_params,
                json_body=json_body,
            ): u
            for u in urls
        }
        for fut in as_completed(futs):
            try:
                rows.extend(fut.result())
            except Exception as e:
                if verbose:
                    try:
                        import sys

                        print(
                            f"[zyra.search.api] {futs[fut]} failed: {e}",
                            file=sys.stderr,
                        )
                    except Exception:
                        pass
    return rows


def print_api_table(
    rows: list[dict[str, Any]], *, fields: list[str] | None = None
) -> None:
    """Pretty-print normalized rows as a compact fixed-width table.

    Parameters
    - rows: list of normalized mapping rows.
    - fields: override column order/selection; defaults to
      ``["source", "dataset", "link"]``.
    """
    headers = fields or ["source", "dataset", "link"]
    caps = {k: 28 for k in headers}
    if "dataset" in caps:
        caps["dataset"] = 40
    if "link" in caps:
        caps["link"] = 60

    def fit(val: str, w: int) -> str:
        return val if len(val) <= w else val[: max(0, w - 1)] + "\u2026"

    # Compute widths
    widths = {k: len(k) for k in headers}
    for r in rows:
        for k in headers:
            v = str(r.get(k) or "")
            widths[k] = min(max(widths[k], len(v)), caps[k])
    # Header
    line = "  ".join(fit(k, widths[k]).ljust(widths[k]) for k in headers)
    print(line)
    print("  ".join("-" * widths[k] for k in headers))
    # Rows
    for r in rows:
        vals = [str(r.get(k) or "") for k in headers]
        print(
            "  ".join(
                fit(vals[i], widths[headers[i]]).ljust(widths[headers[i]])
                for i in range(len(headers))
            )
        )
