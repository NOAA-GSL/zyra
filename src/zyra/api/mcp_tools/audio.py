"""MCP tool helpers for audio downloads.

Currently implements a profile-driven ``download_audio`` helper that supports
the ``limitless`` provider. It maps ISO-8601 time ranges to provider-specific
parameters, validates content type, and streams output to ``DATA_DIR``.
"""

# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import os
from typing import Any

import requests

from zyra.connectors.credentials import (
    CredentialResolutionError,
    resolve_credentials,
)
from zyra.utils.env import env_path
from zyra.utils.iso8601 import iso_to_ms, since_duration_to_range_ms


def _infer_filename_from_headers(
    headers: dict[str, str], default: str = "download.bin"
) -> str:
    """Infer a filename from Content-Disposition or Content-Type.

    Falls back to ``default`` when no hints are available.
    """
    cd = headers.get("Content-Disposition") or headers.get("content-disposition") or ""
    if "filename=" in cd:
        name = cd.split("filename=", 1)[1].strip().strip('"')
        if name:
            return name
    ct = headers.get("Content-Type") or headers.get("content-type") or ""
    if ct:
        ct_main = ct.split(";", 1)[0].strip().lower()
        ext_map = {
            "audio/ogg": ".ogg",
            "audio/mpeg": ".mp3",
            "audio/wav": ".wav",
            "video/mp4": ".mp4",
            "video/webm": ".webm",
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "application/pdf": ".pdf",
            "application/zip": ".zip",
        }
        ext = ext_map.get(ct_main)
        if ext:
            return f"download{ext}"
    return default


def _iso_to_ms(s: str) -> int:
    return iso_to_ms(s)


def _since_duration_to_range(since: str, duration: str) -> tuple[int, int]:
    return since_duration_to_range_ms(since, duration, max_hours=2)


def download_audio(
    *,
    profile: str = "limitless",
    start: str | None = None,
    end: str | None = None,
    since: str | None = None,
    duration: str | None = None,
    audio_source: str | None = None,
    output_dir: str | None = None,
    credentials: dict[str, str] | None = None,
    credential: list[str] | None = None,
    credential_file: str | None = None,
) -> dict[str, Any]:
    """Download audio for a provider profile and save under ``DATA_DIR``.

    Returns a dict with keys:
    - ``path``: relative path under DATA_DIR
    - ``content_type``: MIME type from upstream response
    - ``size_bytes``: total bytes written
    """
    # Resolve base DATA_DIR and ensure caller-provided output_dir stays within it
    from pathlib import Path

    base_dir = env_path("DATA_DIR", "_work").resolve()
    subdir = output_dir or "downloads"
    # Reject absolute paths and traversal segments before joining
    sd = Path(subdir)
    if sd.is_absolute() or any(part in {"", ".", ".."} for part in sd.parts):
        raise ValueError("Invalid output_dir: must be a relative subdirectory")
    # Construct candidate and ensure it does not escape base_dir (no absolute paths / traversal)
    try:
        candidate = (
            base_dir / sd
        ).resolve()  # lgtm [py/path-injection] [py/uncontrolled-data-in-path-expression]
        # Python 3.10: Path.is_relative_to exists
        if not candidate.is_relative_to(base_dir):  # type: ignore[attr-defined]
            raise ValueError("Invalid output_dir: must be a subdirectory of DATA_DIR")
    except Exception as exc:
        raise ValueError(
            "Invalid output_dir: must be a subdirectory of DATA_DIR"
        ) from exc
    out_dir: Path = candidate
    # Directory is under DATA_DIR after explicit sanitize + resolve + containment check
    out_dir.mkdir(
        parents=True, exist_ok=True
    )  # lgtm [py/path-injection] [py/uncontrolled-data-in-path-expression]

    if profile.lower() != "limitless":
        raise ValueError("Unsupported profile; only 'limitless' is implemented")

    base = os.environ.get("LIMITLESS_API_URL", "https://api.limitless.ai/v1").rstrip(
        "/"
    )
    url = f"{base}/download-audio"
    headers: dict[str, str] = {}

    credential_entries: list[str] = []
    if credential:
        credential_entries.extend([c for c in credential if c])
    if credentials:
        credential_entries.extend(f"{k}={v}" for k, v in credentials.items())
    resolved_token: str | None = None
    if credential_entries:
        try:
            resolved = resolve_credentials(
                credential_entries, credential_file=credential_file
            )
        except CredentialResolutionError as exc:
            raise ValueError(str(exc)) from exc
        resolved_token = (
            resolved.get("api_key")
            or resolved.get("token")
            or resolved.get("bearer")
            or resolved.get("access_token")
        )
    api_key = resolved_token or os.environ.get("LIMITLESS_API_KEY")
    if api_key:
        headers["X-API-Key"] = api_key
    headers.setdefault("Accept", "audio/ogg")
    params: dict[str, str] = {}

    if start and end:
        params["startMs"] = str(_iso_to_ms(start))
        params["endMs"] = str(_iso_to_ms(end))
    elif since and duration:
        s_ms, e_ms = _since_duration_to_range(since, duration)
        params["startMs"] = str(s_ms)
        params["endMs"] = str(e_ms)
    else:
        # Allow explicit startMs/endMs via output params in future; for now require mapping
        raise ValueError("Provide start+end or since+duration")

    if audio_source:
        params["audioSource"] = audio_source
    else:
        params["audioSource"] = "pendant"

    # Request streaming
    r = requests.request(
        "GET", url, headers=headers, params=params, timeout=60, stream=True
    )
    if r.status_code >= 400:
        txt = r.text or "Upstream error"
        raise RuntimeError(f"Upstream error {r.status_code}: {txt}")
    ct = r.headers.get("Content-Type") or "application/octet-stream"
    if "audio/ogg" not in ct:
        raise RuntimeError(f"Unexpected Content-Type: {ct}")

    # Derive a safe filename from headers; strip any path components
    from pathlib import Path as _P

    name = _infer_filename_from_headers(r.headers)
    safe_name = _P(name).name or "download.bin"
    candidate = (out_dir / safe_name).resolve()
    try:
        if not candidate.is_relative_to(out_dir):  # type: ignore[attr-defined]
            safe_name = "download.bin"
            candidate = (out_dir / safe_name).resolve()
    except Exception:
        safe_name = "download.bin"
        candidate = (out_dir / safe_name).resolve()
    out_path = candidate
    size = 0
    with out_path.open("wb") as f:
        for chunk in r.iter_content(chunk_size=1024 * 1024):
            if not chunk:
                continue
            f.write(chunk)
            size += len(chunk)

    rel = out_path.relative_to(base_dir)
    return {"path": str(rel), "content_type": ct, "size_bytes": size}
