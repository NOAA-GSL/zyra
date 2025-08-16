"""Jobs router: job status, cancellation, manifest, and artifact downloads.

This module exposes HTTP endpoints under the "jobs" tag. All endpoints are
protected by API key authentication when `DATAVIZHUB_API_KEY` is set.
"""

from __future__ import annotations

import mimetypes
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from datavizhub.api.workers import jobs as jobs_backend
from datavizhub.api.models.cli_request import JobStatusResponse


router = APIRouter(tags=["jobs"])


def _results_dir_for(job_id: str) -> Path:
    root = Path(os.environ.get("DATAVIZHUB_RESULTS_DIR", "/tmp/datavizhub_results"))
    return root / job_id


def _select_download_path(job_id: str, specific_file: Optional[str]) -> Path:
    rd = _results_dir_for(job_id)
    if not rd.exists():
        raise HTTPException(status_code=404, detail="Results not found")
    if specific_file:
        # Prevent path traversal and symlink escapes by resolving and ensuring
        # the target is within the results directory for this job.
        p = (rd / specific_file).resolve()
        base = rd.resolve()
        try:
            _ = p.relative_to(base)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid file parameter")
        if not p.exists() or not p.is_file():
            raise HTTPException(status_code=404, detail="Requested file not found")
        return p
    # Default selection: prefer zip, else first file
    zips = list(rd.glob("*.zip"))
    if zips:
        return zips[0]
    files = [p for p in rd.iterdir() if p.is_file() and p.name != "manifest.json"]
    if not files:
        raise HTTPException(status_code=404, detail="No artifacts available")
    files.sort()
    return files[0]


@router.get("/jobs/{job_id}", response_model=JobStatusResponse, summary="Get job status")
def get_job_status(job_id: str) -> JobStatusResponse:
    """Return current job status, stdio captures, exit code, and resolved inputs.

    Parameters
    - job_id: The opaque job identifier returned by /cli/run (async).
    """
    rec = jobs_backend.get_job(job_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobStatusResponse(
        job_id=job_id,
        status=rec.get("status", "queued"),
        stdout=rec.get("stdout"),
        stderr=rec.get("stderr"),
        exit_code=rec.get("exit_code"),
        output_file=rec.get("output_file"),
        resolved_input_paths=rec.get("resolved_input_paths"),
    )


@router.delete("/jobs/{job_id}", summary="Cancel a queued job")
def cancel_job_endpoint(job_id: str) -> dict:
    """Attempt to cancel a queued job.

    Returns {"status":"canceled","job_id":job_id} on success or 409 if the
    job is not cancelable.
    """
    ok = jobs_backend.cancel_job(job_id)
    if not ok:
        raise HTTPException(status_code=409, detail="Cannot cancel this job")
    return {"status": "canceled", "job_id": job_id}


@router.get(
    "/jobs/{job_id}/download",
    summary="Download job artifact",
    description=(
        "Downloads the job's artifact. By default serves the packaged ZIP if present, "
        "otherwise the first available artifact. Use `?file=NAME` to fetch a specific file "
        "from the manifest, or `?zip=1` to dynamically package all artifacts into a ZIP."
    ),
    responses={
        404: {"description": "Job, artifact, or results not found"},
        410: {"description": "Artifact expired due to TTL cleanup"},
    },
)
def download_job_output(
    job_id: str,
    file: Optional[str] = Query(default=None, description="Specific filename from manifest.json"),
    zip: Optional[int] = Query(default=None, description="If 1, package all artifacts into a zip on demand"),
):
    """Stream the selected job artifact (ZIP or individual file).

    Query parameters
    - file: Specific filename from the job manifest (guards path traversal)
    - zip: When 1, package current artifacts into a zip on demand
    """
    rec = jobs_backend.get_job(job_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Job not found")

    def _zip_results_dir(job_id: str) -> Optional[Path]:
        rd = _results_dir_for(job_id)
        if not rd.exists():
            return None
        zpath = rd / f"{job_id}.zip"
        try:
            import zipfile

            with zipfile.ZipFile(str(zpath), mode="w", compression=zipfile.ZIP_DEFLATED) as zf:  # type: ignore[attr-defined]
                for p in rd.iterdir():
                    if p.name in {"manifest.json", zpath.name} or not p.is_file():
                        continue
                    zf.write(str(p), p.name)
            return zpath
        except Exception:
            return None

    # Choose file: either query param, or pick default in results dir
    if zip and int(zip) == 1:
        zp = _zip_results_dir(job_id)
        if not zp:
            raise HTTPException(status_code=404, detail="No artifacts to zip")
        p = zp
    else:
        p = _select_download_path(job_id, file)

    if not p.exists():
        # If TTL cleanup removed it
        raise HTTPException(status_code=410, detail="Output file no longer available")

    # TTL policy: refuse downloads older than DATAVIZHUB_RESULTS_TTL_SECONDS (default 24h)
    try:
        ttl = int(os.environ.get("DATAVIZHUB_RESULTS_TTL_SECONDS", "86400") or 86400)
    except Exception:
        ttl = 86400
    try:
        import time

        age = time.time() - p.stat().st_mtime
        if age > ttl:
            try:
                p.unlink()
            except Exception:
                pass
            raise HTTPException(status_code=410, detail="Output file expired")
    except FileNotFoundError:
        raise HTTPException(status_code=410, detail="Output file no longer available")

    # MIME type detection with python-magic if present
    media_type = None
    try:
        import magic  # type: ignore

        mt = magic.Magic(mime=True).from_file(str(p))
        media_type = str(mt) if mt else None
    except Exception:
        media_type, _ = mimetypes.guess_type(p.name)
    return FileResponse(str(p), media_type=media_type or "application/octet-stream", filename=p.name)


@router.get(
    "/jobs/{job_id}/manifest",
    summary="Get job artifacts manifest",
    description=(
        "Returns manifest.json describing all artifacts produced by a job, including name, size, "
        "modified time (mtime), and media_type. Use the `name` entries with `?file=` on /download."
    ),
)
def get_job_manifest(job_id: str):
    """Return the manifest.json for job artifacts (name, path, size, mtime, media_type)."""
    rd = _results_dir_for(job_id)
    mf = rd / "manifest.json"
    if not mf.exists():
        raise HTTPException(status_code=404, detail="Manifest not found")
    import json

    try:
        return json.loads(mf.read_text(encoding="utf-8"))
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to read manifest")
