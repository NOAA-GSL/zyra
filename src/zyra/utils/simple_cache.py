# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
import os
import time
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _default_cache_dir() -> Path:
    root = os.getenv("ZYRA_CACHE_DIR") or ".cache/zyra_enrich"
    return Path(root)


@dataclass
class CacheRecord:
    key: str
    expires_at: float
    payload: Any


def _key_to_path(base: Path, key: str) -> Path:
    # Avoid long filenames; hash the key but keep a readable prefix
    import hashlib

    # Use SHA-256 for stronger hashing of cache keys
    h = hashlib.sha256(key.encode("utf-8")).hexdigest()
    prefix = key[:32].replace(os.sep, "_").replace(":", "_")
    fname = f"{prefix}.{h}.json"
    return base / fname


def get(key: str) -> Any | None:
    base = _default_cache_dir()
    try:
        p = _key_to_path(base, key)
        if not p.exists():
            return None
        text = p.read_text(encoding="utf-8")
        data = json.loads(text)
        if float(data.get("expires_at") or 0) < time.time():
            # Expired; best-effort delete
            with suppress(Exception):
                p.unlink()
            return None
        return data.get("payload")
    # Note: json.JSONDecodeError is a subclass of ValueError; ValueError covers it.
    # Catch JSON decoding explicitly for clarity; JSONDecodeError subclasses ValueError.
    except (OSError, json.JSONDecodeError, TypeError):
        return None


def set(key: str, value: Any, ttl_seconds: int) -> None:
    base = _default_cache_dir()
    try:
        base.mkdir(parents=True, exist_ok=True)
        p = _key_to_path(base, key)
        rec = {
            "key": key,
            "expires_at": time.time() + max(0, int(ttl_seconds)),
            "payload": value,
        }
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(rec), encoding="utf-8")
        tmp.replace(p)
    except (OSError, ValueError, TypeError):
        # Cache failures must never be fatal
        return


# End of module
