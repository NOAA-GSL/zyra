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

from zyra.utils.env import env_path


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
    """Convert an ISO-8601 datetime string to epoch milliseconds.

    Accepts a trailing ``Z`` for UTC.
    """
    from datetime import datetime, timezone

    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _since_duration_to_range(since: str, duration: str) -> tuple[int, int]:
    """Return (startMs, endMs) from ISO ``since`` + ``duration``.

    Parses a subset of ISO-8601 durations via regex: supports days and time
    components (hours/minutes/seconds). Enforces a maximum window of two hours
    and raises ``ValueError`` for invalid/unsupported inputs.
    """
    import re
    from datetime import timedelta

    start_ms = _iso_to_ms(since)
    s = (duration or "").strip().upper()
    # Pattern: P[nD][T[nH][nM][nS]] — capture days/hours/minutes/seconds if present
    m = re.match(
        r"^P(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?$",
        s,
        re.IGNORECASE,
    )
    if not m:
        raise ValueError(
            "Unsupported ISO-8601 duration; expected P[nD]T[nH][nM][nS] (e.g., PT30M, PT2H, PT1H30M)"
        )
    days = int(m.group("days") or 0)
    hours = int(m.group("hours") or 0)
    minutes = int(m.group("minutes") or 0)
    seconds = int(m.group("seconds") or 0)
    td = timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)
    if td.total_seconds() <= 0:
        raise ValueError("Duration must be greater than zero")
    end_ms = start_ms + int(td.total_seconds() * 1000)
    if (end_ms - start_ms) > 2 * 60 * 60 * 1000:
        raise ValueError("Maximum duration is 2 hours")
    return start_ms, end_ms


def download_audio(
    *,
    profile: str = "limitless",
    start: str | None = None,
    end: str | None = None,
    since: str | None = None,
    duration: str | None = None,
    audio_source: str | None = None,
    output_dir: str | None = None,
) -> dict[str, Any]:
    """Download audio for a provider profile and save under ``DATA_DIR``.

    Returns a dict with keys:
    - ``path``: relative path under DATA_DIR
    - ``content_type``: MIME type from upstream response
    - ``size_bytes``: total bytes written
    """
    base_dir = env_path("DATA_DIR", "_work")
    out_dir = base_dir / (output_dir or "downloads")
    out_dir.mkdir(parents=True, exist_ok=True)

    if profile.lower() != "limitless":
        raise ValueError("Unsupported profile; only 'limitless' is implemented")

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

    name = _infer_filename_from_headers(r.headers)
    out_path = out_dir / name
    size = 0
    with out_path.open("wb") as f:
        for chunk in r.iter_content(chunk_size=1024 * 1024):
            if not chunk:
                continue
            f.write(chunk)
            size += len(chunk)

    rel = out_path.relative_to(base_dir)
    return {"path": str(rel), "content_type": ct, "size_bytes": size}
