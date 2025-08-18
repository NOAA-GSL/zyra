"""Jobs router: job status, cancellation, manifest, and artifact downloads.

This module exposes HTTP endpoints under the "jobs" tag. All endpoints are
protected by API key authentication when `DATAVIZHUB_API_KEY` is set.
"""
from __future__ import annotations

import mimetypes
import os
import re
from pathlib import Path

from datavizhub.api.models.cli_request import JobStatusResponse
from datavizhub.api.workers import jobs as jobs_backend
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

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
    if Path(job_id).is_absolute():
        raise HTTPException(status_code=400, detail="Invalid job_id parameter")
    if job_id != Path(job_id).name:
        # Ensures no separators and no traversal like "../x"
        raise HTTPException(status_code=400, detail="Invalid job_id parameter")
    # Allowlist characters (tighten further than basename check)
    if not SAFE_JOB_ID_RE.fullmatch(job_id):
        raise HTTPException(status_code=400, detail="Invalid job_id parameter")

    # Compute results dir using pathlib and verify containment
    base = Path(os.environ.get("DATAVIZHUB_RESULTS_DIR", "/tmp/datavizhub_results"))
    full = base / job_id
    try:
        _ = full.relative_to(base)
    except Exception as err:
        raise HTTPException(status_code=400, detail="Invalid job_id parameter") from err
    rd = full
    # Optionally refuse symlinked root directory
    try:
        if Path(base).is_symlink():
            raise HTTPException(
                status_code=500,
                detail="Results root directory misconfigured (symlink not allowed)",
            )
    except Exception:
        pass
    return rd


def _select_download_path(job_id: str, specific_file: str | None) -> Path:
    # Validate job_id early and derive results dir (inline containment check)
    if not isinstance(job_id, str) or not job_id:
        raise HTTPException(status_code=400, detail="Invalid job_id parameter")
    if (
        Path(job_id).is_absolute()
        or job_id != Path(job_id).name
        or not SAFE_JOB_ID_RE.fullmatch(job_id)
    ):
        raise HTTPException(status_code=400, detail="Invalid job_id parameter")
    base = Path(os.environ.get("DATAVIZHUB_RESULTS_DIR", "/tmp/datavizhub_results"))
    full = base / job_id
    try:
        _ = full.relative_to(base)
    except Exception as err:
        raise HTTPException(status_code=400, detail="Invalid job_id parameter") from err
    # rd = Path(full)  # not needed
    if specific_file:
        # Only allow a single safe filename (no directories)
        if (
            not _is_safe_segment(specific_file)
            or specific_file != Path(specific_file).name
        ):
            raise HTTPException(status_code=400, detail="Invalid file parameter")
        # Compose file path and verify containment again
        full_file = base / job_id / specific_file
        try:
            _ = full_file.relative_to(base)
        except Exception as err:
            raise HTTPException(
                status_code=400, detail="Invalid file parameter"
            ) from err
        # Reject symlink targets using O_NOFOLLOW when available and ensure existence
        try:
            import errno as _errno
            import os as _os

            flags = getattr(_os, "O_RDONLY", 0)
            nofollow = getattr(_os, "O_NOFOLLOW", 0)
            # lgtm [py/path-injection] — full_file is validated (single-segment, normpath+commonpath, O_NOFOLLOW)
            fd = _os.open(full_file, flags | nofollow)
            import contextlib

            with contextlib.suppress(Exception):
                _os.close(fd)
        except FileNotFoundError as e:
            raise HTTPException(
                status_code=404, detail="Requested file not found"
            ) from e
        except OSError as e:  # pragma: no cover - platform dependent
            # ELOOP indicates a symlink was encountered when O_NOFOLLOW is honored
            if getattr(e, "errno", None) == getattr(_errno, "ELOOP", 62):
                raise HTTPException(
                    status_code=400, detail="Invalid file parameter"
                ) from e
            # Fall back to conservative 404 for other OS errors
            raise HTTPException(
                status_code=404, detail="Requested file not found"
            ) from e
        return Path(full_file)
    # No specific file requested; let the caller decide (e.g., use job output_file)
    raise HTTPException(status_code=404, detail="No artifacts available")


