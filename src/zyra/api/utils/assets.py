# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import contextlib
import mimetypes
import os
import stat
from pathlib import Path
from typing import Any

from zyra.api.models.types import AssetRef
from zyra.utils.env import env_bool, env_path

# Maximum number of files to include when listing a directory in assets.
# Keep small to avoid large payloads and accidental data disclosure.
MAX_DIRECTORY_FILES_IN_ASSETS = 5


def is_egress_stage(stage: str | None) -> bool:
    """Return True if the given stage name represents egress/dissemination.

    Centralizes alias handling so callers don't duplicate checks. Includes
    common aliases used across the codebase for backward compatibility.
    """
    if not stage:
        return False
    s = stage.strip().lower()
    return s in {"disseminate", "export", "decimate", "decimation"}


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


def guess_media_type(path: Path) -> str | None:
    """Public MIME type detection helper.

    Wrapper around the internal implementation to provide a stable API for
    other modules. Prefer this over importing the underscore-prefixed helper.
    """
    return _guess_media_type(path)


def _as_ref(p: Path) -> AssetRef:
    """Deprecated: prefer _asset_ref_for with containment guard."""
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

    # Precompute normalized base directories as strings for safe string-based checks
    # Feature flag: allow disabling probing entirely (size/magic) for assets
    PROBE = False
    try:
        PROBE = bool(env_bool("ASSET_PROBE", True))
    except Exception:
        PROBE = True

    try:
        _BASES = [
            os.path.normpath(str(env_path("UPLOAD_DIR", "/tmp/zyra_uploads"))),
            os.path.normpath(str(env_path("RESULTS_DIR", "/tmp/zyra_results"))),
            os.path.normpath(
                str(os.environ.get("DATAVIZHUB_RESULTS_DIR", "/tmp/datavizhub_results"))
            ),
        ]
    except Exception:
        _BASES = []

    def _contained_base(path_str: str) -> str | None:
        """Return the containing base dir if path_str is within an allowed base.

        Uses normalized absolute paths and commonpath; returns None when outside.
        """
        try:
            cand = os.path.normpath(path_str)
            if not Path(cand).is_absolute():
                return None
            for b in _BASES:
                try:
                    if os.path.commonpath([cand, b]) == b:
                        return b
                except Exception:
                    continue
            return None
        except Exception:
            return None

    # Single-file outputs
    for key in ("output", "to_video"):
        val = args.get(key)
        if isinstance(val, str):
            base = _contained_base(val)
            if base is not None and PROBE:
                # Re-anchor to the base using a normalized relative path
                rel = os.path.relpath(os.path.normpath(val), base)
                p = Path(base) / rel
                # Attempt safe probing; underlying helper handles missing files
                out.append(_asset_ref_for(p, True, base))
            else:
                # Include reference without probing existence for uncontained paths
                try:
                    mt, _ = mimetypes.guess_type(val)
                except Exception:
                    mt = None
                out.append(AssetRef(uri=val, name=Path(val).name, media_type=mt))
    # Egress local writes to positional 'path' (export/disseminate/decimate)
    if is_egress_stage(stage) and tool == "local":
        val = args.get("path")
        if isinstance(val, str):
            base = _contained_base(val)
            if base is not None and PROBE:
                rel = os.path.relpath(os.path.normpath(val), base)
                p = Path(base) / rel
                out.append(_asset_ref_for(p, True, base))
            else:
                try:
                    mt, _ = mimetypes.guess_type(val)
                except Exception:
                    mt = None
                out.append(AssetRef(uri=val, name=Path(val).name, media_type=mt))
    # Output directory (batch/frame outputs)
    od = args.get("output_dir")
    if isinstance(od, str):
        base = _contained_base(od)
        d = None
        if base is not None and PROBE:
            rel = os.path.relpath(os.path.normpath(od), base)
            d = Path(base) / rel
        # If it has a small number of files, list a few for convenience
        if d is not None:
            try:
                files = [p for p in d.iterdir() if p.is_file()]
                if files:
                    out.append(AssetRef(uri=str(d), name=d.name))
                    for p in files[:MAX_DIRECTORY_FILES_IN_ASSETS]:
                        out.append(_asset_ref_for(p, True, base))
                else:
                    out.append(AssetRef(uri=str(d), name=d.name))
            except Exception:
                # Directory missing or unreadable; include reference only
                out.append(AssetRef(uri=str(d), name=d.name))
        else:
            # Uncontained directory: include only reference
            out.append(AssetRef(uri=od, name=Path(od).name))
    return out


def _asset_ref_for(p: Path, allow_probe: bool, base: str | None = None) -> AssetRef:
    if allow_probe:
        # Safe stat using descriptor with O_NOFOLLOW to avoid symlink targets
        size = None
        try:
            # Optional: verify the final path remains contained under the expected base
            if base is not None:
                with contextlib.suppress(Exception):
                    if os.path.commonpath([str(p), base]) != base:
                        # Fallback to reference without probing if containment is violated
                        mt = _guess_media_type(p)
                        return AssetRef(uri=str(p), name=p.name, media_type=mt)
                    # Reject probing if any parent directory is a symlink
                    rel = os.path.relpath(str(p), base)
                    cur = Path(base)
                    for part in Path(rel).parts[:-1]:  # exclude final filename
                        cur = cur / part
                        st = os.lstat(str(cur))
                        if stat.S_ISLNK(st.st_mode):
                            mt = _guess_media_type(p)
                            return AssetRef(uri=str(p), name=p.name, media_type=mt)
                    # Re-validate containment with a resolved path (guards symlink escapes)
                    resolved = Path(str(p)).resolve(strict=False)
                    if os.path.commonpath([str(resolved), base]) != base:
                        mt = _guess_media_type(p)
                        return AssetRef(uri=str(p), name=p.name, media_type=mt)
            flags = getattr(os, "O_RDONLY", 0) | getattr(os, "O_NOFOLLOW", 0)
            # lgtm [py/path-injection] — path `p` is re-anchored under an allowlisted base and
            # validated via commonpath; O_NOFOLLOW prevents symlink traversal.
            fd = os.open(str(p), flags)
            try:
                st = os.fstat(fd)
                size = st.st_size
            finally:
                from contextlib import suppress as _s

                with _s(Exception):
                    os.close(fd)
        except Exception:
            size = None
            media_type = _guess_media_type(p)
            return AssetRef(uri=str(p), name=p.name, size=size, media_type=media_type)
        # Successful probe; include size and best-effort media type
        media_type = _guess_media_type(p)
        return AssetRef(uri=str(p), name=p.name, size=size, media_type=media_type)
    # No probing requested; return reference with best-effort media type only
    media_type = _guess_media_type(p)
    return AssetRef(uri=str(p), name=p.name, media_type=media_type)
