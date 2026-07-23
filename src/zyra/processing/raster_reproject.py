# SPDX-License-Identifier: Apache-2.0
"""Warp pre-rendered rasters between coordinate reference systems.

Zyra's Process stage already reprojects *native scientific data*
(GRIB2/NetCDF); this module covers the other case: an
**already-rendered raster** in another projection — a
polar-stereographic sea-ice PNG, a geostationary full-disk JPG, a
Mercator web map produced offline. Sphere-rendering consumers
(Science On a Sphere, TerraViz) need such imagery as equirectangular
EPSG:4326, and without this every downstream consumer reinvents a
``gdalwarp`` step.

Requires the optional ``rasterio`` dependency (``zyra[processing]``);
imports are deferred so the module can be imported without it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

DEFAULT_TARGET_CRS = "EPSG:4326"
DEFAULT_WIDTH = 4096
DEFAULT_HEIGHT = 2048
#: Full-globe extent (west, south, east, north) for the default target CRS.
FULL_GLOBE_BOUNDS = (-180.0, -90.0, 180.0, 90.0)

RESAMPLING_CHOICES = ("bilinear", "nearest")


class ReprojectError(ValueError):
    """Raised when reprojection inputs are invalid or insufficient."""


@dataclass
class ReprojectResult:
    """Summary of a completed reprojection."""

    output: str
    width: int
    height: int
    crs: str
    band_count: int


def _require_rasterio() -> Any:
    try:
        import rasterio  # noqa: F401

        return rasterio
    except ImportError as err:  # pragma: no cover - exercised via CLI test
        raise ReprojectError(
            "rasterio is required for reproject; install with: pip install 'zyra[processing]'"
        ) from err


def _driver_for_path(path: str) -> str:
    suffix = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    return {
        "png": "PNG",
        "jpg": "JPEG",
        "jpeg": "JPEG",
        "tif": "GTiff",
        "tiff": "GTiff",
    }.get(suffix, "GTiff")


def reproject_raster(
    input_path: str,
    output_path: str,
    *,
    s_srs: str | None = None,
    t_srs: str = DEFAULT_TARGET_CRS,
    bounds: tuple[float, float, float, float] | None = None,
    dst_bounds: tuple[float, float, float, float] | None = None,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    resampling: str = "bilinear",
) -> ReprojectResult:
    """Warp a raster to a target CRS grid.

    Parameters
    ----------
    input_path : str
        Source raster path. Georeferenced formats (GeoTIFF) carry their
        own CRS/transform; plain images (PNG/JPG) require ``s_srs`` and
        ``bounds``.
    output_path : str
        Destination path; the driver is inferred from the extension
        (PNG/JPEG/GeoTIFF, defaulting to GeoTIFF).
    s_srs : str, optional
        Source CRS (e.g. ``EPSG:3413``). Overrides any embedded CRS;
        required when the source has none.
    t_srs : str, optional
        Target CRS; defaults to EPSG:4326.
    bounds : tuple of float, optional
        Source georeference as ``(west, south, east, north)`` in
        source-CRS units, for rasters without an embedded transform.
    dst_bounds : tuple of float, optional
        Target extent in target-CRS units. Defaults to the full globe
        when the target is EPSG:4326, otherwise it is required.
    width, height : int
        Output grid size; defaults to 4096x2048 (the 2:1 full-globe
        sphere spec).
    resampling : str
        ``bilinear`` (continuous imagery, default) or ``nearest``
        (categorical/palette imagery).

    Returns
    -------
    ReprojectResult
        Output path and grid metadata.
    """
    rasterio = _require_rasterio()
    import numpy as np
    from rasterio.crs import CRS
    from rasterio.enums import Resampling
    from rasterio.transform import from_bounds
    from rasterio.warp import reproject as rio_reproject

    if resampling not in RESAMPLING_CHOICES:
        raise ReprojectError(
            f"resampling must be one of {', '.join(RESAMPLING_CHOICES)}; got: {resampling}"
        )
    if width <= 0 or height <= 0:
        raise ReprojectError(f"width/height must be positive; got: {width}x{height}")

    resampling_enum = (
        Resampling.bilinear if resampling == "bilinear" else Resampling.nearest
    )
    dst_crs = CRS.from_user_input(t_srs)

    if dst_bounds is None:
        if dst_crs == CRS.from_epsg(4326):
            dst_bounds = FULL_GLOBE_BOUNDS
        else:
            raise ReprojectError(
                "--dst-bounds is required when the target CRS is not EPSG:4326"
            )
    dst_transform = from_bounds(*dst_bounds, width, height)

    with rasterio.open(input_path) as src:
        src_crs = CRS.from_user_input(s_srs) if s_srs else src.crs
        if src_crs is None:
            raise ReprojectError(
                "source raster has no embedded CRS; pass --s-srs (and --bounds for plain images)"
            )
        # A plain image (PNG/JPG) reports an identity transform; that is
        # only usable when the caller supplies the real extent.
        src_transform = src.transform
        if bounds is not None:
            src_transform = from_bounds(*bounds, src.width, src.height)
        elif s_srs and (src_transform is None or src_transform.is_identity):
            raise ReprojectError(
                "--s-srs was given but the source has no geotransform; pass --bounds west south east north"
            )

        band_count = src.count
        # Read one band at a time instead of src.read() up front: the
        # full-source array would double peak memory for large rasters.
        # (Array sources rather than rasterio.band() so the explicit
        # src_transform override works for plain images without a
        # geotransform.)
        dst_data = np.zeros((band_count, height, width), dtype=src.dtypes[0])
        for band in range(band_count):
            rio_reproject(
                source=src.read(band + 1),
                destination=dst_data[band],
                src_transform=src_transform,
                src_crs=src_crs,
                dst_transform=dst_transform,
                dst_crs=dst_crs,
                resampling=resampling_enum,
            )

    driver = _driver_for_path(output_path)
    profile = {
        "driver": "GTiff",
        "width": width,
        "height": height,
        "count": band_count,
        "dtype": dst_data.dtype.name,
        "crs": dst_crs,
        "transform": dst_transform,
    }
    if driver == "GTiff":
        with rasterio.open(output_path, "w", **profile) as dst:
            dst.write(dst_data)
    else:
        # PNG/JPEG are CreateCopy-only GDAL drivers: build an in-memory
        # GeoTIFF first, then copy into the target format.
        import rasterio.shutil as rio_shutil
        from rasterio.io import MemoryFile

        with MemoryFile() as mem:
            with mem.open(**profile) as tmp:
                tmp.write(dst_data)
            with mem.open() as tmp:
                rio_shutil.copy(tmp, output_path, driver=driver)

    return ReprojectResult(
        output=output_path,
        width=width,
        height=height,
        crs=dst_crs.to_string(),
        band_count=band_count,
    )
