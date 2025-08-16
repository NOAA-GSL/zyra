from __future__ import annotations

import os
import uuid
from pathlib import Path
import re

from fastapi import APIRouter, File, HTTPException, UploadFile


router = APIRouter(tags=["files"])

UPLOAD_DIR = Path(os.environ.get("DATAVIZHUB_UPLOAD_DIR", "/tmp/datavizhub_uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


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
async def upload_file(file: UploadFile = File(...)) -> dict:
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
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid upload path")
    try:
        with dest.open("wb") as f:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"Upload failed: {exc}")
    return {"file_id": file_id, "path": str(dest)}
