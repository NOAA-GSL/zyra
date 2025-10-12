# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import argparse
import os
from typing import Any

from zyra.cli_common import add_output_option
from zyra.connectors.backends import ftp as ftp_backend
from zyra.connectors.backends import http as http_backend
from zyra.connectors.backends import s3 as s3_backend
from zyra.connectors.credentials import (
    CredentialResolutionError,
    apply_auth_header,
    apply_http_credentials,
    parse_header_strings,
    resolve_basic_auth_credentials,
    resolve_credentials,
)
from zyra.utils.cli_helpers import configure_logging_from_env
from zyra.utils.date_manager import DateManager
from zyra.utils.io_utils import open_output


def _sanitize_headers_for_validation(values: dict[str, str]) -> dict[str, str]:
    sensitive_headers = {
        "authorization",
        "proxy-authorization",
        "token",
        "secret",
        "key",
    }
    sanitized: dict[str, str] = {}
    for name, val in values.items():
        if name.lower() in sensitive_headers:
            sanitized[name] = "<redacted>"
        else:
            sanitized[name] = val
    return sanitized


def _cmd_http(ns: argparse.Namespace) -> int:
    """Acquire data over HTTP(S) and write to stdout or file."""
    if getattr(ns, "verbose", False):
        os.environ["ZYRA_VERBOSITY"] = "debug"
    elif getattr(ns, "quiet", False):
        os.environ["ZYRA_VERBOSITY"] = "quiet"
    if getattr(ns, "trace", False):
        os.environ["ZYRA_SHELL_TRACE"] = "1"
    configure_logging_from_env()
    headers = parse_header_strings(getattr(ns, "header", None))
    credential_entries = list(getattr(ns, "credential", []) or [])
    if credential_entries:
        try:
            resolved = resolve_credentials(
                credential_entries,
                credential_file=getattr(ns, "credential_file", None),
            )
        except CredentialResolutionError as exc:
            raise SystemExit(f"Credential error: {exc}") from exc
        apply_http_credentials(headers, resolved.values)
    apply_auth_header(headers, getattr(ns, "auth", None))

    inputs = list(getattr(ns, "inputs", []) or [])
    if getattr(ns, "manifest", None):
        try:
            from pathlib import Path

            with Path(ns.manifest).open(encoding="utf-8") as f:
                for line in f:
                    s = line.strip()
                    if s and not s.startswith("#"):
                        inputs.append(s)
        except Exception as e:
            raise SystemExit(f"Failed to read manifest: {e}") from e
    # Listing mode
    if getattr(ns, "list", False):
        urls = http_backend.list_files(
            ns.url,
            pattern=getattr(ns, "pattern", None),
            headers=headers or None,
        )
        # Optional date filter using DateManager on URL basenames
        since = getattr(ns, "since", None)
        until = getattr(ns, "until", None)
        # Support ISO period
        if not since and getattr(ns, "since_period", None):
            dm = DateManager()
            start, _ = dm.get_date_range_iso(ns.since_period)
            since = start.isoformat()
        if since or until:
            dm = DateManager(
                [getattr(ns, "date_format", None)]
                if getattr(ns, "date_format", None)
                else None
            )
            from datetime import datetime

            start = datetime.min if not since else datetime.fromisoformat(since)
            end = datetime.max if not until else datetime.fromisoformat(until)
            urls = [u for u in urls if dm.is_date_in_range(u, start, end)]
        for u in urls:
            print(u)
        return 0

    if inputs:
        if ns.output_dir is None:
            raise SystemExit("--output-dir is required with --inputs")
        from pathlib import Path

        outdir = Path(ns.output_dir)
        outdir.mkdir(parents=True, exist_ok=True)
        for u in inputs:
            data = http_backend.fetch_bytes(u, headers=headers or None)
            name = Path(u).name or "download.bin"
            with (outdir / name).open("wb") as f:
                f.write(data)
        return 0
    if os.environ.get("ZYRA_SHELL_TRACE"):
        import logging as _log

        from zyra.utils.cli_helpers import sanitize_for_log

        _log.info("+ http get '%s'", sanitize_for_log(ns.url))
    data = http_backend.fetch_bytes(ns.url, headers=headers or None)
    with open_output(ns.output) as f:
        f.write(data)
    return 0


