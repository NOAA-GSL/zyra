"""Jobs router: job status, cancellation, manifest, and artifact downloads.

This module exposes HTTP endpoints under the "jobs" tag. All endpoints are
protected by API key authentication when `DATAVIZHUB_API_KEY` is set.
"""

from __future__ import annotations

import mimetypes
import os
from pathlib import Path
import re
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from datavizhub.api.workers import jobs as jobs_backend
from datavizhub.api.models.cli_request import JobStatusResponse


router = APIRouter(tags=["jobs"])

# Strict allowlists for user-controlled path segments
SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,255}$")
# Restrict job_id to a conservative length and charset (8–64 chars)
SAFE_JOB_ID_RE = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


def _is_safe_segment(segment: str, *, for_job_id: bool = False) -> bool:
    """Return True if ``segment`` is a safe single path component.

    Allows only a conservative set of characters and rejects any separators,
    traversal tokens, or empty values. ``for_job_id`` applies a tighter length
    constraint appropriate for job identifiers.
    """
    if not isinstance(segment, str) or not segment:
        return False
    # Reject path separators outright
    if "/" in segment or "\\" in segment:
        return False
    if segment in {".", ".."}:
        return False
    pat = SAFE_JOB_ID_RE if for_job_id else SAFE_NAME_RE
    return bool(pat.fullmatch(segment))


def _require_safe_job_id(unsafe_job_id: str) -> str:
    """Validate and return a safe job_id or raise HTTPException(400).

    Centralizes job_id sanitization to make dataflow explicit for security
    tools and to prevent accidental bypasses.
    """
    if not _is_safe_segment(unsafe_job_id, for_job_id=True):
        raise HTTPException(status_code=400, detail="Invalid job_id parameter")
    return unsafe_job_id


def _results_dir_for(job_id: str) -> Path:
    # Inline, explicit sanitization for static analysis and defense-in-depth
    if not isinstance(job_id, str) or not job_id:
        raise HTTPException(status_code=400, detail="Invalid job_id parameter")
    # Reject absolute paths and traversal/separators
    if os.path.isabs(job_id):
        raise HTTPException(status_code=400, detail="Invalid job_id parameter")
    if job_id != os.path.basename(job_id):
        # Ensures no separators and no traversal like "../x"
        raise HTTPException(status_code=400, detail="Invalid job_id parameter")
    # Allowlist characters (tighten further than basename check)
    if not SAFE_JOB_ID_RE.fullmatch(job_id):
        raise HTTPException(status_code=400, detail="Invalid job_id parameter")

    # Compute results dir with normalized join and containment check
    base = os.path.normpath(os.environ.get("DATAVIZHUB_RESULTS_DIR", "/tmp/datavizhub_results"))
    full = os.path.normpath(os.path.join(base, job_id))
    try:
        if os.path.commonpath([base, full]) != base:
            raise HTTPException(status_code=400, detail="Invalid job_id parameter")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid job_id parameter")
    rd = Path(full)
    # Optionally refuse symlinked root directory
    try:
        if Path(base).is_symlink():
            raise HTTPException(status_code=500, detail="Results root directory misconfigured (symlink not allowed)")
    except Exception:
        pass
    return rd


