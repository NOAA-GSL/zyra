# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import ipaddress
import json
import socket
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from zyra.api.models.cli_request import CLIRunRequest
from zyra.api.routers.cli import run_cli_endpoint
from zyra.connectors.credentials import (
    CredentialResolutionError,
    apply_auth_header,
    apply_http_credentials,
    resolve_credentials,
)
from zyra.utils.env import env, env_bool, env_int, env_path


def _infer_filename(headers: dict[str, str], default: str = "download.bin") -> str:
    cd = headers.get("Content-Disposition") or headers.get("content-disposition") or ""
    if "filename=" in cd:
        return cd.split("filename=", 1)[1].strip().strip('"') or default
    ct = headers.get("Content-Type") or headers.get("content-type") or ""
    if ct:
        main = ct.split(";", 1)[0].strip().lower()
        mapping = {
            "application/json": ".json",
            "application/x-ndjson": ".jsonl",
            "text/plain": ".txt",
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "audio/ogg": ".ogg",
        }
        if main in mapping:
            return f"download{mapping[main]}"
    return default


def api_fetch(
    *,
    url: str,
    method: str | None = None,
    headers: dict[str, str] | None = None,
    header: list[str] | None = None,
    params: dict[str, str] | None = None,
    data: Any | None = None,
    output_dir: str | None = None,
    credentials: dict[str, str] | None = None,
    credential: list[str] | None = None,
    credential_file: str | None = None,
    auth: str | None = None,
) -> dict[str, Any]:
    """Fetch an API endpoint and save response under DATA_DIR.

    Returns { path, content_type, size_bytes, status_code }.
    """
    # Resolve base data dir and ensure caller-provided output_dir stays within it
    base = env_path("DATA_DIR", "_work").resolve()
    subdir = output_dir or "downloads"
    # Pre-sanitize: forbid absolute paths and traversal parts before joining
    sd = Path(subdir)
    if sd.is_absolute() or any(part in {"", ".", ".."} for part in sd.parts):
        raise ValueError("Invalid output_dir: must be a relative subdirectory")
    try:
        candidate_dir = (
            base / sd
        ).resolve()  # lgtm [py/path-injection] [py/uncontrolled-data-in-path-expression]
        if not candidate_dir.is_relative_to(base):  # type: ignore[attr-defined]
            raise ValueError("Invalid output_dir: must be a subdirectory of DATA_DIR")
    except Exception as exc:
        raise ValueError(
            "Invalid output_dir: must be a subdirectory of DATA_DIR"
        ) from exc
    out_dir = candidate_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- SSRF hardening & network policy ---
    def _is_public_ip(ip_str: str) -> bool:
        try:
            ip = ipaddress.ip_address(ip_str)
            bad = (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_multicast
                or ip.is_reserved
                or ip.is_unspecified
            )
            # Block common metadata endpoints explicitly
            if ip.version == 4 and ip.exploded.startswith("169.254.169.254"):
                bad = True
            return not bad
        except Exception:
            return False

    def _all_resolved_public(host: str, port: int | None) -> bool:
        try:
            infos = socket.getaddrinfo(host, port or 0, proto=socket.IPPROTO_TCP)
            addrs: set[str] = set()
            for _family, _type, _proto, _canon, sockaddr in infos:
                try:
                    if len(sockaddr) >= 1:
                        addrs.add(str(sockaddr[0]))
                except Exception:
                    continue
            if not addrs:
                return False
            return all(_is_public_ip(a) for a in addrs)
        except Exception:
            return False

    def _host_allowed(host: str) -> bool:
        h = host.lower()
        deny = (env("MCP_FETCH_DENY_HOSTS") or "").strip()
        if deny:
            for d in [s.strip().lower() for s in deny.split(",") if s.strip()]:
                if h.endswith(d):
                    return False
        allow = (env("MCP_FETCH_ALLOW_HOSTS") or "").strip()
        if allow:
            return any(
                h.endswith(a)
                for a in [s.strip().lower() for s in allow.split(",") if s.strip()]
            )
        return True

    # Parse and validate URL
    parsed = urlparse(url)
    scheme = (parsed.scheme or "").lower()
    if scheme not in {"http", "https"}:
        raise ValueError("Only http/https URLs are allowed")
    if env_bool("MCP_FETCH_HTTPS_ONLY", True) and scheme != "https":
        raise ValueError("HTTPS is required for outbound fetches")
    # Forbid URL userinfo (user:pass@host)
    if parsed.username or parsed.password:
        raise ValueError("Credentials in URL are not allowed")
    host = parsed.hostname or ""
    if not host:
        raise ValueError("URL host is required")
    # Port policy
    port = parsed.port or (443 if scheme == "https" else 80)
    allow_ports_raw = (env("MCP_FETCH_ALLOW_PORTS") or "80,443").strip()
    try:
        allow_ports = {int(p.strip()) for p in allow_ports_raw.split(",") if p.strip()}
    except Exception:
        allow_ports = {80, 443}
    if port not in allow_ports:
        raise ValueError(f"Port {port} not permitted")
    # Allow/deny host list check
    if not _host_allowed(host):
        raise ValueError("Host is not permitted")
    # Block direct IPs pointing to non-public ranges and domain names resolving internally
    try:
        ipaddress.ip_address(host)
        # Literal IP provided
        if not _is_public_ip(host):
            raise ValueError("IP address is not publicly routable")
    except ValueError:
        # Not an IP literal; resolve and validate
        if not _all_resolved_public(host, port):
            raise ValueError(
                "Destination resolves to a private or disallowed network"
            ) from None

    # Sanitize sensitive hop/host headers to avoid header-based SSRF tricks
    from zyra.utils.http import strip_hop_headers as _strip

    hdrs = _strip(headers or {})
    if header:
        for item in header:
            if ":" in item:
                name, value = item.split(":", 1)
                hdrs.setdefault(name.strip(), value.lstrip())

    credential_entries: list[str] = []
    if credential:
        credential_entries.extend([c for c in credential if c])
    if credentials:
        credential_entries.extend(f"{k}={v}" for k, v in credentials.items())
    if credential_entries:
        try:
            resolved = resolve_credentials(
                credential_entries, credential_file=credential_file
            )
        except CredentialResolutionError as exc:
            raise ValueError(str(exc)) from exc
        apply_http_credentials(hdrs, resolved.values)
    apply_auth_header(hdrs, auth)
    hdrs = _strip(hdrs)

    m = (method or "GET").upper()
    body = json.dumps(data).encode("utf-8") if isinstance(data, (dict, list)) else data

    # Redirect policy: disabled by default; can be enabled with a small cap
    allow_redirects = False

    r = requests.request(  # codeql[py/ssrf]
        m,
        url,
        headers=hdrs,
        params=params or {},
        data=body,
        timeout=60,
        stream=True,
        allow_redirects=allow_redirects,
    )
    from pathlib import Path as _P

    ct = r.headers.get("Content-Type") or "application/octet-stream"
    name = _infer_filename(r.headers)
    safe_name = _P(name).name or "download.bin"
    candidate = (out_dir / safe_name).resolve()  # lgtm [py/path-injection]
    # Validate containment under out_dir; prefer is_relative_to when available.
    try:
        try:
            rel_ok = candidate.is_relative_to(out_dir)  # type: ignore[attr-defined]
        except AttributeError:
            # Fallback for environments without Path.is_relative_to
            rel_ok = str(candidate).startswith(str(out_dir))
        if not rel_ok:
            safe_name = "download.bin"
            candidate = (out_dir / safe_name).resolve()
    except (OSError, ValueError) as exc:
        # Log specific filesystem/path errors while falling back to a safe name
        import logging as _logging

        _logging.getLogger(__name__).warning(
            "Path containment check failed for %s: %s", candidate, exc
        )
        safe_name = "download.bin"
        candidate = (out_dir / safe_name).resolve()
    out = candidate
    size = 0
    max_bytes_env = int(env_int("MCP_FETCH_MAX_BYTES", 0) or 0)
    with out.open("wb") as f:
        for chunk in r.iter_content(chunk_size=1024 * 1024):
            if not chunk:
                continue
            f.write(chunk)
            size += len(chunk)
            if max_bytes_env > 0 and size > max_bytes_env:
                # Stop writing further to avoid unbounded downloads
                break
    return {
        "path": str(out.relative_to(base)),
        "content_type": ct,
        "size_bytes": size,
        "status_code": r.status_code,
    }


