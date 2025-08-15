from __future__ import annotations

import os
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile


router = APIRouter(tags=["files"])

UPLOAD_DIR = Path(os.environ.get("DATAVIZHUB_UPLOAD_DIR", "/tmp/datavizhub_uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)) -> dict:
    file_id = uuid.uuid4().hex
    dest = UPLOAD_DIR / f"{file_id}_{file.filename}"
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