def _select_download_path(job_id: str, specific_file: Optional[str]) -> Path:
    # Validate job_id early and derive results dir (inline containment check)
    if not isinstance(job_id, str) or not job_id:
        raise HTTPException(status_code=400, detail="Invalid job_id parameter")
    if os.path.isabs(job_id) or job_id != os.path.basename(job_id) or not SAFE_JOB_ID_RE.fullmatch(job_id):
        raise HTTPException(status_code=400, detail="Invalid job_id parameter")
    root = os.environ.get("DATAVIZHUB_RESULTS_DIR", "/tmp/datavizhub_results")
    base = os.path.normpath(root)
    full = os.path.normpath(os.path.join(base, job_id))
    try:
        common = os.path.commonpath([base, full])
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid job_id parameter")
    if common != base:
        raise HTTPException(status_code=400, detail="Invalid job_id parameter")
    rd = Path(full)
    if not rd.exists():
        raise HTTPException(status_code=404, detail="Results not found")
    if specific_file:
        # Only allow a single safe filename (no directories)
        if not _is_safe_segment(specific_file) or specific_file != os.path.basename(specific_file):
            raise HTTPException(status_code=400, detail="Invalid file parameter")
        # Compose file path via normalized join and verify containment again
        base = os.path.normpath(os.environ.get("DATAVIZHUB_RESULTS_DIR", "/tmp/datavizhub_results"))
        full_file = os.path.normpath(os.path.join(base, job_id, specific_file))
        try:
            if os.path.commonpath([base, full_file]) != base:
                raise HTTPException(status_code=400, detail="Invalid file parameter")
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid file parameter")
        p = Path(full_file)
        # Enforce existence and regular file, and reject symlinks.
        if p.is_symlink() or (not p.exists()) or (not p.is_file()):
            raise HTTPException(status_code=404, detail="Requested file not found")
        return p
    # Default selection: prefer zip, else first file
    try:
        base = os.path.normpath(os.environ.get("DATAVIZHUB_RESULTS_DIR", "/tmp/datavizhub_results"))
        full = os.path.normpath(os.path.join(base, job_id))
        if os.path.commonpath([base, full]) != base:
            raise HTTPException(status_code=400, detail="Invalid job_id parameter")
        names = os.listdir(full)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Results not found")
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to enumerate results")

    # Prefer a zip artifact if present
    zips: list[Path] = []
    for name in names:
        if name.endswith(".zip"):
            p = Path(os.path.join(full, name))
            if p.is_file():
                zips.append(p)
    if zips:
        zips.sort(key=lambda x: x.name)
        return zips[0]

    # Otherwise, pick the first regular file (excluding manifest)
    files: list[Path] = []
    for name in names:
        if name == "manifest.json":
            continue
        p = Path(os.path.join(full, name))
        if p.is_file():
            files.append(p)
    if not files:
        raise HTTPException(status_code=404, detail="No artifacts available")
    files.sort(key=lambda x: x.name)
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
    file: Optional[str] = Query(
        default=None,
        description="Specific filename from manifest.json",
    ),
    zip: Optional[int] = Query(default=None, description="If 1, package all artifacts into a zip on demand"),
):
    """Stream the selected job artifact (ZIP or individual file).

    Query parameters
    - file: Specific filename from the job manifest (guards path traversal)
    - zip: When 1, package current artifacts into a zip on demand
    """
    # Validate job_id early and use a distinct variable to avoid taint flow
    jid = job_id
    if not isinstance(jid, str) or not jid or os.path.isabs(jid) or jid != os.path.basename(jid) or not SAFE_JOB_ID_RE.fullmatch(jid):
        raise HTTPException(status_code=400, detail="Invalid job_id parameter")

    rec = jobs_backend.get_job(jid)
    if not rec:
        raise HTTPException(status_code=404, detail="Job not found")

    def _zip_results_dir(job_id: str) -> Optional[Path]:
        # Inline sanitize job_id and derive results dir
        if not isinstance(job_id, str) or not job_id:
            return None
        if os.path.isabs(job_id) or job_id != os.path.basename(job_id) or not SAFE_JOB_ID_RE.fullmatch(job_id):
            return None
        base = os.path.normpath(os.environ.get("DATAVIZHUB_RESULTS_DIR", "/tmp/datavizhub_results"))
        full = os.path.normpath(os.path.join(base, job_id))
        try:
            if os.path.commonpath([base, full]) != base:
                return None
        except Exception:
            return None
        rd = Path(full)
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
        zp = _zip_results_dir(jid)
        if not zp:
            raise HTTPException(status_code=404, detail="No artifacts to zip")
        p = zp
    else:
        p = _select_download_path(jid, file)

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
    # Inline sanitize job_id and derive results dir
    if not isinstance(job_id, str) or not job_id:
        raise HTTPException(status_code=400, detail="Invalid job_id parameter")
    if os.path.isabs(job_id) or job_id != os.path.basename(job_id) or not SAFE_JOB_ID_RE.fullmatch(job_id):
        raise HTTPException(status_code=400, detail="Invalid job_id parameter")
    base = os.path.normpath(os.environ.get("DATAVIZHUB_RESULTS_DIR", "/tmp/datavizhub_results"))
    full = os.path.normpath(os.path.join(base, job_id))
    try:
        if os.path.commonpath([base, full]) != base:
            raise HTTPException(status_code=400, detail="Invalid job_id parameter")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid job_id parameter")
    rd = Path(full)
    mf = rd / "manifest.json"
    if not mf.exists():
        raise HTTPException(status_code=404, detail="Manifest not found")
    import json

    try:
        return json.loads(mf.read_text(encoding="utf-8"))
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to read manifest")
