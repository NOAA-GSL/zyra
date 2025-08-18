from __future__ import annotations

import re
import sys

TARGET_CRS = "EPSG:4326"  # PlateCarree (lon/lat)


def _parse_epsg(s: str | None) -> str | None:
    if not s:
        return None
    m = re.search(r"epsg\s*:?\s*(\d+)", s, re.IGNORECASE)
    if m:
        return f"EPSG:{m.group(1)}"
    if s.strip().upper().startswith("EPSG:"):
        return s.strip().upper()
    return None


def detect_crs_from_xarray(ds) -> str | None:
    # Try CF grid_mapping reference
    try:
        gm_name = ds.attrs.get("grid_mapping") or None
        if gm_name and gm_name in ds:
            gm = ds[gm_name].attrs
            for key in ("spatial_ref", "crs_wkt", "epsg_code", "proj4"):
                v = gm.get(key)
                epsg = _parse_epsg(str(v)) if v is not None else None
                if epsg:
                    return epsg
    except Exception:
        pass
    # Dataset-level hints
    for key in ("crs", "spatial_ref", "crs_wkt", "proj4"):
        v = ds.attrs.get(key)
        epsg = _parse_epsg(str(v)) if v is not None else None
        if epsg:
            return epsg
    # rioxarray crs if available
    try:
        crs = ds.rio.crs  # type: ignore[attr-defined]
        if crs:
            return _parse_epsg(str(crs)) or str(crs)
    except Exception:
        pass
    return None


def detect_crs_from_csv(df) -> str | None:
    cols = {c.lower() for c in df.columns}
    if {"lat", "lon"}.issubset(cols) or {"latitude", "longitude"}.issubset(cols):
        return TARGET_CRS
    return None


def detect_crs_from_path(path: str, *, var: str | None = None) -> str | None:
    if path.lower().endswith((".nc", ".nc4")):
        try:
            import xarray as xr

            ds = xr.open_dataset(path)
            try:
                return detect_crs_from_xarray(ds)
            finally:
                ds.close()
        except Exception:
            return None
    elif path.lower().endswith(".csv"):
        try:
            import pandas as pd

            return detect_crs_from_csv(pd.read_csv(path))
        except Exception:
            return None
    else:
        # .npy and others: assume lon/lat unless overridden
        return TARGET_CRS


def warn_if_mismatch(
    input_crs: str | None,
    *,
    target_crs: str = TARGET_CRS,
    reproject: bool = False,
    context: str = "",
) -> None:
    if not input_crs:
        print(f"Warning: Input CRS unknown; assuming {target_crs}.", file=sys.stderr)
        return
    if input_crs.upper() != target_crs.upper():
        print(
            f"Warning: Input CRS ({input_crs}) differs from display CRS ({target_crs}). "
            f"Reprojection {'requested but not applied' if reproject else 'not applied'}.",
            file=sys.stderr,
        )


def to_cartopy_crs(crs: str | None):
    """Return a Cartopy CRS object for an EPSG string, defaulting to PlateCarree.

    Returns None if Cartopy is unavailable.
    """
    try:
        import cartopy.crs as ccrs

        if not crs:
            return ccrs.PlateCarree()
        epsg = _parse_epsg(crs)
        if not epsg:
            return ccrs.PlateCarree()
        code = int(epsg.split(":", 1)[1])
        return ccrs.epsg(code)
    except Exception:
        return None