def _cmd_s3(ns: argparse.Namespace) -> int:
    """Acquire data from S3 (s3:// or bucket/key) and write to stdout or file."""
    if getattr(ns, "verbose", False):
        os.environ["ZYRA_VERBOSITY"] = "debug"
    elif getattr(ns, "quiet", False):
        os.environ["ZYRA_VERBOSITY"] = "quiet"
    if getattr(ns, "trace", False):
        os.environ["ZYRA_SHELL_TRACE"] = "1"
    configure_logging_from_env()
    # Batch via s3:// URLs
    inputs = list(getattr(ns, "inputs", []) or [])
    if getattr(ns, "manifest", None):
        try:
            from pathlib import Path

            with Path(ns.manifest).open(encoding="utf-8") as f:
                for line in f:
                    s = line.strip()
                    if s and not s.startswith("#"):
                        inputs.append(s)
        except Exception as e:
            raise SystemExit(f"Failed to read manifest: {e}") from e
    # Listing mode
    if getattr(ns, "list", False):
        # Prefer full s3:// URL when provided
        prefix = (
            ns.url
            if getattr(ns, "url", None)
            else (ns.bucket if getattr(ns, "bucket", None) else None)
        )
        keys = s3_backend.list_files(
            prefix,
            pattern=getattr(ns, "pattern", None),
            since=(
                lambda sp, s: (
                    DateManager().get_date_range_iso(sp)[0].isoformat()
                    if sp and not s
                    else s
                )
            )(getattr(ns, "since_period", None), getattr(ns, "since", None)),
            until=getattr(ns, "until", None),
            date_format=getattr(ns, "date_format", None),
        )
        for k in keys or []:
            print(k)
        return 0

    if inputs:
        if ns.output_dir is None:
            raise SystemExit("--output-dir is required with --inputs")
        from pathlib import Path

        outdir = Path(ns.output_dir)
        outdir.mkdir(parents=True, exist_ok=True)
        for u in inputs:
            if os.environ.get("ZYRA_SHELL_TRACE"):
                import logging as _log

                from zyra.utils.cli_helpers import sanitize_for_log

                _log.info("+ s3 get '%s'", sanitize_for_log(u))
            data = s3_backend.fetch_bytes(u, unsigned=ns.unsigned)
            name = Path(u).name or "object.bin"
            with (outdir / name).open("wb") as f:
                f.write(data)
        return 0
    # Accept either s3://bucket/key or split bucket/key
    if ns.url.startswith("s3://"):
        data = s3_backend.fetch_bytes(ns.url, unsigned=ns.unsigned)
    else:
        data = s3_backend.fetch_bytes(ns.bucket, ns.key, unsigned=ns.unsigned)
    with open_output(ns.output) as f:
        f.write(data)
    return 0


def _cmd_ftp(ns: argparse.Namespace) -> int:
    """Acquire data from FTP and write to stdout or file."""
    configure_logging_from_env()
    credential_entries = list(getattr(ns, "credential", []) or [])
    if getattr(ns, "user", None):
        credential_entries.append(f"user={ns.user}")
    if getattr(ns, "password", None):
        credential_entries.append(f"password={ns.password}")
    username: str | None = None
    password: str | None = None
    if credential_entries:
        try:
            resolved = resolve_credentials(
                credential_entries,
                credential_file=getattr(ns, "credential_file", None),
            )
        except CredentialResolutionError as exc:
            raise SystemExit(f"Credential error: {exc}") from exc
        username, password = resolve_basic_auth_credentials(resolved.values)
    inputs = list(getattr(ns, "inputs", []) or [])
    if getattr(ns, "manifest", None):
        try:
            from pathlib import Path

            with Path(ns.manifest).open(encoding="utf-8") as f:
                for line in f:
                    s = line.strip()
                    if s and not s.startswith("#"):
                        inputs.append(s)
        except Exception as e:
            raise SystemExit(f"Failed to read manifest: {e}") from e
    # Listing mode
    if getattr(ns, "list", False):
        names = (
            ftp_backend.list_files(
                ns.path,
                pattern=getattr(ns, "pattern", None),
                since=(
                    lambda sp, s: (
                        DateManager().get_date_range_iso(sp)[0].isoformat()
                        if sp and not s
                        else s
                    )
                )(getattr(ns, "since_period", None), getattr(ns, "since", None)),
                until=getattr(ns, "until", None),
                date_format=getattr(ns, "date_format", None),
                username=username,
                password=password,
            )
            or []
        )
        for n in names:
            print(n)
        return 0

    # Sync mode
    if getattr(ns, "sync_dir", None):
        ftp_backend.sync_directory(
            ns.path,
            ns.sync_dir,
            pattern=getattr(ns, "pattern", None),
            since=(
                lambda sp, s: (
                    DateManager().get_date_range_iso(sp)[0].isoformat()
                    if sp and not s
                    else s
                )
            )(getattr(ns, "since_period", None), getattr(ns, "since", None)),
            until=getattr(ns, "until", None),
            date_format=getattr(ns, "date_format", None),
            username=username,
            password=password,
        )
        return 0

    if inputs:
        if ns.output_dir is None:
            raise SystemExit("--output-dir is required with --inputs")
        from pathlib import Path

        outdir = Path(ns.output_dir)
        outdir.mkdir(parents=True, exist_ok=True)
        for p in inputs:
            data = ftp_backend.fetch_bytes(p, username=username, password=password)
            name = Path(p).name or "download.bin"
            with (outdir / name).open("wb") as f:
                f.write(data)
        return 0
    data = ftp_backend.fetch_bytes(ns.path, username=username, password=password)
    with open_output(ns.output) as f:
        f.write(data)
    return 0


def _cmd_vimeo(ns: argparse.Namespace) -> int:  # pragma: no cover - placeholder
    """Placeholder for Vimeo acquisition; not implemented."""
    if getattr(ns, "verbose", False):
        os.environ["ZYRA_VERBOSITY"] = "debug"
    elif getattr(ns, "quiet", False):
        os.environ["ZYRA_VERBOSITY"] = "quiet"
    if getattr(ns, "trace", False):
        os.environ["ZYRA_SHELL_TRACE"] = "1"
    configure_logging_from_env()
    raise SystemExit("acquire vimeo is not implemented yet")


