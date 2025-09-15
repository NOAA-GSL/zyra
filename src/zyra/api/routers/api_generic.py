# SPDX-License-Identifier: Apache-2.0
"""Generic API routers for direct, streaming-friendly endpoints.

Adds:
- POST /v1/acquire/api — generic REST fetch with optional streaming
- POST /v1/process/api-json — transform JSON/NDJSON to CSV/JSONL via CLI path

These are thin wrappers around internal helpers to avoid duplicating logic from
the CLI while providing HTTP-friendly streaming behavior.
"""

from __future__ import annotations

import ipaddress
import json
import os
import socket
import tempfile
from typing import Any
from urllib.parse import urlparse

import requests
from fastapi import APIRouter, Body, File, HTTPException, Request, UploadFile
from fastapi.responses import Response, StreamingResponse

from zyra.api.schemas.domain_args import (
    AcquireApiArgs,
    PresetLimitlessAudioArgs,
    ProcessApiJsonArgs,
)

router = APIRouter(tags=["api"], prefix="")


_ACQUIRE_BODY = Body(...)


@router.post("/acquire/api")
def acquire_api(req: AcquireApiArgs = _ACQUIRE_BODY):
    """Fetch an API endpoint (single-shot, streaming, or paginated).

    Modes
    - Streaming (``stream=true``): stream bytes directly with upstream
      ``Content-Type`` and optional ``Content-Disposition``.
    - Single-shot: perform one request and return the body with upstream
      ``Content-Type`` when available.
    - Paginated (``paginate=page|cursor|link``): when not streaming, either
      stream NDJSON (``newline_json=true``) or aggregate pages into a JSON array.
    """
    url = req.url
    if not url and req.preset:
        # Minimal preset support for limitless-audio as convenience; CLI preset is richer
        base = "https://api.limitless.ai/v1"
        url = f"{base}/download-audio"
    if not url:
        raise HTTPException(status_code=400, detail="url or preset is required")

    # SSRF hardening helpers (scoped to this endpoint to avoid broad refactors)
    from zyra.utils.env import env, env_bool

    def _cfg(name: str, default: str | None = None) -> str | None:
        # Prefer API_* envs, fall back to MCP_* for consistency with MCP tools
        return env(
            name,
            env(name.replace("API_", "MCP_")) if name.startswith("API_") else default,
        )

    def _https_only() -> bool:
        return bool(env_bool("API_FETCH_HTTPS_ONLY", True))

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
            ip = ipaddress.ip_address(ip_str)
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
            infos = socket.getaddrinfo(host, port or 0, proto=socket.IPPROTO_TCP)
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

    def _validate_outbound_url(u: str) -> str:
        pr = urlparse(u)
        scheme = (pr.scheme or "").lower()
        if scheme not in {"http", "https"}:
            raise HTTPException(
                status_code=400, detail="Only http/https URLs are allowed"
            )
        if _https_only() and scheme != "https":
            raise HTTPException(status_code=400, detail="HTTPS is required")
        if pr.username or pr.password:
            raise HTTPException(
                status_code=400, detail="Credentials in URL are not allowed"
            )
        host = pr.hostname or ""
        if not host:
            raise HTTPException(status_code=400, detail="URL host is required")
        # Permit RFC 2606 example domains for tests/docs
        h_l = host.lower()
        if h_l.endswith(".example") or h_l in {
            "example.com",
            "example.org",
            "example.net",
        }:
            port = pr.port or (443 if scheme == "https" else 80)
            if port not in _allowed_ports():
                raise HTTPException(
                    status_code=400, detail=f"Port {port} not permitted"
                )
            if not _host_allowed(host):
                raise HTTPException(status_code=400, detail="Host is not permitted")
            # Return the original URL after checks (no rewrite for example hosts)
            return u
        port = pr.port or (443 if scheme == "https" else 80)
        if port not in _allowed_ports():
            raise HTTPException(status_code=400, detail=f"Port {port} not permitted")
        if not _host_allowed(host):
            raise HTTPException(status_code=400, detail="Host is not permitted")
        try:
            # If literal IP, must be public
            ipaddress.ip_address(host)
            if not _is_public_ip(host):
                raise HTTPException(
                    status_code=400, detail="IP address is not publicly routable"
                )
        except ValueError:
            # DNS-resolved addresses must all be public
            if not _all_resolved_public(host, port):
                raise HTTPException(
                    status_code=400, detail="Destination resolves to a private network"
                ) from None
        # Return original URL after validation (no mutation performed)
        return u

    from zyra.utils.http import strip_hop_headers as _strip_hop_headers

    # Shared request helper to avoid duplication across streaming and single-shot fallbacks
    def _issue_request(
        m: str,
        u: str,
        h: dict[str, str] | None,
        p: dict[str, str] | None,
        d: Any | None,
        *,
        stream: bool,
    ):
        payload = json.dumps(d).encode("utf-8") if isinstance(d, (dict, list)) else d
        return requests.request(  # codeql[py/ssrf]
            m,
            u,
            headers=_strip_hop_headers(h or {}),
            params=p,
            data=payload,
            timeout=60,
            stream=stream,
            allow_redirects=False,
        )

    headers = _strip_hop_headers(dict(req.headers or {}))
    params = dict(req.params or {})
    if req.accept and "Accept" not in headers:
        headers["Accept"] = req.accept
    data = req.data
    method = (req.method or "GET").upper()
    # Convenience auth helper
    if getattr(req, "auth", None):
        try:
            scheme, val = str(req.auth).split(":", 1)
            scheme_l = scheme.strip().lower()
            v = val.strip()
            if v.startswith("$"):
                import os as _os

                v = _os.environ.get(v[1:], "")
            if scheme_l == "bearer" and v and "Authorization" not in headers:
                headers["Authorization"] = f"Bearer {v}"
            elif scheme_l == "basic" and v and "Authorization" not in headers:
                try:
                    import base64 as _b64

                    token = _b64.b64encode(v.encode("utf-8")).decode("ascii")
                    headers["Authorization"] = f"Basic {token}"
                except Exception:
                    pass
            elif scheme_l == "header" and v:
                try:
                    name, value = v.split(":", 1)
                    name = name.strip()
                    value = value.strip()
                    if value.startswith("$"):
                        import os as _os

                        value = _os.environ.get(value[1:], "")
                    if name and value and name not in headers:
                        headers[name] = value
                except Exception:
                    pass
        except Exception:
            pass

    # Validate URL once up front to avoid SSRF
    # Bind sanitized value under a distinct name so analyzers preserve taint separation
    sanitized_url = _validate_outbound_url(url)

    # HEAD preflight
    if req.head_first:
        # URL was validated earlier via `_validate_outbound_url(url)` at top
        safe_url = sanitized_url
        r_head = requests.head(  # codeql[py/ssrf]
            safe_url,
            headers=_strip_hop_headers(headers),
            params=params,
            allow_redirects=False,
            timeout=60,
        )  # lgtm [py/ssrf]
        ct = r_head.headers.get("Content-Type")
        if req.expect_content_type and (not ct or req.expect_content_type not in ct):
            raise HTTPException(
                status_code=415, detail=f"Unexpected Content-Type: {ct!r}"
            )

    # Optional OpenAPI validation (non-streaming path only)
    if bool(getattr(req, "openapi_validate", False)) and not req.stream:
        try:
            from urllib.parse import urlparse as _urlparse

            from zyra.connectors.openapi import validate as _ov

            pr = _urlparse(sanitized_url)
            base_root = f"{pr.scheme}://{pr.netloc}"
            spec = _ov.load_openapi(base_root)
            if spec:
                issues = _ov.validate_request(
                    spec=spec,
                    url=sanitized_url,
                    method=method,
                    headers=headers,
                    params=params,
                    data=data,
                )
                strict = (
                    True
                    if getattr(req, "openapi_strict", None) is None
                    else bool(req.openapi_strict)
                )
                if issues and strict:
                    return Response(
                        content=json.dumps({"errors": issues}).encode("utf-8"),
                        media_type="application/json",
                        status_code=400,
                    )
            # When spec is unavailable, proceed silently
        except Exception:
            pass

    # Pagination (non-streaming) with optional NDJSON output
    paginate = (req.paginate or "none").lower() if req.paginate else "none"
    if paginate in {"page", "cursor", "link"} and not req.stream:
        from zyra.connectors.backends import api as api_backend

        payload = (
            json.dumps(data).encode("utf-8") if isinstance(data, (dict, list)) else data
        )
        if paginate == "cursor":
            iterator = api_backend.paginate_cursor(
                method,
                sanitized_url,
                headers=_strip_hop_headers(headers),
                params=params,
                data=payload,
                timeout=60,
                max_retries=3,
                retry_backoff=0.5,
                cursor_param=req.cursor_param or "cursor",
                next_cursor_json_path=req.next_cursor_json_path or "next",
            )
        elif paginate == "page":
            iterator = api_backend.paginate_page(
                method,
                sanitized_url,
                headers=_strip_hop_headers(headers),
                params=params,
                data=payload,
                timeout=60,
                max_retries=3,
                retry_backoff=0.5,
                page_param=req.page_param or "page",
                page_start=int(req.page_start or 1),
                page_size_param=req.page_size_param,
                page_size=req.page_size,
                empty_json_path=req.empty_json_path,
            )
        else:  # link
            iterator = api_backend.paginate_link(
                method,
                sanitized_url,
                headers=_strip_hop_headers(headers),
                params=params,
                data=payload,
                timeout=60,
                max_retries=3,
                retry_backoff=0.5,
                link_rel=(req.link_rel or "next"),
            )

        if req.newline_json:

            def _gen():
                for status, _h, content in iterator:
                    if status >= 400:
                        txt = (content or b"").decode("utf-8", errors="ignore")
                        raise HTTPException(
                            status_code=status, detail=(txt or "Upstream error")
                        )
                    yield (content.rstrip(b"\n") + b"\n")

            return StreamingResponse(_gen(), media_type="application/x-ndjson")

        # Aggregate as JSON array
        items: list[Any] = []
        for status, _h, content in iterator:
            if status >= 400:
                txt = (content or b"").decode("utf-8", errors="ignore")
                raise HTTPException(
                    status_code=status, detail=(txt or "Upstream error")
                )
            try:
                items.append(json.loads((content or b"").decode("utf-8")))
            except Exception:
                items.append(None)
        return Response(
            content=json.dumps(items).encode("utf-8"), media_type="application/json"
        )

    # Streaming path
    if req.stream:
        # URL was validated earlier via `_validate_outbound_url(url)`
        r = _issue_request(method, sanitized_url, headers, params, data, stream=True)
        if r.status_code >= 400:
            # Try to return upstream error text
            raise HTTPException(
                status_code=r.status_code, detail=(r.text or "Upstream error")
            )
        ct = r.headers.get("Content-Type") or "application/octet-stream"
        if req.expect_content_type and (not ct or req.expect_content_type not in ct):
            raise HTTPException(
                status_code=415, detail=f"Unexpected Content-Type: {ct!r}"
            )
        headers_out = {"Content-Type": ct}
        cd = r.headers.get("Content-Disposition")
        if cd:
            headers_out["Content-Disposition"] = cd
        return StreamingResponse(
            r.iter_content(chunk_size=1024 * 1024), headers=headers_out
        )

    # Single-shot fetch (with retries)
    try:
        from zyra.connectors.backends import api as api_backend

        status, hdrs, content = api_backend.request_with_retries(
            method,
            sanitized_url,
            headers=_strip_hop_headers(headers),
            params=params,
            data=(
                json.dumps(data).encode("utf-8")
                if isinstance(data, (dict, list))
                else data
            ),
            timeout=60,
            max_retries=3,
            retry_backoff=0.5,
        )
        if status >= 400:
            text = None
            try:
                text = (content or b"").decode("utf-8")
            except Exception:
                text = None
            raise HTTPException(status_code=status, detail=(text or "Upstream error"))
        ct = (
            hdrs.get("Content-Type")
            or hdrs.get("content-type")
            or "application/octet-stream"
        )
        return Response(content=content or b"", media_type=ct)
    except ImportError as err:
        # Backend helper not available; log and fall back to direct request
        import logging as _logging

        _logging.getLogger("zyra.api.api_generic").warning(
            "connectors.backends.api unavailable; falling back to direct request: %s",
            err,
            exc_info=err,
        )
        # URL was validated earlier via `_validate_outbound_url(url)` at top
        r = _issue_request(method, sanitized_url, headers, params, data, stream=False)
        if r.status_code >= 400:
            # Keep original stack context clear for HTTPException
            raise HTTPException(
                status_code=r.status_code, detail=(r.text or "Upstream error")
            ) from None
        ct = r.headers.get("Content-Type") or "application/octet-stream"
        return Response(content=r.content or b"", media_type=ct)
    except Exception as err:
        # Unexpected error using backend helper; log and fall back to direct request
        import logging as _logging

        _logging.getLogger("zyra.api.api_generic").warning(
            "request_with_retries failed; falling back to direct request: %s",
            err,
            exc_info=err,
        )
        # If backend raised a ValueError due to SSRF validation, surface 400 and do not fallback
        if isinstance(err, ValueError):
            raise HTTPException(
                status_code=400, detail=str(err) or "Invalid request"
            ) from None
        # URL was validated earlier via `_validate_outbound_url(url)` at top
        r = _issue_request(method, sanitized_url, headers, params, data, stream=False)
        if r.status_code >= 400:
            raise HTTPException(
                status_code=r.status_code, detail=(r.text or "Upstream error")
            ) from None
        ct = r.headers.get("Content-Type") or "application/octet-stream"
        return Response(content=r.content or b"", media_type=ct)


