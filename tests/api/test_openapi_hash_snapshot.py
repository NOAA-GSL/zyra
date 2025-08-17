from __future__ import annotations

import json
import copy
import hashlib
from pathlib import Path

from datavizhub.api.server import app


def _normalize_openapi(spec: dict) -> dict:
    """Return a copy of the spec with volatile fields removed.

    - Removes info.version so snapshot stays stable across version bumps.
    """
    # Deep copy to avoid mutating FastAPI's cached spec
    data = copy.deepcopy(spec)
    try:
        if isinstance(data.get("info"), dict):
            data["info"].pop("version", None)
    except Exception:
        pass
    return data


def test_openapi_sha256_snapshot() -> None:
    spec = _normalize_openapi(app.openapi())
    s = json.dumps(spec, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(s.encode()).hexdigest()
    snap_path = Path("tests/snapshots/openapi_sha256.txt")
    assert (
        snap_path.exists()
    ), "Missing snapshot file tests/snapshots/openapi_sha256.txt"
    snap = snap_path.read_text().strip()
    assert snap == digest