@router.get(
    "/jobs/{job_id}", response_model=JobStatusResponse, summary="Get job status"
)
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
    file: str | None = Query(
        default=None,
        description="Specific filename from manifest.json",
    ),
    zip: int | None = Query(
        default=None, description="If 1, package all artifacts into a zip on demand"
    ),
):
    """Stream the selected job artifact (ZIP or individual file).

    Query parameters
    - file: Specific filename from the job manifest (guards path traversal)
    - zip: When 1, package current artifacts into a zip on demand
    """
    # Validate job_id early and use a distinct variable to avoid taint flow
    jid = job_id
    if (
        not isinstance(jid, str)
        or not jid
        or Path(jid).is_absolute()
        or jid != Path(jid).name
        or not SAFE_JOB_ID_RE.fullmatch(jid)
    ):
        raise HTTPException(status_code=400, detail="Invalid job_id parameter")

    rec = jobs_backend.get_job(jid)
    if not rec:
        raise HTTPException(status_code=404, detail="Job not found")

    def _zip_results_dir(job_id: str) -> Path | None:
        # Inline sanitize job_id and derive results dir
        if not isinstance(job_id, str) or not job_id:
            return None
        if (
            Path(job_id).is_absolute()
            or job_id != Path(job_id).name
            or not SAFE_JOB_ID_RE.fullmatch(job_id)
        ):
            return None
        base_dir = Path(
            os.environ.get("DATAVIZHUB_RESULTS_DIR", "/tmp/datavizhub_results")
        )
        full_dir = base_dir / job_id
        # Normalize and validate that full_dir is contained within base_dir
        full_dir_real = Path(os.path.realpath(str(full_dir)))
        base_dir_real = Path(os.path.realpath(str(base_dir)))
        if not str(full_dir_real).startswith(str(base_dir_real)):
            return None
        # Build manifest and zip paths
        try:
            import json
            import zipfile

            mf = full_dir_real / "manifest.json"
            items = []
            try:
                with mf.open(encoding="utf-8") as _fh:
                    data = json.load(_fh)
                items = data.get("artifacts") or []
            except Exception:
                items = []
            if not items:
                return None
            zpath = full_dir_real / f"{job_id}.zip"
            with zipfile.ZipFile(
                str(zpath), mode="w", compression=zipfile.ZIP_DEFLATED
            ) as zf:  # type: ignore[attr-defined]
                for it in items:
                    if not isinstance(it, dict):
                        continue
                    name = it.get("name") or Path(it.get("path", "")).name
                    if not isinstance(name, str) or not name:
                        continue
                    # Only single safe segments
                    if not _is_safe_segment(name):
                        continue
                    fp = full_dir_real / name
                    # Write using the safe name inside the archive
                    try:
                        zf.write(str(fp), name)
                    except Exception:
                        continue
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
        if file:
            p = _select_download_path(jid, file)
        else:
            # Prefer recorded output_file but re-anchor under results dir for containment
            p = None
            base_dir = Path(
                os.environ.get("DATAVIZHUB_RESULTS_DIR", "/tmp/datavizhub_results")
            )
            try:
                out = rec.get("output_file")
                if isinstance(out, str) and out:
                    name = Path(out).name
                    p_candidate = base_dir / jid / name
                    p = p_candidate
                if not p:
                    # Try manifest.json for first artifact and re-anchor by name
                    mf = base_dir / jid / "manifest.json"
                    try:
                        import json

                        # Normalize and check containment
                        mf_path = mf.resolve()
                        base_dir_resolved = base_dir.resolve()
                        def _is_subpath(path, base):
                            try:
                                return path.is_relative_to(base)
                            except AttributeError:
                                # For Python <3.9
                                return str(path).startswith(str(base) + os.sep)
                        if not _is_subpath(mf_path, base_dir_resolved):
                            raise HTTPException(status_code=400, detail="Invalid job_id: path traversal detected")
                        with mf_path.open(encoding="utf-8") as _fh:
                            data = json.load(_fh)
                    except FileNotFoundError:
                        try:
                            from datavizhub.api.workers.executor import (
                                write_manifest as _wm,
                            )

                            _wm(jid)
                            mf_path = mf.resolve()
                            base_dir_resolved = base_dir.resolve()
                            if not _is_subpath(mf_path, base_dir_resolved):
                                raise HTTPException(status_code=400, detail="Invalid job_id: path traversal detected")
                            with mf_path.open(encoding="utf-8") as _fh:
                                data = json.load(_fh)
                        except Exception:
                            data = {"artifacts": []}
                    arts = data.get("artifacts") or []
                    if arts and isinstance(arts[0], dict):
                        name = arts[0].get("name") or Path(arts[0].get("path", "")).name
                        if isinstance(name, str) and name:
                            p = base_dir / jid / name
            except Exception:
                p = None
            if not p:
                raise HTTPException(status_code=404, detail="No artifacts available")

    # Re-anchor the selected path under the contained base/jid using only its basename,
    # and obtain a file descriptor for TTL checks without path-based stat calls.
    try:
        base = Path(os.environ.get("DATAVIZHUB_RESULTS_DIR", "/tmp/datavizhub_results"))
        # Support when p is a Path or a string
        pname = p.name if hasattr(p, "name") else str(p)
        fname = Path(pname).name
        if not _is_safe_segment(fname):
            raise HTTPException(status_code=400, detail="Invalid file parameter")
        fullp = base / jid / fname
        # Normalize and check containment
        normalized_fullp = fullp.resolve()
        if not str(normalized_fullp).startswith(str(base.resolve())):
            raise HTTPException(status_code=400, detail="File path outside allowed directory")
        import errno as _errno
        import os as _os
        try:
            st = _os.fstat(fd)
        finally:
            import contextlib

            with contextlib.suppress(Exception):
                _os.close(fd)
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=410, detail="Output file no longer available"
        ) from e
    except OSError as e:  # pragma: no cover - platform dependent
        if getattr(e, "errno", None) == getattr(_errno, "ELOOP", 62):
            raise HTTPException(status_code=400, detail="Invalid file parameter") from e
        raise HTTPException(
            status_code=410, detail="Output file no longer available"
        ) from e
    except HTTPException:
        raise
    except Exception as err:
        raise HTTPException(status_code=400, detail="Invalid file parameter") from err

    # TTL policy: refuse downloads older than DATAVIZHUB_RESULTS_TTL_SECONDS (default 24h)
    try:
        ttl = int(os.environ.get("DATAVIZHUB_RESULTS_TTL_SECONDS", "86400") or 86400)
    except Exception:
        ttl = 86400
    try:
        import time

        age = time.time() - st.st_mtime
        if age > ttl:
            raise HTTPException(status_code=410, detail="Output file expired")
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=410, detail="Output file no longer available"
        ) from e

    # MIME type detection with python-magic if present
    media_type = None
    try:
        import magic  # type: ignore

        mt = magic.Magic(mime=True).from_file(str(p))
        media_type = str(mt) if mt else None
    except Exception:
        media_type, _ = mimetypes.guess_type(p.name)
    return FileResponse(
        normalized_fullp, media_type=media_type or "application/octet-stream", filename=fname
    )


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
    if (
        Path(job_id).is_absolute()
        or job_id != Path(job_id).name
        or not SAFE_JOB_ID_RE.fullmatch(job_id)
    ):
        raise HTTPException(status_code=400, detail="Invalid job_id parameter")
    base = Path(os.environ.get("DATAVIZHUB_RESULTS_DIR", "/tmp/datavizhub_results"))
    full = base / job_id
    try:
        _ = full.relative_to(base)
    except Exception as err:
        raise HTTPException(status_code=400, detail="Invalid job_id parameter") from err
    # Build manifest path and verify containment
    mf = full / "manifest.json"
    import errno as _errno
    import json
    import os as _os

    try:
        # lgtm [py/path-injection] — mf is contained via normpath+commonpath, O_NOFOLLOW used
        fd = _os.open(
            str(mf), getattr(_os, "O_RDONLY", 0) | getattr(_os, "O_NOFOLLOW", 0)
        )
        try:
            chunks: list[bytes] = []
            while True:
                b = _os.read(fd, 8192)
                if not b:
                    break
                chunks.append(b)
            data = b"".join(chunks).decode("utf-8", errors="strict")
        finally:
            import contextlib

            with contextlib.suppress(Exception):
                _os.close(fd)
        return json.loads(data)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail="Manifest not found") from e
    except OSError as e:  # pragma: no cover - platform dependent
        if getattr(e, "errno", None) == getattr(_errno, "ELOOP", 62):
            raise HTTPException(
                status_code=400, detail="Invalid job_id parameter"
            ) from e
        raise HTTPException(status_code=500, detail="Failed to read manifest") from e
    except Exception as err:
        raise HTTPException(status_code=500, detail="Failed to read manifest") from err
