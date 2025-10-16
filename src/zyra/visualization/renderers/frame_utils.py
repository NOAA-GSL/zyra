# SPDX-License-Identifier: Apache-2.0
"""Shared helpers for processing frame manifests and timestamps."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from dateutil import parser as date_parser

from zyra.utils.date_manager import DateManager

_SIMPLE_TYPES = (str, int, float, bool)


def load_manifest_entries(text: str) -> list[dict[str, Any]] | None:
    """Parse a JSON manifest describing frame entries.

    Accepts JSON arrays or mapping objects with ``frames``/``items``/``entries`` keys.
    Returns a list of dictionaries each containing at least ``path``. Additional scalar
    metadata is preserved when possible.
    """

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None

    frames: list[dict[str, Any]] | None = None
    if isinstance(data, list):
        frames = [item for item in data if isinstance(item, dict)]
    elif isinstance(data, dict):
        for key in ("frames", "items", "entries"):
            value = data.get(key)
            if isinstance(value, list):
                frames = [item for item in value if isinstance(item, dict)]
                break
        if frames is None and "path" in data:
            frames = [data]
    if not frames:
        return []

    results: list[dict[str, Any]] = []
    for item in frames:
        path = None
        for key in ("path", "texture", "uri", "url", "source"):
            value = item.get(key)
            if value:
                path = str(value)
                break
        if not path:
            continue
        entry: dict[str, Any] = {"path": path}
        if "timestamp" in item:
            entry["timestamp"] = item["timestamp"]
        elif "time" in item:
            entry["timestamp"] = item["time"]
        elif "datetime" in item:
            entry["timestamp"] = item["datetime"]

        if "display" in item:
            entry["display_timestamp"] = item["display"]
        elif "display_timestamp" in item:
            entry["display_timestamp"] = item["display_timestamp"]

        if isinstance(item.get("label"), str):
            entry["label"] = item["label"]

        metadata: dict[str, Any] = {}
        if isinstance(item.get("metadata"), dict):
            for key, value in item["metadata"].items():
                if isinstance(value, _SIMPLE_TYPES) or value is None:
                    metadata[key] = value
        for key, value in item.items():
            if key in {
                "path",
                "texture",
                "uri",
                "url",
                "source",
                "timestamp",
                "time",
                "datetime",
                "display",
                "display_timestamp",
                "metadata",
                "label",
            }:
                continue
            if isinstance(value, _SIMPLE_TYPES) or value is None:
                metadata.setdefault(key, value)
        if metadata:
            entry["metadata"] = metadata
        results.append(entry)
    return results


def finalize_frame_entries(
    entries: list[dict[str, Any]],
    *,
    time_key: str | None = None,
    parse_formats: list[str] | None = None,
    display_format: str | None = None,
) -> list[dict[str, Any]]:
    """Normalize frame entries by resolving timestamps and sanitizing metadata."""

    date_manager = DateManager(parse_formats or [])
    normalized: list[dict[str, Any]] = []
    for raw in entries:
        path = raw.get("path")
        if not path:
            continue
        metadata = raw.get("metadata")
        if not isinstance(metadata, dict):
            metadata = None

        timestamp_value = raw.get("timestamp")
        if timestamp_value is None and time_key:
            if time_key in raw:
                timestamp_value = raw[time_key]
            elif metadata:
                timestamp_value = metadata.get(time_key)

        iso_value, display_value = _normalize_timestamp(
            timestamp_value, date_manager, display_format
        )
        if display_value is None and isinstance(raw.get("display_timestamp"), str):
            candidate = raw["display_timestamp"].strip()
            if candidate:
                display_value = candidate

        entry: dict[str, Any] = {"path": str(path)}
        if iso_value:
            entry["timestamp"] = iso_value
        if display_value:
            entry["display_timestamp"] = display_value

        if metadata:
            clean_meta = {
                key: value
                for key, value in metadata.items()
                if isinstance(value, _SIMPLE_TYPES) or value is None
            }
            if clean_meta:
                entry["metadata"] = clean_meta

        if isinstance(raw.get("label"), str):
            label = raw["label"].strip()
            if label:
                entry["label"] = label

        normalized.append(entry)
    return normalized


def _normalize_timestamp(
    value: Any,
    date_manager: DateManager,
    display_format: str | None,
) -> tuple[str | None, str | None]:
    """Convert a timestamp-like value to ISO-8601 and a display string."""

    if value is None:
        return None, None

    dt: datetime | None = None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, (int, float)):
        dt = datetime.fromtimestamp(_coerce_epoch(value), tz=timezone.utc)
    else:
        value_str = str(value).strip()
        if not value_str:
            return None, None
        try:
            dt = date_parser.isoparse(value_str)
        except (ValueError, TypeError):
            dt = None
        if dt is None and value_str.isdigit():
            try:
                dt = datetime.fromtimestamp(
                    _coerce_epoch(int(value_str)), tz=timezone.utc
                )
            except (ValueError, OSError, OverflowError):
                dt = None
        if dt is None:
            extracted = None
            try:
                extracted = date_manager.extract_date_time(value_str)
            except Exception:
                extracted = None
            if extracted:
                try:
                    dt = date_parser.isoparse(extracted)
                except (ValueError, TypeError):
                    dt = None
        if dt is None:
            return None, value_str

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)

    iso_value = dt.isoformat().replace("+00:00", "Z")
    if display_format:
        try:
            display_value = dt.strftime(display_format)
        except Exception:
            display_value = iso_value.replace("T", " ").replace("Z", " UTC")
    else:
        display_value = iso_value.replace("T", " ").replace("Z", " UTC")
    return iso_value, display_value


def _coerce_epoch(value: float) -> float:
    """Interpret a numeric value as seconds (detecting millisecond precision)."""

    seconds = float(value)
    if seconds > 1e12:
        # Heuristic: treat as milliseconds.
        seconds /= 1000.0
    return seconds