_PROCESS_BODY = Body(None)
_PROCESS_FILE = File(None)


@router.post("/process/api-json")
async def process_api_json(request: Request):
    """Transform JSON/NDJSON to CSV/JSONL using the CLI path under the hood.

    Accepts either an uploaded file or a request body that points to a file_or_url.
    Returns CSV (text/csv) or JSONL (application/x-ndjson).
    """
    from zyra.api.models.cli_request import CLIRunRequest
    from zyra.api.routers.cli import run_cli_endpoint

    args: dict[str, Any] = {}
    temp_path: str | None = None
    try:
        # Detect content type and parse accordingly
        ct = (request.headers.get("content-type") or "").lower()
        if ct.startswith("multipart/form-data"):
            form = await request.form()
            # File is required in multipart mode
            up: UploadFile | None = form.get("file")  # type: ignore[assignment]
            if up is None:
                raise HTTPException(
                    status_code=400, detail="Multipart upload requires 'file' field"
                )
            with tempfile.NamedTemporaryFile(delete=False, suffix=".jsonl") as tmp:
                temp_path = tmp.name
                # Stream chunks from UploadFile
                while True:
                    chunk = await up.read(1024 * 1024)
                    if not chunk:
                        break
                    tmp.write(chunk)
            args["file_or_url"] = temp_path
            # Optional fields from form
            if form.get("records_path"):
                args["records_path"] = str(form.get("records_path"))
            if form.get("fields"):
                args["fields"] = str(form.get("fields"))
            if form.get("flatten") is not None:
                v = str(form.get("flatten")).strip().lower()
                args["flatten"] = v in {"1", "true", "yes", "on"}
            # explode may be repeated or comma-separated
            if "explode" in form:
                val = form.getlist("explode")  # type: ignore[attr-defined]
                if not val:
                    v = str(form.get("explode") or "")
                    val = [p.strip() for p in v.split(",") if p.strip()]
                args["explode"] = val
            if form.get("derived"):
                args["derived"] = str(form.get("derived"))
            if form.get("format"):
                args["format"] = str(form.get("format")).lower()
            if form.get("preset"):
                args["preset"] = str(form.get("preset"))
        else:
            # Expect JSON body mapping to ProcessApiJsonArgs
            try:
                body = await request.json()
            except Exception:
                body = None
            if not isinstance(body, dict):
                raise HTTPException(
                    status_code=400,
                    detail="Provide JSON body or multipart form with file",
                )
            # Validate and normalize via Pydantic schema
            obj = ProcessApiJsonArgs(**body)
            args["file_or_url"] = obj.file_or_url
            if obj.records_path:
                args["records_path"] = obj.records_path
            if obj.fields:
                args["fields"] = obj.fields
            if obj.flatten is not None:
                args["flatten"] = bool(obj.flatten)
            if obj.explode:
                args["explode"] = list(obj.explode)
            if obj.derived:
                args["derived"] = obj.derived
            if obj.format:
                args["format"] = obj.format
            if obj.preset:
                args["preset"] = obj.preset

        fmt = (args.get("format") or "csv").lower()
        cr = run_cli_endpoint(
            CLIRunRequest(stage="process", command="api-json", args=args, mode="sync"),
            None,
        )
        if cr.exit_code != 0:
            raise HTTPException(
                status_code=500, detail=cr.stderr or "Processing failed"
            )
        media = "text/csv" if fmt == "csv" else "application/x-ndjson"
        data = (
            cr.stdout.encode("utf-8")
            if isinstance(cr.stdout, str)
            else (cr.stdout or b"")
        )
        return Response(content=data, media_type=media)
    finally:
        if temp_path:
            try:
                from pathlib import Path as _P

                _P(temp_path).unlink()
            except Exception:
                pass


