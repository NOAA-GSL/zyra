from __future__ import annotations

import json
import hashlib
from pathlib import Path

from datavizhub.api.server import app


def test_openapi_sha256_snapshot() -> None:
    spec = app.openapi()
    s = json.dumps(spec, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(s.encode()).hexdigest()
    snap_path = Path('tests/snapshots/openapi_sha256.txt')
    assert snap_path.exists(), "Missing snapshot file tests/snapshots/openapi_sha256.txt"
    snap = snap_path.read_text().strip()
    assert snap == digest
