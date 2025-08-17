from __future__ import annotations

from pathlib import Path

from datavizhub.api.routers import jobs as jobs_router
from datavizhub.api.routers import files as files_router
from datavizhub.api.workers import jobs as jb


def test_upload_run_download_happy_path(tmp_path: Path) -> None:
    # Simulate an uploaded NetCDF-like file (classic CDF magic)
    fid = "testfid1234"
    up = files_router.UPLOAD_DIR
    up.mkdir(parents=True, exist_ok=True)
    uploaded = up / f"{fid}_demo.nc"
    uploaded.write_bytes(b"CDF\x00\x00\x00dummy")

    # Submit and run a job that writes an explicit output file (decimate local)
    jid = jb.submit_job("decimate", "local", {})
    dest = Path("/tmp") / f"e2e_out_{jid}.bin"
    args = {"input": f"file_id:{fid}", "path": str(dest)}
    jb.start_job(jid, "decimate", "local", args)

    # Manifest exists and lists output.txt
    manifest = jobs_router.get_job_manifest(jid)
    names = [a.get("name") for a in manifest.get("artifacts", [])]
    assert Path(str(dest)).name in names

    # Download default (should pick copied output file)
    resp = jobs_router.download_job_output(jid, file=None, zip=None)
    from starlette.responses import FileResponse as FR  # type: ignore

    assert isinstance(resp, FR)
