from __future__ import annotations

import contextlib
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from zyra.utils.env import env_path

router = APIRouter(tags=["files"])


def _resolve_upload_dir() -> Path:
    """Pick an uploads directory that is writable.

    Respects `ZYRA_UPLOAD_DIR`/`DATAVIZHUB_UPLOAD_DIR` via env, but falls back to
    `/tmp/zyra_uploads` when the configured path cannot be created (e.g., missing
    permissions in CI). Ensures the directory exists before returning.
    """
    base = env_path("UPLOAD_DIR", "/tmp/zyra_uploads")
    try:
        base.mkdir(parents=True, exist_ok=True)
        # Verify writability by creating a tiny probe file
        probe = base / ".probe"
        with probe.open("wb") as f:
            f.write(b"ok")
        with contextlib.suppress(Exception):
            probe.unlink()
        return base
    except Exception:
        # Not writable or cannot be created; fall back below
        pass
    # Fallback when configured dir is not writable or cannot be created
    fallback = Path("/tmp/zyra_uploads")
    try:
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback
    except Exception:
        # last resort: keep the original and let downstream raise as needed
        return base


UPLOAD_DIR = _resolve_upload_dir()

# Avoid B008: evaluate File() at module import and reuse as default
_FILE_REQUIRED = File(...)


def _sanitize_filename(name: str) -> str:
    # Drop any path components and normalize to a safe subset
    base = Path(name).name
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base)
    base = base.strip("._-")
    if not base:
        base = "upload.bin"
    # Preserve single suffix and cap length
    p = Path(base)
    stem = p.stem[:80] if len(p.stem) > 80 else p.stem
    suffix = p.suffix if len(p.suffix) <= 16 else p.suffix[:16]
    return (stem or "file") + suffix


@router.post("/upload")
async def upload_file(file: UploadFile = _FILE_REQUIRED) -> dict:
    file_id = uuid.uuid4().hex
    safe_name = _sanitize_filename(file.filename or "")
    # Compose destination under uploads dir and ensure it resolves within
    base = UPLOAD_DIR.resolve()
    dest = base / f"{file_id}_{safe_name}"
    try:
        rp = dest.resolve()
        # Guard against unexpected symlink tricks on the base directory
        if rp.parent != base:
            raise HTTPException(status_code=400, detail="Invalid upload path")
    except HTTPException:
        raise
    except Exception as err:
        raise HTTPException(status_code=400, detail="Invalid upload path") from err
    try:
        with dest.open("wb") as f:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"Upload failed: {exc}") from exc
    return {"file_id": file_id, "path": str(dest)}
