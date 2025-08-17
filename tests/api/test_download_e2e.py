from __future__ import annotations

from pathlib import Path

from datavizhub.api.routers import jobs as jobs_router
from datavizhub.api.workers import jobs as jb
from datavizhub.api.workers.executor import write_manifest


def test_e2e_results_manifest_and_download(tmp_path: Path) -> None:
    # Create a job and a results file
    jid = jb.submit_job("visualize", "heatmap", {})
    rd = Path("/tmp/datavizhub_results") / jid
    rd.mkdir(parents=True, exist_ok=True)
    f = rd / "hello.txt"
    f.write_text("hello world", encoding="utf-8")
    # Mark job as completed and set output_file
    rec = jb.get_job(jid)
    rec["status"] = "succeeded"
    rec["exit_code"] = 0
    rec["output_file"] = str(f)
    # Write manifest
    write_manifest(jid)
    # Fetch manifest via router
    manifest = jobs_router.get_job_manifest(jid)
    names = [a.get("name") for a in manifest.get("artifacts", [])]
    assert "hello.txt" in names
    # Download specific file
    resp = jobs_router.download_job_output(jid, file="hello.txt", zip=None)
    from starlette.responses import FileResponse as FR  # type: ignore

    assert isinstance(resp, FR)
    # On-demand zip
    resp2 = jobs_router.download_job_output(jid, file=None, zip=1)
    # Ensure a zip was created in results dir
    zpath = rd / f"{jid}.zip"
    assert zpath.exists()
