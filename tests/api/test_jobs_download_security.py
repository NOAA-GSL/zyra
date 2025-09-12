from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from zyra.api.routers import jobs as jobs_router


def test_select_download_path_rejects_symlink_escape(
    tmp_path: Path, monkeypatch
) -> None:
    # Point results dir to temp base
    base = tmp_path / "results"
    monkeypatch.setenv("DATAVIZHUB_RESULTS_DIR", str(base))
    job_id = "jidsec001"
    rd = base / job_id
    rd.mkdir(parents=True, exist_ok=True)

    # Create a file outside the job results dir
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")

    # Create a symlink within the job dir pointing outside
    evil = rd / "evil.txt"
    try:
        evil.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks not supported on this platform")

    # A valid file inside the results dir
    good = rd / "good.txt"
    good.write_text("ok", encoding="utf-8")

    # Good selection resolves and returns a path under results dir
    p = jobs_router._select_download_path(job_id, "good.txt")
    assert p.resolve() == good.resolve()

    # Symlink selection is rejected with 400
    with pytest.raises(HTTPException) as ei:
        jobs_router._select_download_path(job_id, "evil.txt")
    assert ei.value.status_code == 400
