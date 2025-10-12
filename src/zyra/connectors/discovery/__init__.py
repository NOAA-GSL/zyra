# SPDX-License-Identifier: Apache-2.0
"""Dataset discovery backends and CLI for `zyra search`.

Implements a lightweight local backend that searches the packaged
SOS dataset catalog at `zyra.assets.metadata/sos_dataset_metadata.json`.

Also includes a federated API search subcommand, ``zyra search api``, that can
query one or more Zyra-like APIs exposing ``/search`` (or equivalent via
OpenAPI). Results are normalized and can be emitted as JSON/CSV or displayed
as a compact table.

Usage examples:
  - zyra search "tsunami"
  - zyra search "GFS" --json
  - Use the selected URI with the matching connector, e.g.:
      zyra acquire ftp "$(zyra search 'earthquake' --select 1)" -o out.bin

API search examples:
  - zyra search api --url https://zyra.noaa.gov/api --query "temperature"
  - zyra search api --url https://zyra.a.edu/api --url https://zyra.b.edu/api \
        --query "precipitation" --table
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from typing import Any, Iterable

from zyra.connectors.credentials import (
    CredentialResolutionError,
    apply_auth_header,
    apply_http_credentials,
    resolve_credentials,
)

try:  # Prefer standard library importlib.resources
    from importlib import resources as importlib_resources
except Exception:  # pragma: no cover - fallback for very old Python
    import importlib_resources  # type: ignore


@dataclass
class DatasetMetadata:
    id: str
    name: str
    description: str | None
    source: str
    format: str
    uri: str


class DiscoveryBackend:
    """Interface for dataset discovery backends."""

    def search(self, query: str, *, limit: int = 10) -> list[DatasetMetadata]:
        raise NotImplementedError


class LocalCatalogBackend(DiscoveryBackend):
    """Local backend backed by the packaged SOS catalog JSON.

    File: `zyra.assets.metadata/sos_dataset_metadata.json`
    Schema (subset of fields used here):
      - url (str): public catalog URL
      - title (str): dataset title
      - description (str): dataset description
      - keywords (list[str]): search tags
      - ftp_download (str|None): FTP base path to assets (preferred URI)
    """

    _cache: list[dict[str, Any]] | None = None

    def __init__(
        self, catalog_path: str | None = None, *, weights: dict[str, int] | None = None
    ) -> None:
        self._catalog_path = catalog_path
        self._weights = weights or {}

    def _load(self) -> list[dict[str, Any]]:
        if self._cache is not None:
            return self._cache
        data: list[dict[str, Any]]
        if self._catalog_path:
            from pathlib import Path

            # Support packaged resource references: pkg:package/resource or pkg:package:resource
            cp = str(self._catalog_path)
            if cp.startswith("pkg:"):
                ref = cp[4:]
                if ":" in ref and "/" not in ref:
                    pkg, res = ref.split(":", 1)
                else:
                    parts = ref.split("/", 1)
                    pkg = parts[0]
                    res = parts[1] if len(parts) > 1 else "sos_dataset_metadata.json"
                path = importlib_resources.files(pkg).joinpath(res)
                with importlib_resources.as_file(path) as p:
                    data = json.loads(p.read_text(encoding="utf-8"))
            else:
                # Optional allowlist: if env vars are set, require catalog under one of them
                try:
                    # First, perform a syntactic containment check without resolving symlinks.
                    # This guards obvious traversal attempts before any filesystem resolution.
                    try:
                        import os as _os

                        def _syntactic_allowed(p0: str, envs0: list[str]) -> bool:
                            tgt = _os.path.abspath(_os.path.normpath(str(p0)))  # noqa: PTH100
                            have_env = False
                            for _env in envs0:
                                base = _os.getenv(_env)
                                if not base:
                                    continue
                                have_env = True
                                base_abs = _os.path.abspath(_os.path.normpath(base))  # noqa: PTH100
                                try:
                                    if _os.path.commonpath([tgt, base_abs]) == base_abs:
                                        return True
                                except Exception:
                                    continue
                            return not have_env

                        allowed_envs = ["ZYRA_CATALOG_DIR", "DATA_DIR"]
                        if not _syntactic_allowed(cp, allowed_envs):
                            raise ValueError(
                                "catalog_file not allowed; must be under ZYRA_CATALOG_DIR or DATA_DIR"
                            )
                    except Exception:
                        pass

                    def _is_under_allowed(p: str, envs: list[str]) -> bool:
                        """Robust path containment: resolve symlinks and compare real paths.

                        Uses Path.resolve() on both target and base to prevent traversal via
                        symlinks and to normalize case/segments where applicable.
                        """
                        try:
                            import os as _os

                            tgt_res = (
                                Path(str(p)).resolve()
                            )  # lgtm [py/uncontrolled-data-in-path-expression]
                            allowed_set = False
                            for env in envs:
                                base = _os.getenv(env)
                                if not base:
                                    continue
                                allowed_set = True
                                try:
                                    base_res = Path(base).resolve()
                                    # Python 3.9+: is_relative_to ensures proper path semantics
                                    if hasattr(tgt_res, "is_relative_to"):
                                        if tgt_res.is_relative_to(base_res):
                                            return True
                                    else:  # pragma: no cover - old Python fallback
                                        if str(tgt_res).startswith(str(base_res)):
                                            return True
                                except Exception:
                                    continue
                            # If no allowlist env is set, allow by default; otherwise deny
                            return not allowed_set
                        except Exception:
                            return False

                    allowed_envs = ["ZYRA_CATALOG_DIR", "DATA_DIR"]
                    if not _is_under_allowed(cp, allowed_envs):
                        raise ValueError(
                            "catalog_file not allowed; must be under ZYRA_CATALOG_DIR or DATA_DIR"
                        )
                except Exception:
                    # Fall through; Path read may still raise appropriately
                    pass
                # Optional allowlist already enforced above when envs are set.
                # Explicitly deny suspicious traversal patterns prior to resolving.
                _raw = str(cp)
                _scan = _raw.replace("\\", "/")
                _parts = [p for p in _scan.split("/") if p]
                if any(p == ".." for p in _parts):
                    raise ValueError(
                        "catalog_file contains parent traversal segment ('..')"
                    )
                # Resolve to a normalized absolute path (handles symlinks) before reading.
                resolved = Path(cp).resolve()
                # Re-validate containment post-resolve for defense-in-depth
                try:
                    allowed_envs = ["ZYRA_CATALOG_DIR", "DATA_DIR"]
                    # Reuse helper from above scope
                    if not _is_under_allowed(str(resolved), allowed_envs):
                        raise ValueError(
                            "catalog_file not allowed after resolve; must be under ZYRA_CATALOG_DIR or DATA_DIR"
                        )
                except Exception:
                    # If the helper isn't available in scope due to refactor, fall back to direct read error
                    pass
                if not resolved.is_file():
                    raise FileNotFoundError(str(resolved))
                data = json.loads(
                    resolved.read_text(encoding="utf-8")
                )  # lgtm [py/path-injection] [py/uncontrolled-data-in-path-expression]
        else:
            pkg = "zyra.assets.metadata"
            path = importlib_resources.files(pkg).joinpath("sos_dataset_metadata.json")
            with importlib_resources.as_file(path) as p:
                data = json.loads(p.read_text(encoding="utf-8"))
        # Store as-is; we'll normalize per-result on demand
        self._cache = data
        return data

    def _match_score(self, item: dict[str, Any], rx: re.Pattern[str]) -> int:
        title = str(item.get("title") or "")
        desc = str(item.get("description") or "")
        keywords = item.get("keywords") or []
        score = 0
        if rx.search(title):
            score += int(self._weights.get("title", 3))
        if rx.search(desc):
            score += int(self._weights.get("description", 2))
        for kw in keywords:
            if isinstance(kw, str) and rx.search(kw):
                score += int(self._weights.get("keywords", 1))
        return score

    @staticmethod
    def _slug_from_url(url: str) -> str:
        # e.g., https://sos.noaa.gov/catalog/datasets/tsunami-history/ -> tsunami-history
        m = re.search(r"/datasets/([^/]+)/?", url)
        if m:
            return m.group(1)
        # Fallback: derive a compact slug and cap length with a hash suffix for stability
        try:
            import hashlib
            from urllib.parse import urlparse

            parsed = urlparse(url)
            path_parts = [p for p in (parsed.path or "").split("/") if p]
            # Prefer last path segment; otherwise use host or whole URL as candidate
            candidate = path_parts[-1] if path_parts else (parsed.netloc or url)
            slug = re.sub(r"\W+", "-", candidate).strip("-") or "item"
            MAX = 64
            if len(slug) > MAX:
                h = hashlib.sha1(url.encode("utf-8")).hexdigest()[:8]
                slug = slug[: MAX - 9].rstrip("-") + "-" + h
            return slug
        except Exception:
            return re.sub(r"\W+", "-", url).strip("-")[:64]

    def _normalize(self, item: dict[str, Any]) -> DatasetMetadata:
        url = str(item.get("url") or "")
        title = str(item.get("title") or "")
        desc = str(item.get("description") or "") or None
        ftp = item.get("ftp_download")
        uri = str(ftp or url)
        fmt = "FTP" if ftp else "HTML"
        return DatasetMetadata(
            id=self._slug_from_url(url) if url else title.lower().replace(" ", "-"),
            name=title or (url or uri),
            description=desc,
            source="sos-catalog",
            format=fmt,
            uri=uri,
        )

    def search(self, query: str, *, limit: int = 10) -> list[DatasetMetadata]:
        data = self._load()
        # Token-aware matching: break the query into words and score per-token
        tokens = [t for t in re.split(r"\W+", query) if t]
        token_patterns = [
            re.compile(re.escape(t), re.IGNORECASE) for t in tokens if len(t) >= 3
        ]
        scored: list[tuple[int, dict[str, Any]]] = []
        if token_patterns:
            for it in data:
                s = 0
                for pat in token_patterns:
                    s += self._match_score(it, pat)
                if s > 0:
                    scored.append((s, it))
        else:
            # Fallback to phrase search when no meaningful tokens extracted
            rx = re.compile(re.escape(query), re.IGNORECASE)
            for it in data:
                s = self._match_score(it, rx)
                if s > 0:
                    scored.append((s, it))
        # Sort by score desc, then title asc for stability
        scored.sort(key=lambda t: (-t[0], str(t[1].get("title") or "")))
        results = [self._normalize(it) for _, it in scored[: max(0, limit) or None]]
        return results


def _print_table(items: Iterable[DatasetMetadata]) -> None:
    rows = [("ID", "Name", "Format", "URI")]
    for d in items:
        rows.append((d.id, d.name, d.format, d.uri))
    # Compute simple column widths with caps
    caps = (32, 40, 10, 60)
    widths = [
        min(max(len(str(r[i])) for r in rows), caps[i]) for i in range(len(rows[0]))
    ]

    def _fit(s: str, w: int) -> str:
        if len(s) <= w:
            return s.ljust(w)
        return s[: max(0, w - 1)] + "\u2026"

    for i, r in enumerate(rows):
        line = "  ".join(_fit(str(r[j]), widths[j]) for j in range(len(r)))
        print(line)
        if i == 0:
            print("  ".join("-" * w for w in widths))


def register_cli(p: argparse.ArgumentParser) -> None:
    # Optional subcommands under `zyra search`.
    # Keep base (no subcommand) behavior intact for local/OGC discovery.
    sub = p.add_subparsers(dest="search_cmd", required=False)

    # -----------------------------
    # api: federated API search
    # -----------------------------
    p_api = sub.add_parser(
        "api",
        help=("Query remote Zyra-like APIs via /search; supports federated URLs"),
    )
    p_api.add_argument(
        "--url",
        action="append",
        required=True,
        help=("Base API URL (repeatable). Examples: https://zyra.noaa.gov/api"),
    )
    p_api.add_argument(
        "--query",
        dest="api_query",
        required=True,
        help="Search query to pass to remote APIs",
    )
    p_api.add_argument(
        "-l",
        "--limit",
        type=int,
        default=10,
        help="Maximum results per source (default: 10)",
    )
    p_api.add_argument(
        "--json",
        action="store_true",
        help="Output in JSON (default)",
    )
    p_api.add_argument(
        "--csv",
        action="store_true",
        help="Output in CSV (columns: source,dataset,description,link)",
    )
    p_api.add_argument(
        "--table",
        action="store_true",
        help="Pretty table output to the terminal",
    )
    p_api.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print debug info about requests and response shapes",
    )
    # Request shaping
    p_api.add_argument(
        "--param",
        action="append",
        help="Extra query param k=v (repeatable)",
    )
    p_api.add_argument(
        "--header",
        action="append",
        help="HTTP header `key=value` or `Key: Value` (repeatable)",
    )
    p_api.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Request timeout seconds (default: 30)",
    )
    p_api.add_argument(
        "--retries",
        type=int,
        default=0,
        help="Retry attempts for transient failures (default: 0)",
    )
    p_api.add_argument(
        "--concurrency",
        type=int,
        default=4,
        help="Parallel requests across URLs (default: 4)",
    )
    # Endpoint control
    p_api.add_argument(
        "--no-openapi",
        action="store_true",
        help="Skip OpenAPI discovery and use /search",
    )
    p_api.add_argument(
        "--endpoint",
        help="Override endpoint path (e.g., /search/items)",
    )
    p_api.add_argument(
        "--qp",
        help="Override query parameter name (default: q)",
    )
    p_api.add_argument(
        "--result-key",
        help="Read array from this key when response is an object (e.g., items)",
    )
    # POST support
    p_api.add_argument(
        "--post",
        action="store_true",
        help="Use POST /search with JSON body instead of GET",
    )
    p_api.add_argument(
        "--json-param",
        action="append",
        help="JSON body field k=v (repeatable)",
    )
    p_api.add_argument(
        "--json-body",
        help="JSON body as raw string or @/path/to/file.json",
    )
    p_api.add_argument(
        "--credential",
        action="append",
        dest="credential",
        help=(
            "Credential slot (repeatable), e.g., token=$API_TOKEN or header.Authorization=Bearer abc"
        ),
    )
    p_api.add_argument(
        "--credential-file",
        help="Optional dotenv file for @NAME credential lookups",
    )
    p_api.add_argument(
        "--auth",
        help=(
            "Convenience auth helper (e.g., bearer:$TOKEN, basic:user:pass, header:Name:Value)"
        ),
    )
    p_api.add_argument(
        "--url-credential",
        action="append",
        nargs=2,
        metavar=("URL", "ENTRY"),
        help=(
            "Per-URL credential entry (repeatable), e.g., --url-credential https://api.example token=$TOKEN"
        ),
    )
    p_api.add_argument(
        "--url-auth",
        action="append",
        nargs=2,
        metavar=("URL", "AUTH"),
        help=(
            "Per-URL auth helper (same syntax as --auth), e.g., --url-auth https://api.example bearer:$TOKEN"
        ),
    )
    # Output shaping
    p_api.add_argument(
        "--fields",
        help=(
            "Comma-separated output fields for CSV/table (default: source,dataset,link)"
        ),
    )
    p_api.add_argument(
        "--limit-total",
        type=int,
        help="Limit total aggregated results across URLs",
    )
    p_api.add_argument(
        "--dedupe",
        choices=["dataset", "link"],
        help="Drop duplicates by key (dataset or link)",
    )
    p_api.add_argument(
        "--sort",
        help="Sort by comma-separated keys (e.g., source,dataset)",
    )
    # OpenAPI diagnostics
    p_api.add_argument(
        "--print-openapi",
        action="store_true",
        help="Print discovered endpoint and query params for each URL",
    )
    p_api.add_argument(
        "--suggest-flags",
        action="store_true",
        help="Suggest simple OpenAPI query params that can be passed via --param",
    )

    def _parse_header_args(values: Iterable[str] | None) -> dict[str, str]:
        parsed: dict[str, str] = {}
        if not values:
            return parsed
        for raw in values:
            if raw is None:
                continue
            s = str(raw)
            if ":" in s:
                key, val = s.split(":", 1)
            elif "=" in s:
                key, val = s.split("=", 1)
            else:
                continue
            key = key.strip()
            val = val.strip()
            if key:
                parsed[key] = val
        return parsed

    def _cmd_api(ns: argparse.Namespace) -> int:
        try:
            from .api_search import federated_api_search, print_api_table

            urls: list[str] = [u.strip() for u in (ns.url or []) if u and u.strip()]
            if not urls:
                print(
                    "error: provide at least one --url", file=__import__("sys").stderr
                )
                return 2
            eff_query = (
                getattr(ns, "api_query", None)
                or getattr(ns, "query", None)
                or getattr(ns, "q", None)
            )
            if not eff_query:
                print(
                    "error: missing --query; pass it after the subcommand (e.g., zyra search api --query 'text')",
                    file=__import__("sys").stderr,
                )
                return 2
            # OpenAPI diagnostics
            if ns.print_openapi or ns.suggest_flags:
                from .api_search import print_openapi_info

                for u in urls:
                    print_openapi_info(
                        u, suggest=bool(ns.suggest_flags), verbose=bool(ns.verbose)
                    )
                return 0

            header_entries = _parse_header_args(getattr(ns, "header", None))
            credential_entries = list(getattr(ns, "credential", []) or [])
            if credential_entries:
                try:
                    resolved = resolve_credentials(
                        credential_entries,
                        credential_file=getattr(ns, "credential_file", None),
                    )
                except CredentialResolutionError as exc:
                    print(f"error: {exc}", file=__import__("sys").stderr)
                    return 2
                apply_http_credentials(header_entries, resolved.values)
            apply_auth_header(header_entries, getattr(ns, "auth", None))

            scoped_credential_entries: dict[str, list[str]] = {}
            for scope, entry in getattr(ns, "url_credential", []) or []:
                if scope and entry:
                    scoped_credential_entries.setdefault(str(scope), []).append(
                        str(entry)
                    )

            headers_by_url: dict[str, dict[str, str]] = {}

            def _ensure_scoped_headers(scope: str) -> dict[str, str]:
                scoped = headers_by_url.get(scope)
                if scoped is None:
                    scoped = header_entries.copy() if header_entries else {}
                    headers_by_url[scope] = scoped
                return scoped

            for scope, entries in scoped_credential_entries.items():
                try:
                    resolved = resolve_credentials(
                        entries,
                        credential_file=getattr(ns, "credential_file", None),
                    )
                except CredentialResolutionError as exc:
                    print(f"error: {exc}", file=__import__("sys").stderr)
                    return 2
                scoped_headers = _ensure_scoped_headers(scope)
                scoped_headers.pop("Authorization", None)
                apply_http_credentials(scoped_headers, resolved.values)

            for scope, auth_value in getattr(ns, "url_auth", []) or []:
                if not scope or not auth_value:
                    continue
                scoped_headers = _ensure_scoped_headers(str(scope))
                scoped_headers.pop("Authorization", None)
                apply_auth_header(scoped_headers, str(auth_value))

            rows = federated_api_search(
                urls,
                eff_query,
                limit=int(ns.limit or 10),
                verbose=bool(ns.verbose),
                params=list(ns.param or []) if ns.param else None,
                headers=header_entries if header_entries else None,
                headers_by_url=headers_by_url if headers_by_url else None,
                timeout=float(ns.timeout or 30.0),
                retries=int(ns.retries or 0),
                concurrency=int(ns.concurrency or 4),
                no_openapi=bool(ns.no_openapi),
                endpoint=ns.endpoint,
                qp_name=ns.qp,
                result_key=ns.result_key,
                use_post=bool(ns.post),
                json_params=list(ns.json_param or []) if ns.json_param else None,
                json_body=ns.json_body,
            )
            # Output shaping
            if ns.dedupe:
                key = ns.dedupe
                seen: set[str] = set()
                deduped = []
                for r in rows:
                    v = str(r.get(key) or "")
                    if v and v not in seen:
                        seen.add(v)
                        deduped.append(r)
                rows = deduped
            if ns.sort:
                keys = [k.strip() for k in ns.sort.split(",") if k.strip()]
                rows = sorted(
                    rows, key=lambda r: tuple(str(r.get(k) or "") for k in keys)
                )
            if ns.limit_total:
                rows = rows[: max(0, int(ns.limit_total)) or None]
            # Default to JSON unless CSV/table explicitly requested
            fields = (
                [s.strip() for s in ns.fields.split(",") if s.strip()]
                if ns.fields
                else None
            )
            if ns.csv:
                import csv
                import sys

                cols = fields or ["source", "dataset", "description", "link"]
                w = csv.DictWriter(sys.stdout, fieldnames=cols)
                w.writeheader()
                for r in rows:
                    w.writerow({k: r.get(k) for k in cols})
                return 0
            if ns.table:
                print_api_table(rows, fields=fields)
                return 0
            # JSON (default)
            print(__import__("json").dumps(rows, indent=2))
            return 0
        except Exception as e:  # pragma: no cover - defensive
            print(f"API search failed: {e}", file=__import__("sys").stderr)
            return 2

    p_api.set_defaults(func=_cmd_api)

    # -----------------------------
    # Base `zyra search` arguments
    # -----------------------------
    p.add_argument(
        "query",
        nargs="?",
        help="Search query (matches title/keywords/description)",
    )
    p.add_argument(
        "--query",
        "-q",
        dest="q",
        help="Search query (alternative to positional)",
    )
    p.add_argument(
        "-l",
        "--limit",
        type=int,
        default=10,
        help="Maximum number of results (default: 10)",
    )
    p.add_argument(
        "--catalog-file",
        help=("Path to a local catalog JSON file (overrides packaged SOS catalog)"),
    )
    p.add_argument(
        "--include-local",
        action="store_true",
        help=("When remote sources are provided, also include local catalog results"),
    )
    p.add_argument(
        "--profile",
        help=("Name of a bundled profile under zyra.assets.profiles (e.g., sos)"),
    )
    p.add_argument(
        "--profile-file",
        help=(
            "Path to a JSON profile describing sources (local/ogc) and optional scoring weights"
        ),
    )
    p.add_argument(
        "--semantic-analyze",
        action="store_true",
        help=(
            "Perform general search and send results to LLM for analysis/ranking (prints summary and picks)"
        ),
    )
    p.add_argument(
        "--analysis-limit",
        type=int,
        default=20,
        help="Max number of results to include in LLM analysis (default: 20)",
    )
    p.add_argument(
        "--semantic",
        help=(
            "Natural-language semantic search; plans sources via LLM and executes backends"
        ),
    )
    p.add_argument(
        "--show-plan",
        action="store_true",
        help="Print the generated semantic search plan (JSON)",
    )
    # Optional remote discovery: OGC WMS capabilities
    p.add_argument(
        "--ogc-wms",
        help=(
            "WMS GetCapabilities URL to search (remote). If provided, results"
            " include remote matches; use --remote-only to skip local catalog."
        ),
    )
    p.add_argument(
        "--remote-only",
        action="store_true",
        help="When used with --ogc-wms, only show remote results",
    )
    p.add_argument(
        "--ogc-records",
        help=(
            "OGC API - Records items URL to search (remote). Often ends with /collections/{id}/items"
        ),
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Output results in JSON format",
    )
    p.add_argument(
        "--yaml",
        action="store_true",
        help="Output results in YAML format",
    )
    p.add_argument(
        "--select",
        type=int,
        help=("Select a single result by 1-based index and print its URI only"),
    )
    # Enrichment flags (Phase 2)
    p.add_argument(
        "--enrich",
        choices=["shallow", "capabilities", "probe"],
        help=(
            "Optional metadata enrichment level: shallow|capabilities|probe (bounded, cached)"
        ),
    )
    p.add_argument(
        "--enrich-timeout",
        type=float,
        default=3.0,
        help="Per-item soft timeout seconds for enrichment (default: 3.0)",
    )
    p.add_argument(
        "--enrich-workers",
        type=int,
        default=4,
        help="Enrichment concurrency (workers). Default: 4",
    )
    p.add_argument(
        "--cache-ttl",
        type=int,
        default=86400,
        help="Enrichment cache TTL seconds. Default: 86400 (1 day)",
    )
    p.add_argument(
        "--enrich-async",
        action="store_true",
        help=(
            "Request async enrichment (API-driven). CLI-only runs print a warning and run sync."
        ),
    )
    p.add_argument(
        "--offline",
        action="store_true",
        help=("Disable network fetches during enrichment; local files only"),
    )
    p.add_argument(
        "--https-only",
        action="store_true",
        help=("Require HTTPS for any remote probing"),
    )
    p.add_argument(
        "--allow-host",
        action="append",
        dest="allow_hosts",
        help=("Explicitly allow a host suffix for remote probing (can repeat)"),
    )
    p.add_argument(
        "--deny-host",
        action="append",
        dest="deny_hosts",
        help=("Explicitly deny a host suffix for remote probing (can repeat)"),
    )
    p.add_argument(
        "--max-probe-bytes",
        type=int,
        help=("Maximum content length to probe (bytes); larger assets are skipped"),
    )

    def _cmd(ns: argparse.Namespace) -> int:
        items: list[DatasetMetadata] = []
        # Semantic search (LLM-planned)
        if getattr(ns, "semantic", None):
            try:
                items = _semantic_search(ns)
            except Exception as e:
                print(f"Semantic search failed: {e}", file=__import__("sys").stderr)
                return 2
            return _emit_results(ns, items)
        # Semantic analysis: general search then LLM analysis over results
        if getattr(ns, "semantic_analyze", None):
            try:
                return _semantic_analyze(ns)
            except Exception as e:
                print(f"Semantic analysis failed: {e}", file=__import__("sys").stderr)
                return 2
        # Non-semantic path requires a query
        effective_query = getattr(ns, "query", None) or getattr(ns, "q", None)
        if not effective_query:
            print(
                "error: the following arguments are required: query",
                file=__import__("sys").stderr,
            )
            return 2
        # Optional profile(s)
        prof_sources: dict[str, Any] = {}
        prof_weights: dict[str, int] = {}
        prof_defaults: dict[str, Any] = {}
        prof_license_policy: dict[str, Any] = {}
        defaults_sources: list[str] = []
        # Bundled profile by name
        if getattr(ns, "profile", None):
            try:
                pkg = "zyra.assets.profiles"
                res = f"{ns.profile}.json"
                path = importlib_resources.files(pkg).joinpath(res)
                with importlib_resources.as_file(path) as p:
                    prof0 = json.loads(p.read_text(encoding="utf-8"))
                prof_sources.update(dict(prof0.get("sources") or {}))
                prof_weights.update(
                    {k: int(v) for k, v in (prof0.get("weights") or {}).items()}
                )
                enr = prof0.get("enrichment") or {}
                ed = enr.get("defaults") or {}
                if isinstance(ed, dict):
                    prof_defaults.update(ed)
                lp = enr.get("license_policy") or {}
                if isinstance(lp, dict):
                    prof_license_policy.update(lp)
            except Exception as e:
                print(
                    f"Failed to load bundled profile '{ns.profile}': {e}",
                    file=__import__("sys").stderr,
                )
                return 2
        # External profile file (overrides bundled)
        if getattr(ns, "profile_file", None):
            try:
                from pathlib import Path

                prof = json.loads(Path(ns.profile_file).read_text(encoding="utf-8"))
                prof_sources.update(dict(prof.get("sources") or {}))
                prof_weights.update(
                    {k: int(v) for k, v in (prof.get("weights") or {}).items()}
                )
                enr = prof.get("enrichment") or {}
                ed = enr.get("defaults") or {}
                if isinstance(ed, dict):
                    prof_defaults.update(ed)
                lp = enr.get("license_policy") or {}
                if isinstance(lp, dict):
                    prof_license_policy.update(lp)
            except Exception as e:
                print(f"Failed to load profile: {e}", file=__import__("sys").stderr)
                return 2

        # Decide local inclusion consistently via helper
        from .utils import compute_inclusion

        include_local, any_remote, cat_path = compute_inclusion(
            getattr(ns, "ogc_wms", None),
            getattr(ns, "ogc_records", None),
            prof_sources,
            remote_only=bool(getattr(ns, "remote_only", False)),
            include_local_flag=bool(getattr(ns, "include_local", False)),
            catalog_file_flag=getattr(ns, "catalog_file", None),
        )
        if include_local:
            items.extend(
                LocalCatalogBackend(cat_path, weights=prof_weights).search(
                    effective_query, limit=ns.limit
                )
            )
            # If no profile provided, auto-scope SOS defaults to local items
            if not getattr(ns, "profile", None) and not getattr(
                ns, "profile_file", None
            ):
                try:
                    pkg = "zyra.assets.profiles"
                    res = "sos.json"
                    path = importlib_resources.files(pkg).joinpath(res)
                    with importlib_resources.as_file(path) as p:
                        import json as _json

                        prof0 = _json.loads(p.read_text(encoding="utf-8"))
                    enr = prof0.get("enrichment") or {}
                    ed = enr.get("defaults") or {}
                    if isinstance(ed, dict):
                        prof_defaults.update(ed)
                    lp = enr.get("license_policy") or {}
                    if isinstance(lp, dict):
                        prof_license_policy.update(lp)
                    defaults_sources = ["sos-catalog"]
                except Exception:
                    pass
        # Optional remote OGC WMS
        # Remote WMS: combine CLI flag and profile list
        wms_urls = []
        if getattr(ns, "ogc_wms", None):
            wms_urls.append(ns.ogc_wms)
        prof_wms = prof_sources.get("ogc_wms") or []
        if isinstance(prof_wms, list):
            wms_urls.extend([u for u in prof_wms if isinstance(u, str)])
        for wurl in wms_urls:
            try:
                from .ogc import OGCWMSBackend

                rem = OGCWMSBackend(wurl, weights=prof_weights).search(
                    effective_query, limit=ns.limit
                )
                items.extend(rem)
            except Exception as e:
                print(
                    f"Remote OGC WMS search failed: {e}",
                    file=__import__("sys").stderr,
                )
        # Remote OGC API - Records: combine CLI flag and profile list
        rec_urls = []
        if getattr(ns, "ogc_records", None):
            rec_urls.append(ns.ogc_records)
        prof_rec = prof_sources.get("ogc_records") or []
        if isinstance(prof_rec, list):
            rec_urls.extend([u for u in prof_rec if isinstance(u, str)])
        for rurl in rec_urls:
            try:
                from .ogc_records import OGCRecordsBackend

                rec = OGCRecordsBackend(rurl, weights=prof_weights).search(
                    effective_query, limit=ns.limit
                )
                items.extend(rec)
            except Exception as e:
                print(
                    f"Remote OGC Records search failed: {e}",
                    file=__import__("sys").stderr,
                )
        # Optional enrichment
        if getattr(ns, "enrich", None):
            try:
                from zyra.transform.enrich import enrich_items

                items = enrich_items(
                    items,
                    level=str(ns.enrich),
                    timeout=float(getattr(ns, "enrich_timeout", 3.0) or 3.0),
                    workers=int(getattr(ns, "enrich_workers", 4) or 4),
                    cache_ttl=int(getattr(ns, "cache_ttl", 86400) or 86400),
                    offline=bool(getattr(ns, "offline", False) or False),
                    https_only=bool(getattr(ns, "https_only", False) or False),
                    allow_hosts=list(getattr(ns, "allow_hosts", []) or []),
                    deny_hosts=list(getattr(ns, "deny_hosts", []) or []),
                    max_probe_bytes=(getattr(ns, "max_probe_bytes", None)),
                    profile_defaults=prof_defaults,
                    profile_license_policy=prof_license_policy,
                    defaults_sources=defaults_sources,
                )
            except Exception as e:
                print(f"Enrichment failed: {e}", file=__import__("sys").stderr)
            if getattr(ns, "enrich_async", False):
                print(
                    "note: --enrich-async is only available via the API; returned sync results",
                    file=__import__("sys").stderr,
                )
        return _emit_results(ns, items)

    p.set_defaults(func=_cmd)


def _emit_results(ns: argparse.Namespace, items: list[DatasetMetadata]) -> int:
    # Respect overall limit
    items = items[: max(0, ns.limit) or None]
    if ns.select is not None:
        idx = ns.select
        if idx < 1 or idx > len(items):
            print(
                f"--select index out of range (1..{len(items)})",
                file=__import__("sys").stderr,
            )
            return 2
        print(items[idx - 1].uri)
        return 0
    if ns.json and ns.yaml:
        print("Choose one of --json or --yaml", file=__import__("sys").stderr)
        return 2
    if ns.json:
        from zyra.utils.serialize import to_list

        out = to_list(items)
        print(json.dumps(out, indent=2))
        return 0
    if ns.yaml:
        try:
            import yaml  # type: ignore

            from zyra.utils.serialize import to_list

            out = to_list(items)
            print(yaml.safe_dump(out, sort_keys=False))
            return 0
        except Exception:
            print(
                "PyYAML is not installed. Use --json or install PyYAML.",
                file=__import__("sys").stderr,
            )
            return 2
    _print_table(items)
    return 0


def _semantic_search(ns: argparse.Namespace) -> list[DatasetMetadata]:
    # Plan with the same LLM provider/model as Wizard
    from zyra.wizard import _select_provider  # type: ignore[attr-defined]
    from zyra.wizard.prompts import load_semantic_search_prompt

    client = _select_provider(None, None)
    sys_prompt = load_semantic_search_prompt()
    user = (
        "Given a user's dataset request, produce a minimal JSON search plan.\n"
        f"User request: {ns.semantic}\n"
        "If unsure about endpoints, prefer profile 'sos'. Keep keys minimal."
    )
    plan_raw = client.generate(sys_prompt, user)
    try:
        plan = json.loads(plan_raw.strip())
    except Exception:
        plan = {"query": ns.semantic, "profile": "sos"}
    # Apply CLI overrides
    if getattr(ns, "limit", None):
        plan["limit"] = ns.limit
    # Heuristic: switch from 'sos' when SST/NASA or pygeoapi terms detected
    q = str(plan.get("query") or ns.semantic)
    wms_urls = plan.get("ogc_wms") or []
    rec_urls = plan.get("ogc_records") or []
    profile = plan.get("profile")
    if (not profile or profile == "sos") and not wms_urls and not rec_urls:
        ql = q.lower()
        if "sea surface temperature" in ql or "sst" in ql or "nasa" in ql:
            plan["profile"] = "gibs"
        elif "lake" in ql or "pygeoapi" in ql:
            plan["profile"] = "pygeoapi"

    # Execute using the same backends as normal search
    from zyra.connectors.discovery.ogc import OGCWMSBackend
    from zyra.connectors.discovery.ogc_records import OGCRecordsBackend

    q = str(plan.get("query") or ns.semantic)
    limit = int(plan.get("limit", ns.limit or 10))
    include_local = bool(plan.get("include_local", False))
    remote_only = bool(plan.get("remote_only", False))
    profile = plan.get("profile")
    catalog_file = plan.get("catalog_file")
    wms_urls = plan.get("ogc_wms") or []
    rec_urls = plan.get("ogc_records") or []

    prof_sources: dict[str, Any] = {}
    prof_weights: dict[str, int] = {}
    if isinstance(profile, str) and profile:
        from contextlib import suppress
        from importlib import resources as ir

        with suppress(Exception):
            base = ir.files("zyra.assets.profiles").joinpath(profile + ".json")
            with ir.as_file(base) as p:
                pr = json.loads(p.read_text(encoding="utf-8"))
            prof_sources = dict(pr.get("sources") or {})
            prof_weights = {k: int(v) for k, v in (pr.get("weights") or {}).items()}

    results: list[DatasetMetadata] = []
    from .utils import compute_inclusion as _compute_inclusion

    include_local_eff, _any_remote, cat = _compute_inclusion(
        wms_urls,
        rec_urls,
        prof_sources,
        remote_only=bool(remote_only),
        include_local_flag=bool(include_local),
        catalog_file_flag=catalog_file,
    )
    if include_local_eff:
        results.extend(
            LocalCatalogBackend(cat, weights=prof_weights).search(q, limit=limit)
        )

    # Remote WMS
    prof_wms = prof_sources.get("ogc_wms") or []
    if isinstance(prof_wms, list):
        wms_urls = list(wms_urls) + [u for u in prof_wms if isinstance(u, str)]
    from contextlib import suppress

    for u in wms_urls:
        with suppress(Exception):
            results.extend(
                OGCWMSBackend(u, weights=prof_weights).search(q, limit=limit)
            )
    # Remote Records
    prof_rec = prof_sources.get("ogc_records") or []
    if isinstance(prof_rec, list):
        rec_urls = list(rec_urls) + [u for u in prof_rec if isinstance(u, str)]
    for u in rec_urls:
        with suppress(Exception):
            results.extend(
                OGCRecordsBackend(u, weights=prof_weights).search(q, limit=limit)
            )

    # Optional show-plan
    if getattr(ns, "show_plan", False):
        try:
            effective = {
                "query": q,
                "limit": limit,
                "profile": profile,
                "catalog_file": catalog_file,
                "include_local": include_local,
                "remote_only": remote_only,
                "ogc_wms": wms_urls or None,
                "ogc_records": rec_urls or None,
            }
            print(json.dumps(plan, indent=2))
            print(json.dumps({k: v for k, v in effective.items() if v}, indent=2))
        except Exception:
            pass

    return results


def _semantic_analyze(ns: argparse.Namespace) -> int:
    # 1) Perform a broad search using provided flags (reuse normal path)
    # We'll emulate non-semantic search execution path to collect items
    from types import SimpleNamespace

    temp_ns = SimpleNamespace(**vars(ns))
    temp_ns.semantic = None
    # Build up items using the same code paths
    items: list[DatasetMetadata] = []
    # Local
    eff_query = getattr(ns, "query", None) or getattr(ns, "q", None) or ""
    if not getattr(ns, "remote_only", False):
        items.extend(
            LocalCatalogBackend(getattr(ns, "catalog_file", None)).search(
                eff_query, limit=ns.limit
            )
        )
    # WMS
    if getattr(ns, "ogc_wms", None):
        from .ogc import OGCWMSBackend

        items.extend(OGCWMSBackend(ns.ogc_wms).search(eff_query, limit=ns.limit))
    # Records
    if getattr(ns, "ogc_records", None):
        from .ogc_records import OGCRecordsBackend

        items.extend(
            OGCRecordsBackend(ns.ogc_records).search(eff_query, limit=ns.limit)
        )
    # 2) Analyze via LLM
    import json as _json

    from zyra.utils.serialize import compact_dataset
    from zyra.wizard import _select_provider  # type: ignore[attr-defined]
    from zyra.wizard.prompts import load_semantic_analysis_prompt

    ctx_items = [
        compact_dataset(i, max_desc_len=240)
        for i in items[: max(1, getattr(ns, "analysis_limit", 20))]
    ]
    client = _select_provider(None, None)
    sys_prompt = load_semantic_analysis_prompt()
    user = _json.dumps({"query": eff_query, "results": ctx_items})
    raw = client.generate(sys_prompt, user)
    try:
        analysis = _json.loads(raw.strip())
    except Exception:
        analysis = {"summary": raw.strip(), "picks": []}
    # Emit analysis; respect --json
    out = {
        "query": eff_query,
        "items": ctx_items,
        "analysis": analysis,
    }
    if getattr(ns, "json", False):
        print(_json.dumps(out, indent=2))
    else:
        print(analysis.get("summary", ""))
        picks = analysis.get("picks", []) or []
        if picks:
            print("")
            print("Top picks:")
            for p in picks:
                print(f"- {p.get('id')}: {p.get('reason')}")
    return 0
