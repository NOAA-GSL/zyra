# SPDX-License-Identifier: Apache-2.0
"""Utilities for sampling frames from video sources."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

from zyra.connectors.backends import vimeo as vimeo_backend


class VideoExtractionError(RuntimeError):
    """Raised when frame extraction fails."""


@dataclass(frozen=True)
class VideoMetadata:
    duration_seconds: float
    width: int | None = None
    height: int | None = None
    codec: str | None = None


def ensure_ffmpeg() -> None:
    """Ensure ``ffmpeg`` and ``ffprobe`` are available in ``PATH``."""

    if shutil.which("ffmpeg") is None:
        raise VideoExtractionError(
            "ffmpeg is required to extract frames from video sources."
        )
    if shutil.which("ffprobe") is None:
        raise VideoExtractionError("ffprobe is required to probe video metadata.")


def resolve_video_source(source: str, credentials: dict[str, str] | None = None) -> str:
    """Return a playable URL/path for ``source``.

    Supports Vimeo URIs (``vimeo:12345`` or ``https://vimeo.com/12345``) by returning a
    progressive download link using PyVimeo.
    """

    parsed = urlparse(source)
    if source.startswith("vimeo:") or "vimeo.com" in parsed.netloc:
        video_id = _extract_vimeo_id(source)
        url = vimeo_backend.get_download_url(
            video_id,
            token=(credentials or {}).get("access_token"),
            client_id=(credentials or {}).get("client_id"),
            client_secret=(credentials or {}).get("client_secret"),
        )
        if not url:
            raise VideoExtractionError(
                f"Unable to resolve Vimeo download URL for video '{video_id}'."
            )
        return url
    return source


def _extract_vimeo_id(value: str) -> str:
    value = value.strip()
    if value.startswith("vimeo:"):
        return value.split(":", 1)[1].strip("/")
    parsed = urlparse(value)
    path = parsed.path.strip("/")
    if path.startswith("video/"):
        path = path.split("/", 1)[1]
    if path.startswith("videos/"):
        path = path.split("/", 1)[1]
    return path


def probe_video_metadata(source: str) -> VideoMetadata:
    """Return video metadata using ``ffprobe``."""

    ensure_ffmpeg()

    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        source,
    ]
    try:
        proc = subprocess.run(cmd, check=True, capture_output=True, text=True)
    except (
        subprocess.CalledProcessError
    ) as exc:  # pragma: no cover - depends on ffprobe
        raise VideoExtractionError(
            f"ffprobe failed to inspect video: {exc.stderr or exc.stdout or exc}"
        ) from exc

    payload = json.loads(proc.stdout or "{}")
    fmt = payload.get("format", {})
    duration = fmt.get("duration")
    if duration is None:
        raise VideoExtractionError("ffprobe did not return a duration for the video.")

    try:
        duration_seconds = float(duration)
    except ValueError as exc:
        raise VideoExtractionError(
            f"Invalid duration reported by ffprobe: {duration}"
        ) from exc

    width = height = codec = None
    for stream in payload.get("streams", []):
        if stream.get("codec_type") == "video":
            width = stream.get("width")
            height = stream.get("height")
            codec = stream.get("codec_name")
            break

    return VideoMetadata(
        duration_seconds=duration_seconds,
        width=width,
        height=height,
        codec=codec,
    )


def extract_frames(
    source: str,
    *,
    output_dir: Path,
    fps: float,
    image_format: str = "png",
) -> list[Path]:
    """Extract frames from ``source`` into ``output_dir`` using ``ffmpeg``."""

    ensure_ffmpeg()
    output_dir.mkdir(parents=True, exist_ok=True)
    for file in output_dir.glob(f"frame_*.{image_format}"):
        file.unlink()

    fps = max(fps, 0.1)
    pattern = output_dir / f"frame_%05d.{image_format}"

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        source,
        "-vf",
        f"fps={fps}",
        "-y",
        str(pattern),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as exc:  # pragma: no cover - depends on ffmpeg
        raise VideoExtractionError(
            f"ffmpeg failed to extract frames: {exc.stderr.decode('utf-8', 'ignore')}"
        ) from exc

    frames = sorted(output_dir.glob(f"frame_*.{image_format}"))
    if not frames:
        raise VideoExtractionError("No frames were extracted from the video.")
    return frames


def compute_frame_timestamps(
    *,
    frames: Iterable[Path],
    start_time: datetime,
    fps: float,
) -> list[dict[str, Any]]:
    """Return frame metadata with timestamps for each frame."""

    start_time = _coerce_utc(start_time)
    frame_interval = timedelta(seconds=1.0 / fps if fps > 0 else 1.0)
    entries: list[dict[str, Any]] = []
    for index, frame in enumerate(sorted(frames)):
        timestamp = start_time + frame_interval * index
        iso = timestamp.isoformat().replace("+00:00", "Z")
        display = timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")
        entries.append(
            {
                "path": str(frame),
                "timestamp": iso,
                "display_timestamp": display,
            }
        )
    return entries


def _coerce_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_datetime(value: str) -> datetime:
    """Parse ISO-8601 datetime strings with optional ``Z`` suffix."""

    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def format_datetime(dt: datetime) -> str:
    return _coerce_utc(dt).isoformat().replace("+00:00", "Z")


def compute_end_time(start: datetime, frame_count: int, fps: float) -> datetime:
    if frame_count <= 1 or fps <= 0:
        return start
    delta = (frame_count - 1) / fps
    return _coerce_utc(start) + timedelta(seconds=delta)
