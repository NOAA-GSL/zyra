from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterable


def env(key: str, default: str | None = None) -> str | None:
    """Read `ZYRA_<KEY>` with fallback to `DATAVIZHUB_<KEY>`.

    Returns the string value or the provided default when both are unset.
    """
    return os.environ.get(f"ZYRA_{key}", os.environ.get(f"DATAVIZHUB_{key}", default))


def env_bool(key: str, default: bool = False) -> bool:
    val = env(key)
    if val is None:
        return default
    return str(val).strip().lower() in {"1", "true", "yes", "on"}


def env_int(key: str, default: int) -> int:
    val = env(key)
    if val is None or str(val).strip() == "":
        return default
    try:
        return int(str(val))
    except ValueError:
        return default


def env_seconds(key: str, default: int) -> int:
    """Read an integer seconds value, with fallback to default on errors."""
    return env_int(key, default)


def env_path(key: str, default: str) -> Path:
    return Path(env(key, default) or default)


def coalesce(*values: Iterable[Any]) -> Any:
    """Return the first value that is not None and not empty string."""
    for v in values:
        if v is not None and v != "":
            return v
    return None
