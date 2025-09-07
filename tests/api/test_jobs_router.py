from __future__ import annotations

from pathlib import Path

from zyra.api.routers import jobs as jobs_router
from zyra.api.server import app
from zyra.api.workers import jobs as jb


def test_get_job_status_returns_expected_keys(tmp_path: Path) -> None:
    jid = jb.submit_job("process", "convert-format", {})
    rec = jb.get_job(jid)
    rec["status"] = "succeeded"
    rec["exit_code"] = 0
    res = jobs_router.get_job_status(jid)
    # Pydantic v2+: prefer model_dump; fall back to dict()
    to_dict = getattr(res, "model_dump", None)
    data = to_dict() if callable(to_dict) else res.dict()  # type: ignore[attr-defined]
    assert data["job_id"] == jid
    assert data["status"] == "succeeded"
    assert "stdout" in data and "stderr" in data and "exit_code" in data


def test_download_job_output_file_response(tmp_path: Path) -> None:
    jid = jb.submit_job("visualize", "heatmap", {})
    # Create a fake results file
    rd = Path("/tmp/datavizhub_results") / jid
    rd.mkdir(parents=True, exist_ok=True)
    out = rd / "out.txt"
    out.write_text("hello", encoding="utf-8")
    rec = jb.get_job(jid)
    rec["status"] = "succeeded"
    rec["output_file"] = str(out)

    resp = jobs_router.download_job_output(jid, file=None, zip=None)
    # Starlette FileResponse instance
    from starlette.responses import FileResponse as FR  # type: ignore

    assert isinstance(resp, FR)


def test_openapi_contains_jobs_paths() -> None:
    # app.openapi doesn't require httpx
    spec = app.openapi()
    paths = spec.get("paths", {})
    assert "/v1/jobs/{job_id}" in paths
    assert "/v1/jobs/{job_id}/manifest" in paths
    assert "/v1/jobs/{job_id}/download" in paths


def test_download_ttl_expired_returns_410(monkeypatch, tmp_path: Path) -> None:
    jid = jb.submit_job("visualize", "heatmap", {})
    rd = Path("/tmp/datavizhub_results") / jid
    rd.mkdir(parents=True, exist_ok=True)
    out = rd / "old.bin"
    out.write_bytes(b"123")
    # Set file mtime in the past
    import os
    import time

    old_time = time.time() - 10_000
    os.utime(out, (old_time, old_time))
    # Set TTL small so it's expired
    monkeypatch.setenv("DATAVIZHUB_RESULTS_TTL_SECONDS", "1")
    # Should raise HTTPException 410
    from fastapi import HTTPException

    try:
        jobs_router.download_job_output(jid, file=None, zip=None)
        assert False, "Expected HTTPException for expired artifact"
    except HTTPException as exc:
        assert exc.status_code == 410
