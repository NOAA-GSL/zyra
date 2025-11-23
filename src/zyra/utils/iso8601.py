# SPDX-License-Identifier: Apache-2.0
"""Lightweight ISO-8601 helpers for datetimes and durations.

Provides parsing helpers used across CLI, API routers, and MCP tools to avoid
duplicating slightly different implementations.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

try:  # NumPy is an optional dependency in a few lightweight environments
    import numpy as _np
except Exception:  # pragma: no cover - fallback when numpy unavailable
    _np = None


def iso_to_ms(s: str) -> int:
    """Convert an ISO-8601 datetime string to epoch milliseconds.

    Accepts a trailing ``Z`` for UTC.
    """
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def to_datetime(value: Any) -> datetime | None:
    """Coerce ``value`` into a timezone-aware ``datetime`` where possible.

    Accepts ``datetime`` objects (naive assumed UTC), ISO strings with optional
    ``Z`` suffix, and ``numpy.datetime64`` values. Returns ``None`` when the
    input is empty or cannot be interpreted as a timestamp.
    """

    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        token = value.strip()
        if not token:
            return None
        if token.endswith("Z"):
            token = token[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(token)
        except ValueError:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
                try:
                    dt = datetime.strptime(token, fmt)
                    break
                except ValueError:
                    continue
            else:
                return None
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    if _np is not None and isinstance(value, _np.datetime64):  # pragma: no cover
        # Use nanosecond precision to preserve sub-second detail when present
        ts = value.astype("datetime64[ns]").astype("int64")
        return datetime.fromtimestamp(ts / 1_000_000_000, tz=timezone.utc)
    if hasattr(value, "item"):
        try:
            return to_datetime(value.item())
        except Exception:
            return None
    return None


# Supported duration subset: P[nD]T[nH][nM][nS]
# Examples: PT30M, PT2H, PT1H30M, P1DT30M
# Notes:
# - The leading "P" is required
# - The date part currently supports only days (D)
# - The time part is introduced by "T" and supports hours (H), minutes (M), seconds (S)
# - Each component is optional but at least one must be present overall
_DUR_RX = re.compile(
    r"""
    ^P                             # Duration designator
    (?:(?P<days>\d+)D)?           # Optional days
    (?:                            # Optional time part
      T
      (?:(?P<hours>\d+)H)?        # Optional hours
      (?:(?P<minutes>\d+)M)?      # Optional minutes
      (?:(?P<seconds>\d+)S)?      # Optional seconds
    )?
    $                             # End of string
    """,
    re.IGNORECASE | re.VERBOSE,
)


def iso_duration_to_timedelta(s: str) -> timedelta:
    """Parse a subset of ISO-8601 durations into ``timedelta``.

    Supports ``P[nD]T[nH][nM][nS]`` patterns, e.g., ``PT30M``, ``PT2H``,
    ``PT1H30M``, or ``P1DT30M``.
    """
    m = _DUR_RX.match((s or "").strip().upper())
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
    return td


def since_duration_to_range_ms(
    since: str, duration: str, *, max_hours: int | None = 2
) -> tuple[int, int]:
    """Return a (startMs, endMs) tuple given ISO ``since`` + ``duration``.

    Enforces a maximum window when ``max_hours`` is provided.
    """
    start_ms = iso_to_ms(since)
    td = iso_duration_to_timedelta(duration)
    end_ms = start_ms + int(td.total_seconds() * 1000)
    if max_hours is not None and (end_ms - start_ms) > max_hours * 60 * 60 * 1000:
        raise ValueError(f"Maximum duration is {max_hours} hours")
    return start_ms, end_ms