def _parse_kv_params(s: str | None) -> dict[str, str]:
    if not s:
        return {}
    out: dict[str, str] = {}
    for pair in s.split("&"):
        if not pair:
            continue
        if "=" in pair:
            k, v = pair.split("=", 1)
            out[k] = v
        else:
            out[pair] = ""
    return out


def _load_data_arg(data: str | None) -> bytes | str | dict | None:
    if not data:
        return None
    s = data.strip()
    if s.startswith("@"):
        from pathlib import Path

        path = s[1:]
        p = Path(path)
        b = p.read_bytes()
        # Try JSON first
        try:
            import json

            return json.loads(b.decode("utf-8"))
        except Exception:
            return b
    # Try to parse inline JSON
    try:
        import json

        return json.loads(s)
    except Exception:
        return s


def _cmd_api(ns: argparse.Namespace) -> int:
    """Call a REST API endpoint and write the response.

    Supports:
    - Methods, headers, params, and JSON/body data (``--data`` or ``@file``)
    - Streaming binary downloads with resume, content-type validation, and
      filename inference (``--stream``, ``--resume``, ``--expect-content-type``,
      ``--detect-filename``)
    - Pagination: cursor, page, and RFC 5988 Link with NDJSON output or
      aggregated JSON array (``--paginate``, ``--newline-json``)
    - Provider presets (e.g., ``--preset limitless-lifelogs`` and
      ``--preset limitless-audio``)
    """
    # Map verbosity/trace
    if getattr(ns, "verbose", False):
        os.environ["ZYRA_VERBOSITY"] = "debug"
    elif getattr(ns, "quiet", False):
        os.environ["ZYRA_VERBOSITY"] = "quiet"
    if getattr(ns, "trace", False):
        os.environ["ZYRA_SHELL_TRACE"] = "1"
    configure_logging_from_env()

    headers = parse_header_strings(getattr(ns, "header", None))
    params = _parse_kv_params(getattr(ns, "params", None))
    if getattr(ns, "content_type", None):
        headers.setdefault("Content-Type", ns.content_type)
    body = _load_data_arg(getattr(ns, "data", None))
    credential_entries = list(getattr(ns, "credential", []) or [])
    if credential_entries:
        try:
            resolved = resolve_credentials(
                credential_entries,
                credential_file=getattr(ns, "credential_file", None),
            )
        except CredentialResolutionError as exc:
            raise SystemExit(f"Credential error: {exc}") from exc
        apply_http_credentials(headers, resolved.values)
    apply_auth_header(headers, getattr(ns, "auth", None))
    validation_headers = _sanitize_headers_for_validation(headers)

    from zyra.connectors.backends import api as api_backend

    method = (getattr(ns, "method", "GET") or "GET").upper()
    paginate = getattr(ns, "paginate", "none") or "none"
    timeout = int(getattr(ns, "timeout", 60) or 60)
    max_retries = int(getattr(ns, "max_retries", 3) or 3)
    retry_backoff = float(getattr(ns, "retry_backoff", 0.5) or 0.5)
    allow_non_2xx = bool(getattr(ns, "allow_non_2xx", False))

    # OpenAPI: help/validation (before making requests)
    if getattr(ns, "openapi_help", False) or getattr(ns, "openapi_validate", False):
        from urllib.parse import urlparse as _urlparse  # noqa: I001
        from zyra.connectors.openapi import validate as _ov  # noqa: I001

        openapi_url = getattr(ns, "openapi_url", None)
        if openapi_url:
            spec = _ov.load_openapi_url(openapi_url)
        else:
            if not getattr(ns, "url", None):
                raise SystemExit("--url is required for OpenAPI help/validation")
            try:
                pr = _urlparse(ns.url)
                base_root = f"{pr.scheme}://{pr.netloc}"
            except Exception:
                base_root = ns.url
            spec = _ov.load_openapi(base_root)
        if not spec:
            print("OpenAPI: not found", file=__import__("sys").stderr)
            if getattr(ns, "openapi_help", False):
                return 0
        if getattr(ns, "openapi_help", False) and spec:
            txt = _ov.help_text(spec=spec, url=ns.url, method=method)
            print(txt)
            return 0
        if getattr(ns, "openapi_validate", False) and spec:
            issues = _ov.validate_request(
                spec=spec,
                url=ns.url,
                method=method,
                headers=validation_headers,
                params=params,
                data=body,
            )
            if issues:
                import sys as _sys

                for it in issues:
                    loc = it.get("loc")
                    name = it.get("name")
                    msg = it.get("message")
                    if (
                        isinstance(name, str)
                        and isinstance(msg, str)
                        and name.lower()
                        in {
                            "authorization",
                            "proxy-authorization",
                            "token",
                            "secret",
                            "key",
                        }
                    ):
                        msg = "<redacted>"
                    _sys.stderr.write(f"OpenAPI validation: {loc} {name}: {msg}\n")
                if getattr(ns, "openapi_strict", False):
                    raise SystemExit(2)
            else:
                print("OpenAPI validation: OK")
                return 0

    # Preset defaults (user-provided flags win)
    preset = getattr(ns, "preset", None)
    if preset == "limitless-lifelogs":
        if not getattr(ns, "paginate", None) or ns.paginate == "none":
            paginate = "cursor"
        if not getattr(ns, "cursor_param", None):
            ns.cursor_param = "cursor"
        if not getattr(ns, "next_cursor_json_path", None):
            ns.next_cursor_json_path = "meta.lifelogs.nextCursor"
        # Map --since to 'start'
        if getattr(ns, "since", None) and "start" not in params:
            params["start"] = ns.since
    elif preset == "limitless-audio":
        import os as _os

        # Default URL if not provided
        if not getattr(ns, "url", None):
            base = _os.environ.get("LIMITLESS_API_URL", "https://api.limitless.ai/v1")
            ns.url = base.rstrip("/") + "/download-audio"
        # Headers: Accept and expected content type
        headers.setdefault("Accept", "audio/ogg")
        if not getattr(ns, "expect_content_type", None):
            ns.expect_content_type = "audio/ogg"
        # Default audio source if not supplied
        if getattr(ns, "audio_source", None) and "audioSource" not in params:
            params["audioSource"] = ns.audio_source
        elif "audioSource" not in params:
            params["audioSource"] = "pendant"
        # Map start/end or since/duration to epoch ms (startMs/endMs)
        from datetime import datetime, timezone

        def _parse_iso(s: str) -> datetime:
            try:
                # Support 'Z'
                if s.endswith("Z"):
                    s = s[:-1] + "+00:00"
                return datetime.fromisoformat(s)
            except Exception as exc:  # pragma: no cover - defensive
                raise SystemExit(
                    f"Invalid ISO datetime for --start/--end: {s}"
                ) from exc

        def _to_ms(dt: datetime) -> str:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return str(int(dt.timestamp() * 1000))

        start_iso = getattr(ns, "start", None)
        end_iso = getattr(ns, "end", None)
        since_iso = getattr(ns, "since", None)
        duration_iso = getattr(ns, "duration", None)
        if start_iso and end_iso:
            start_dt = _parse_iso(start_iso)
            end_dt = _parse_iso(end_iso)
        elif since_iso and duration_iso:
            start_dt = _parse_iso(since_iso)
            # Robust ISO-8601 duration parsing (P[nD]T[nH][nM][nS])
            from zyra.utils.iso8601 import iso_duration_to_timedelta

            try:
                td = iso_duration_to_timedelta(duration_iso)
            except Exception as exc:
                raise SystemExit(
                    f"Unsupported ISO-8601 duration: {duration_iso}"
                ) from exc
            end_dt = start_dt + td
        else:
            # Expect startMs/endMs already via --params
            start_dt = end_dt = None
        if start_dt and end_dt:
            # Validate max 2 hours
            if (end_dt - start_dt).total_seconds() > 7200:
                raise SystemExit(
                    "Limitless audio maximum duration is 2 hours per request"
                )
            params.setdefault("startMs", _to_ms(start_dt))
            params.setdefault("endMs", _to_ms(end_dt))
        # Streaming is recommended
        if not getattr(ns, "stream", False):
            ns.stream = True

    pages: list[bytes] = []
    if paginate == "none" and not getattr(ns, "stream", False):
        status, _resp_headers, content = api_backend.request_with_retries(
            method,
            ns.url,
            headers=headers,
            params=params,
            data=body,
            timeout=timeout,
            max_retries=max_retries,
            retry_backoff=retry_backoff,
        )
        if not allow_non_2xx and status >= 400:
            raise SystemExit(f"HTTP error {status}")
        if getattr(ns, "pretty", False):
            try:
                import json

                obj = json.loads(content.decode("utf-8"))
                content = (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode(
                    "utf-8"
                )
            except Exception:
                pass
        with open_output(ns.output) as f:
            f.write(content)
        return 0

    # Streaming (binary-safe, large payloads)
    if getattr(ns, "stream", False):
        try:
            import requests as _requests  # type: ignore
        except Exception as exc:  # pragma: no cover - runtime error path
            raise SystemExit(
                "The 'requests' package is required for streaming; install extras: 'pip install \"zyra[connectors]\"'"
            ) from exc
        # Optional HEAD preflight
        if getattr(ns, "head_first", False):
            r_head = _requests.head(
                ns.url,
                headers=headers,
                params=params,
                timeout=timeout,
                allow_redirects=True,
            )
            ct = r_head.headers.get("Content-Type")
            if getattr(ns, "expect_content_type", None) and (
                not ct or ns.expect_content_type not in ct
            ):
                raise SystemExit(f"Unexpected Content-Type: {ct!r}")
        # Accept header
        if getattr(ns, "accept", None):
            headers.setdefault("Accept", ns.accept)
        # Resume support
        out_path = getattr(ns, "output", "-")
        start_at = 0
        if getattr(ns, "resume", False) and out_path not in (None, "-"):
            from pathlib import Path as _P

            p = _P(out_path)
            if p.is_file():
                start_at = p.stat().st_size
                if start_at > 0:
                    headers["Range"] = f"bytes={start_at}-"
        resp = _requests.request(
            method,
            ns.url,
            headers=headers,
            params=params,
            data=body,
            timeout=timeout,
            stream=True,
            allow_redirects=True,
        )
        status = resp.status_code
        if not allow_non_2xx and status >= 400:
            raise SystemExit(f"HTTP error {status}")
        ct = resp.headers.get("Content-Type")
        if getattr(ns, "expect_content_type", None) and (
            not ct or ns.expect_content_type not in ct
        ):
            raise SystemExit(f"Unexpected Content-Type: {ct!r}")
        # Detect filename when output is a directory
        out = getattr(ns, "output", "-") or "-"
        if out not in ("-", None):
            from pathlib import Path as _P

            out_p = _P(out)
            if (out_p.exists() and out_p.is_dir()) or str(out).endswith("/"):
                if not getattr(ns, "detect_filename", False):
                    raise SystemExit(
                        "Output is a directory; pass --detect-filename to infer a name or specify a file path"
                    )
                name = None
                cd = resp.headers.get("Content-Disposition") or ""
                if "filename=" in cd:
                    name = cd.split("filename=", 1)[1].strip().strip('"')
                if not name and ct:
                    ct_main = ct.split(";", 1)[0].strip().lower()
                    ext_map = {
                        "audio/ogg": ".ogg",
                        "audio/mpeg": ".mp3",
                        "audio/wav": ".wav",
                        "video/mp4": ".mp4",
                        "video/webm": ".webm",
                        "video/ogg": ".ogv",
                        "image/png": ".png",
                        "image/jpeg": ".jpg",
                        "image/gif": ".gif",
                        "image/webp": ".webp",
                        "application/pdf": ".pdf",
                        "application/zip": ".zip",
                        "application/octet-stream": ".bin",
                    }
                    ext = ext_map.get(ct_main)
                    if ext:
                        name = f"download{ext}"
                if not name:
                    name = "download.bin"
                out_p = out_p / name
                ns.output = str(out_p)
        # Write chunks
        total = 0
        try:
            total = int(resp.headers.get("Content-Length") or 0)
        except Exception:
            total = 0
        downloaded = 0
        show_progress = bool(getattr(ns, "progress", False)) and total > 0
        # When resuming and the file already exists, append to it; otherwise, open normally
        from contextlib import ExitStack as _ExitStack

        with _ExitStack() as _stack:
            if out not in ("-", None) and getattr(ns, "resume", False) and start_at > 0:
                from pathlib import Path as _P

                writer = _stack.enter_context(_P(ns.output).open("ab"))
            else:
                # Use standard helper which respects '-' to stdout
                from zyra.utils.io_utils import open_output as _open_output

                writer = _stack.enter_context(_open_output(ns.output))
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue
                writer.write(chunk)
                if show_progress:
                    downloaded += len(chunk)
                    try:
                        import sys as _sys

                        pct = (downloaded / total) * 100.0
                        _sys.stderr.write(
                            f"\rDownloaded {downloaded:,}/{total:,} bytes ({pct:5.1f}%)"
                        )
                        _sys.stderr.flush()
                    except Exception:
                        show_progress = False
        if show_progress:
            try:
                import sys as _sys

                _sys.stderr.write("\n")
                _sys.stderr.flush()
            except Exception:
                pass
        return 0

    # Pagination
    out_is_ndjson = bool(getattr(ns, "newline_json", False))
    if out_is_ndjson:
        with open_output(ns.output) as writer:
            if paginate == "cursor":
                cursor_param = getattr(ns, "cursor_param", "cursor")
                next_cursor_json_path = getattr(ns, "next_cursor_json_path", "next")
                for status, _h, content in api_backend.paginate_cursor(
                    method,
                    ns.url,
                    headers=headers,
                    params=params,
                    data=body,
                    timeout=timeout,
                    max_retries=max_retries,
                    retry_backoff=retry_backoff,
                    cursor_param=cursor_param,
                    next_cursor_json_path=next_cursor_json_path,
                ):
                    if not allow_non_2xx and status >= 400:
                        raise SystemExit(f"HTTP error {status}")
                    writer.write(content.rstrip(b"\n") + b"\n")
            elif paginate == "page":
                page_param = getattr(ns, "page_param", "page")
                page_start = int(getattr(ns, "page_start", 1) or 1)
                page_size_param = getattr(ns, "page_size_param", None)
                page_size = getattr(ns, "page_size", None)
                empty_json_path = getattr(ns, "empty_json_path", None)
                for status, _h, content in api_backend.paginate_page(
                    method,
                    ns.url,
                    headers=headers,
                    params=params,
                    data=body,
                    timeout=timeout,
                    max_retries=max_retries,
                    retry_backoff=retry_backoff,
                    page_param=page_param,
                    page_start=page_start,
                    page_size_param=page_size_param,
                    page_size=page_size,
                    empty_json_path=empty_json_path,
                ):
                    if not allow_non_2xx and status >= 400:
                        raise SystemExit(f"HTTP error {status}")
                    writer.write(content.rstrip(b"\n") + b"\n")
            elif paginate == "link":
                link_rel = getattr(ns, "link_rel", "next")
                for status, _h, content in api_backend.paginate_link(
                    method,
                    ns.url,
                    headers=headers,
                    params=params,
                    data=body,
                    timeout=timeout,
                    max_retries=max_retries,
                    retry_backoff=retry_backoff,
                    link_rel=link_rel,
                ):
                    if not allow_non_2xx and status >= 400:
                        raise SystemExit(f"HTTP error {status}")
                    writer.write(content.rstrip(b"\n") + b"\n")
            else:
                raise SystemExit(
                    "Unsupported --paginate value. Use 'none', 'page', 'cursor', or 'link'"
                )
        return 0

    # Aggregate paginated pages as a JSON array when not using NDJSON
    import json as _json

    if paginate == "cursor":
        for status, _h, content in api_backend.paginate_cursor(
            method,
            ns.url,
            headers=headers,
            params=params,
            data=body,
            timeout=timeout,
            max_retries=max_retries,
            retry_backoff=retry_backoff,
            cursor_param=getattr(ns, "cursor_param", "cursor"),
            next_cursor_json_path=getattr(ns, "next_cursor_json_path", "next"),
        ):
            if not allow_non_2xx and status >= 400:
                raise SystemExit(f"HTTP error {status}")
            pages.append(content)
    elif paginate == "page":
        for status, _h, content in api_backend.paginate_page(
            method,
            ns.url,
            headers=headers,
            params=params,
            data=body,
            timeout=timeout,
            max_retries=max_retries,
            retry_backoff=retry_backoff,
            page_param=getattr(ns, "page_param", "page"),
            page_start=int(getattr(ns, "page_start", 1) or 1),
            page_size_param=getattr(ns, "page_size_param", None),
            page_size=getattr(ns, "page_size", None),
            empty_json_path=getattr(ns, "empty_json_path", None),
        ):
            if not allow_non_2xx and status >= 400:
                raise SystemExit(f"HTTP error {status}")
            pages.append(content)
    elif paginate == "link":
        for status, _h, content in api_backend.paginate_link(
            method,
            ns.url,
            headers=headers,
            params=params,
            data=body,
            timeout=timeout,
            max_retries=max_retries,
            retry_backoff=retry_backoff,
            link_rel=getattr(ns, "link_rel", "next"),
        ):
            if not allow_non_2xx and status >= 400:
                raise SystemExit(f"HTTP error {status}")
            pages.append(content)
    else:
        raise SystemExit(
            "Unsupported --paginate value. Use 'none', 'page', 'cursor', or 'link'"
        )

    arr = []
    for b in pages:
        try:
            arr.append(_json.loads(b.decode("utf-8")))
        except Exception:
            arr.append(None)
    payload = (_json.dumps(arr, ensure_ascii=False) + "\n").encode("utf-8")
    with open_output(ns.output) as f:
        f.write(payload)
    return 0


def register_cli(acq_subparsers: Any) -> None:
    # http
    p_http = acq_subparsers.add_parser(
        "http",
        help="Fetch via HTTP(S)",
        description=(
            "Fetch a file via HTTP(S) to a local path. Optionally list/filter directory pages, "
            "or fetch multiple URLs with --inputs/--manifest."
        ),
    )
    p_http.add_argument("url")
    add_output_option(p_http)
    p_http.add_argument(
        "--list", action="store_true", help="List links on a directory page"
    )
    p_http.add_argument("--pattern", help="Regex to filter listed links")
    p_http.add_argument("--since", help="ISO date filter for list mode")
    p_http.add_argument(
        "--since-period",
        dest="since_period",
        help="ISO-8601 duration for lookback (e.g., P1Y, P6M, P7D, PT24H)",
    )
    p_http.add_argument("--until", help="ISO date filter for list mode")
    p_http.add_argument(
        "--date-format",
        dest="date_format",
        help="Filename date format for list filtering (e.g., YYYYMMDD)",
    )
    p_http.add_argument("--inputs", nargs="+", help="Multiple HTTP URLs to fetch")
    p_http.add_argument("--manifest", help="Path to a file listing URLs (one per line)")
    p_http.add_argument(
        "--output-dir",
        dest="output_dir",
        help="Directory to write outputs for --inputs",
    )
    p_http.add_argument(
        "--verbose", action="store_true", help="Verbose logging for this command"
    )
    p_http.add_argument(
        "--quiet", action="store_true", help="Quiet logging for this command"
    )
    p_http.add_argument(
        "--trace",
        action="store_true",
        help="Shell-style trace of key steps and external commands",
    )
    p_http.add_argument(
        "--header",
        action="append",
        help="Add custom HTTP header 'Name: Value' (repeatable)",
    )
    p_http.add_argument(
        "--auth",
        help=(
            "Convenience auth helper: 'bearer:$TOKEN' -> Authorization: Bearer <value>, "
            "'basic:user:pass' sets HTTP Basic auth"
        ),
    )
    p_http.add_argument(
        "--credential",
        action="append",
        dest="credential",
        help=(
            "Credential slot resolution (repeatable), e.g., 'token=$API_TOKEN' or "
            "'header.Authorization=@EUMETSAT_TOKEN'"
        ),
    )
    p_http.add_argument(
        "--credential-file",
        dest="credential_file",
        help="Optional dotenv file for resolving @KEY credentials",
    )
    p_http.set_defaults(func=_cmd_http)

    # s3
    p_s3 = acq_subparsers.add_parser(
        "s3",
        help="Fetch from S3",
        description=(
            "Fetch objects from Amazon S3 via s3:// URL or bucket/key. Supports unsigned access, "
            "listing prefixes, and batch via --inputs/--manifest."
        ),
    )
    # Either a single s3:// URL or bucket+key
    grp = p_s3.add_mutually_exclusive_group(required=True)
    grp.add_argument("--url", help="Full URL s3://bucket/key")
    grp.add_argument("--bucket", help="Bucket name")
    p_s3.add_argument("--key", help="Object key (when using --bucket)")
    p_s3.add_argument(
        "--unsigned", action="store_true", help="Use unsigned access for public buckets"
    )
    p_s3.add_argument("--list", action="store_true", help="List keys under a prefix")
    p_s3.add_argument("--pattern", help="Regex to filter listed keys")
    p_s3.add_argument("--since", help="ISO date filter for list mode")
    p_s3.add_argument(
        "--since-period",
        dest="since_period",
        help="ISO-8601 duration for lookback (e.g., P1Y, P6M, P7D, PT24H)",
    )
    p_s3.add_argument("--until", help="ISO date filter for list mode")
    p_s3.add_argument(
        "--date-format",
        dest="date_format",
        help="Filename date format for list filtering (e.g., YYYYMMDD)",
    )
    p_s3.add_argument("--inputs", nargs="+", help="Multiple s3:// URLs to fetch")
    p_s3.add_argument(
        "--manifest", help="Path to a file listing s3:// URLs (one per line)"
    )
    p_s3.add_argument(
        "--output-dir",
        dest="output_dir",
        help="Directory to write outputs for --inputs",
    )
    add_output_option(p_s3)
    p_s3.add_argument(
        "--verbose", action="store_true", help="Verbose logging for this command"
    )
    p_s3.add_argument(
        "--quiet", action="store_true", help="Quiet logging for this command"
    )
    p_s3.add_argument(
        "--trace",
        action="store_true",
        help="Shell-style trace of key steps and external commands",
    )
    p_s3.set_defaults(func=_cmd_s3)

    # ftp
    p_ftp = acq_subparsers.add_parser(
        "ftp",
        help="Fetch from FTP",
        description=(
            "Fetch files via FTP (single path or batch). Optionally list or sync directories to a local folder."
        ),
    )
    p_ftp.add_argument("path", help="ftp://host/path or host/path")
    add_output_option(p_ftp)
    p_ftp.add_argument(
        "--list", action="store_true", help="List files in an FTP directory"
    )
    p_ftp.add_argument(
        "--sync-dir", dest="sync_dir", help="Sync FTP directory to a local directory"
    )
    p_ftp.add_argument("--pattern", help="Regex to filter list/sync")
    p_ftp.add_argument("--since", help="ISO date filter for list/sync")
    p_ftp.add_argument(
        "--since-period",
        dest="since_period",
        help="ISO-8601 duration for lookback (e.g., P1Y, P6M, P7D, PT24H)",
    )
    p_ftp.add_argument("--until", help="ISO date filter for list/sync")
    p_ftp.add_argument(
        "--date-format",
        dest="date_format",
        help="Filename date format for filtering (e.g., YYYYMMDD)",
    )
    p_ftp.add_argument("--inputs", nargs="+", help="Multiple FTP paths to fetch")
    p_ftp.add_argument(
        "--manifest", help="Path to a file listing FTP paths (one per line)"
    )
    p_ftp.add_argument(
        "--output-dir",
        dest="output_dir",
        help="Directory to write outputs for --inputs",
    )
    p_ftp.add_argument(
        "--verbose", action="store_true", help="Verbose logging for this command"
    )
    p_ftp.add_argument(
        "--quiet", action="store_true", help="Quiet logging for this command"
    )
    p_ftp.add_argument(
        "--trace",
        action="store_true",
        help="Shell-style trace of key steps and external commands",
    )
    p_ftp.add_argument(
        "--user",
        help="FTP username (alias for --credential user=...)",
    )
    p_ftp.add_argument(
        "--password",
        help="FTP password (alias for --credential password=...)",
    )
    p_ftp.add_argument(
        "--credential",
        action="append",
        dest="credential",
        help=(
            "Credential slot resolution (repeatable), e.g., 'user=@FTP_USER' or "
            "'password=$FTP_PASS'"
        ),
    )
    p_ftp.add_argument(
        "--credential-file",
        dest="credential_file",
        help="Optional dotenv file for resolving @KEY credentials",
    )
    p_ftp.set_defaults(func=_cmd_ftp)

    # vimeo (placeholder)
    p_vimeo = acq_subparsers.add_parser(
        "vimeo",
        help="Fetch video by id (not implemented)",
        description=(
            "Placeholder for fetching Vimeo videos by id. Not implemented yet."
        ),
    )
    p_vimeo.add_argument("video_id")
    add_output_option(p_vimeo)
    p_vimeo.add_argument(
        "--verbose", action="store_true", help="Verbose logging for this command"
    )
    p_vimeo.add_argument(
        "--quiet", action="store_true", help="Quiet logging for this command"
    )
    p_vimeo.add_argument(
        "--trace",
        action="store_true",
        help="Shell-style trace of key steps and external commands",
    )
    p_vimeo.set_defaults(func=_cmd_vimeo)

    # api (generic REST)
    p_api = acq_subparsers.add_parser(
        "api",
        help="Generic REST API fetch",
        description=(
            "Call a REST API endpoint with headers/params/body. Supports cursor/page pagination."
        ),
    )
    p_api.add_argument(
        "--preset",
        choices=["limitless-lifelogs", "limitless-audio"],
        help="Apply provider-specific defaults (e.g., Limitless lifelogs cursor mapping; Limitless audio download)",
    )
    p_api.add_argument("--url", help="Target endpoint URL (may be set by preset)")
    p_api.add_argument(
        "--method",
        default="GET",
        help="HTTP method (GET, POST, DELETE, PUT, PATCH)",
    )
    add_output_option(p_api)
    p_api.add_argument(
        "--header",
        action="append",
        help="Custom header 'K: V' (repeatable)",
    )
    p_api.add_argument(
        "--content-type",
        dest="content_type",
        help="Content-Type header (e.g., application/json)",
    )
    p_api.add_argument(
        "--auth",
        help=(
            "Convenience auth helper: 'bearer:$TOKEN' -> Authorization: Bearer <value>, "
            "'basic:user:pass' -> Authorization: Basic <base64(user:pass)>"
        ),
    )
    p_api.add_argument(
        "--params",
        help="URL query parameters as k1=v1&k2=v2",
    )
    p_api.add_argument(
        "--credential",
        action="append",
        dest="credential",
        help="Credential slot resolution (repeatable), e.g., token=$API_TOKEN",
    )
    p_api.add_argument(
        "--credential-file",
        dest="credential_file",
        help="Optional dotenv file for resolving @KEY credentials",
    )
    p_api.add_argument(
        "--since",
        help="Convenience ISO start time; may map to provider param under presets",
    )
    p_api.add_argument(
        "--data",
        help="Inline JSON string or @path/to/file (JSON or raw)",
    )
    p_api.add_argument(
        "--paginate",
        choices=["none", "page", "cursor", "link"],
        default="none",
        help="Pagination mode",
    )
    # page-based
    p_api.add_argument("--page-param", default="page")
    p_api.add_argument("--page-start", type=int, default=1)
    p_api.add_argument("--page-size-param")
    p_api.add_argument("--page-size", type=int)
    p_api.add_argument(
        "--empty-json-path",
        help="Dot path for list to detect empty page (stops when empty)",
    )
    # cursor-based
    p_api.add_argument("--cursor-param", default="cursor")
    p_api.add_argument(
        "--next-cursor-json-path",
        default="next",
        help="Dot path to next cursor in response",
    )
    # link-based
    p_api.add_argument(
        "--link-rel",
        dest="link_rel",
        default="next",
        help="Link relation to follow when --paginate link (default: next)",
    )
    # output behavior
    p_api.add_argument(
        "--newline-json",
        action="store_true",
        help="Write each page as one JSON line (NDJSON)",
    )
    p_api.add_argument(
        "--pretty",
        action="store_true",
        default=True,
        help="Pretty-print JSON for single response",
    )
    # Binary/streaming options
    p_api.add_argument(
        "--stream", action="store_true", help="Stream large/binary responses to output"
    )
    p_api.add_argument(
        "--detect-filename",
        dest="detect_filename",
        action="store_true",
        help="When output is a directory, infer filename from headers/content-type",
    )
    p_api.add_argument(
        "--accept",
        help="Set Accept header (e.g., audio/ogg)",
    )
    p_api.add_argument(
        "--expect-content-type",
        dest="expect_content_type",
        help="Fail if response Content-Type does not contain this value",
    )
    p_api.add_argument(
        "--head-first",
        dest="head_first",
        action="store_true",
        help="Send a HEAD request before GET to validate type/size",
    )
    p_api.add_argument(
        "--resume", action="store_true", help="Attempt HTTP Range resume when possible"
    )
    p_api.add_argument(
        "--progress",
        action="store_true",
        help="Show simple byte progress when Content-Length is available",
    )
    # OpenAPI-aided help and validation
    p_api.add_argument(
        "--openapi-help",
        action="store_true",
        help="Fetch OpenAPI and print required params/headers/body for the resolved operation",
    )
    p_api.add_argument(
        "--openapi-validate",
        action="store_true",
        help="Validate provided params/headers/body against OpenAPI (prints issues)",
    )
    p_api.add_argument(
        "--openapi-strict",
        action="store_true",
        help="Exit non-zero when --openapi-validate finds issues",
    )
    p_api.add_argument(
        "--openapi-url",
        help=(
            "Explicit OpenAPI spec URL (json/yaml). Overrides automatic discovery based on --url"
        ),
    )
    # Limitless audio helpers
    p_api.add_argument(
        "--start", help="ISO-8601 start time (e.g., 2025-08-01T00:00:00Z)"
    )
    p_api.add_argument("--end", help="ISO-8601 end time (e.g., 2025-08-01T02:00:00Z)")
    p_api.add_argument(
        "--duration",
        help="ISO-8601 duration for limitless-audio preset (e.g., PT2H, PT30M)",
    )
    p_api.add_argument(
        "--audio-source",
        dest="audio_source",
        choices=["pendant", "app"],
        help="Limitless audio source (maps to audioSource)",
    )
    # retries & timeouts
    p_api.add_argument("--timeout", type=int, default=60)
    p_api.add_argument("--max-retries", type=int, default=3)
    p_api.add_argument("--retry-backoff", type=float, default=0.5)
    p_api.add_argument(
        "--allow-non-2xx",
        action="store_true",
        help="Do not exit non-zero for HTTP >= 400",
    )
    p_api.add_argument(
        "--verbose", action="store_true", help="Verbose logging for this command"
    )
    p_api.add_argument(
        "--quiet", action="store_true", help="Quiet logging for this command"
    )
    p_api.add_argument(
        "--trace",
        action="store_true",
        help="Shell-style trace of key steps and external commands",
    )
    p_api.set_defaults(func=_cmd_api)