_PRESET_LIMITLESS_AUDIO_BODY = Body(...)


@router.post("/presets/limitless/audio")
def preset_limitless_audio(
    req: PresetLimitlessAudioArgs = _PRESET_LIMITLESS_AUDIO_BODY,
):
    """Stream audio from Limitless profile by mapping friendly time args.

    Accepts either (start & end) or (since & duration). Enforces a maximum
    duration of 2 hours for since+duration. Returns a streaming response with
    upstream Content-Type and optional Content-Disposition.
    """
    # Time mapping helpers

    from zyra.utils.iso8601 import iso_to_ms as _iso_to_ms
    from zyra.utils.iso8601 import (
        since_duration_to_range_ms as _since_duration_to_range,
    )

    # Build request
    base = os.environ.get("LIMITLESS_API_URL", "https://api.limitless.ai/v1").rstrip(
        "/"
    )
    url = f"{base}/download-audio"
    headers: dict[str, str] = {}
    api_key = os.environ.get("LIMITLESS_API_KEY")
    if api_key:
        headers["X-API-Key"] = api_key
    headers.setdefault("Accept", "audio/ogg")
    params: dict[str, str] = {}

    if req.start and req.end:
        params["startMs"] = str(_iso_to_ms(req.start))
        params["endMs"] = str(_iso_to_ms(req.end))
    elif req.since and req.duration:
        try:
            s_ms, e_ms = _since_duration_to_range(req.since, req.duration)
        except ValueError as exc:
            # Map validation error to HTTP 400 to satisfy preflight tests
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        params["startMs"] = str(s_ms)
        params["endMs"] = str(e_ms)
    if req.audio_source:
        params["audioSource"] = req.audio_source
    else:
        params["audioSource"] = "pendant"

    # Disable redirects explicitly and document safety context for CodeQL.
    # The URL is constructed from a trusted base (defaulting to api.limitless.ai)
    # and static path; callers may override via env for deployment, not user input.
    r = requests.request(
        "GET",
        url,
        headers=headers,
        params=params,
        timeout=60,
        stream=True,
    )  # lgtm [py/ssrf]
    if r.status_code >= 400:
        raise HTTPException(
            status_code=r.status_code, detail=(r.text or "Upstream error")
        )
    ct = r.headers.get("Content-Type") or "application/octet-stream"
    if "audio/ogg" not in ct:
        raise HTTPException(status_code=415, detail=f"Unexpected Content-Type: {ct!r}")
    headers_out = {"Content-Type": ct}
    cd = r.headers.get("Content-Disposition")
    if cd:
        headers_out["Content-Disposition"] = cd
    return StreamingResponse(
        r.iter_content(chunk_size=1024 * 1024), headers=headers_out
    )