def api_process_json(
    *,
    file_or_url: str,
    records_path: str | None = None,
    fields: str | None = None,
    flatten: bool | None = None,
    explode: list[str] | None = None,
    derived: str | None = None,
    format: str | None = None,
    output_dir: str | None = None,
    output_name: str | None = None,
) -> dict[str, Any]:
    """Transform JSON/NDJSON to CSV/JSONL via CLI path and save under DATA_DIR.

    Returns { path, size_bytes, format }.
    """
    # Resolve and validate output directory
    base = env_path("DATA_DIR", "_work").resolve()
    subdir = output_dir or "outputs"
    try:
        candidate_dir = (base / subdir).resolve()
        if not candidate_dir.is_relative_to(base):  # type: ignore[attr-defined]
            raise ValueError("Invalid output_dir: must be a subdirectory of DATA_DIR")
    except Exception as exc:
        raise ValueError(
            "Invalid output_dir: must be a subdirectory of DATA_DIR"
        ) from exc
    out_dir = candidate_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    fmt = (format or "csv").lower()
    # Sanitize output name
    safe_default = "output.jsonl" if fmt == "jsonl" else "output.csv"
    name_raw = output_name or safe_default
    name = Path(name_raw).name or safe_default
    out_path = (out_dir / name).resolve()  # lgtm [py/path-injection]
    try:
        if not out_path.is_relative_to(out_dir):  # type: ignore[attr-defined]
            name = safe_default
            out_path = (out_dir / name).resolve()
    except Exception:
        name = safe_default
        out_path = (out_dir / name).resolve()

    args: dict[str, Any] = {
        "file_or_url": file_or_url,
        "output": str(out_path),
        "format": fmt,
    }
    if records_path:
        args["records_path"] = records_path
    if fields:
        args["fields"] = fields
    if flatten is not None:
        args["flatten"] = bool(flatten)
    if explode:
        args["explode"] = list(explode)
    if derived:
        args["derived"] = derived

    cr = run_cli_endpoint(
        CLIRunRequest(stage="process", command="api-json", args=args, mode="sync"), None
    )
    if cr.exit_code != 0:
        raise RuntimeError(cr.stderr or "Processing failed")
    size = 0
    try:
        size = Path(out_path).stat().st_size
    except Exception:
        size = 0
    return {"path": str(out_path.relative_to(base)), "size_bytes": size, "format": fmt}
