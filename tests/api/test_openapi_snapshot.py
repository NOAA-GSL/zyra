from __future__ import annotations

import json
from pathlib import Path

from zyra.api.server import app


def test_openapi_paths_snapshot() -> None:
    """Compare OpenAPI paths to a committed snapshot for router changes.

    If this test fails due to intentional changes, update tests/snapshots/openapi_paths.json
    by running: poetry run python scripts/dump_openapi.py | jq '.paths | keys' > tests/snapshots/openapi_paths.json
    """
    spec = app.openapi()
    current = sorted(list((spec.get("paths") or {}).keys()))
    snap_path = Path("tests/snapshots/openapi_paths.json")
    assert (
        snap_path.exists()
    ), "Missing snapshot file tests/snapshots/openapi_paths.json"
    snap = json.loads(snap_path.read_text())
    assert sorted(snap) == current
