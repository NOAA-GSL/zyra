from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any

from zyra.api.models.types import AssetRef


def _guess_media_type(path: Path) -> str | None:
    """Best-effort media type detection.

    Order of precedence: python-magic (if available) → well-known extensions → mimetypes → None.
    """
    # 1) Try python-magic if available (best accuracy)
    try:
        import magic  # type: ignore

        m = magic.Magic(mime=True)
        mt = str(m.from_file(str(path)))
        if mt:
            return mt
    except Exception:
        pass

    # 2) Extension-based hints (lowercased)
    ext = path.suffix.lower()
    ext_map = {
        ".nc": "application/x-netcdf",
        ".grib2": "application/grib2",
        ".grb2": "application/grib2",
        ".grb": "application/grib",
        ".tif": "image/tiff",
        ".tiff": "image/tiff",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".mp4": "video/mp4",
        ".zip": "application/zip",
        ".json": "application/json",
    }
    if ext in ext_map:
        return ext_map[ext]

    # 3) Fallback to mimetypes
    try:
        mt, _ = mimetypes.guess_type(str(path))
        return mt
    except Exception:
        return None


def _as_ref(p: Path) -> AssetRef:
    try:
        size = p.stat().st_size if p.exists() and p.is_file() else None
    except Exception:
        size = None
    media_type: str | None = _guess_media_type(p)
    return AssetRef(uri=str(p), name=p.name, size=size, media_type=media_type)


def infer_assets(stage: str, tool: str, args: dict[str, Any]) -> list[AssetRef]:
    """Best-effort asset harvesting based on common arg conventions.

    - Picks up file paths from keys like 'output', 'path', 'to_video'.
    - When 'output_dir' is provided, includes the directory if it exists.
    - Only returns paths that exist at call time; otherwise returns an empty list.
    """
    out: list[AssetRef] = []
    # Single-file outputs
    for key in ("output", "to_video"):
        val = args.get(key)
        if isinstance(val, str):
            p = Path(val)
            if p.exists():
                out.append(_as_ref(p))
    # Decimate local writes to positional 'path'
    if stage == "decimate" and tool == "local":
        val = args.get("path")
        if isinstance(val, str):
            p = Path(val)
            if p.exists():
                out.append(_as_ref(p))
    # Output directory (batch/frame outputs)
    od = args.get("output_dir")
    if isinstance(od, str):
        d = Path(od)
        if d.exists():
            # If it has a small number of files, list a few for convenience
            try:
                files = [p for p in d.iterdir() if p.is_file()]
                if files:
                    # Include directory as a container + first few files
                    out.append(AssetRef(uri=str(d), name=d.name))
                    for p in files[:5]:
                        out.append(_as_ref(p))
                else:
                    out.append(AssetRef(uri=str(d), name=d.name))
            except Exception:
                out.append(AssetRef(uri=str(d), name=d.name))
    return out
