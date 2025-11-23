# SPDX-License-Identifier: Apache-2.0
"""Raster transform helpers (e.g., GeoTIFF → Cloud Optimized GeoTIFF)."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import rasterio
from rasterio.crs import CRS
from rasterio.enums import Resampling
from rasterio.errors import RasterioIOError
from rasterio.warp import calculate_default_transform, reproject

DEFAULT_BLOCKSIZE = 512
DEFAULT_COMPRESSION = "DEFLATE"


def _auto_overview_levels(width: int, height: int) -> tuple[int, ...]:
    levels: list[int] = []
    max_dim = max(width, height)
    factor = 2
    while max_dim / factor > 256 and factor <= 512:
        levels.append(factor)
        factor *= 2
    return tuple(levels)


def _detect_predictor(dtypes: Iterable[str]) -> int | None:
    """Return a suitable predictor value for the dataset."""

    try:
        import numpy
    except (
        ModuleNotFoundError
    ):  # pragma: no cover - numpy is a required dep via rasterio
        return None

    predictor: int | None = None
    for dtype in dtypes:
        if numpy.issubdtype(numpy.dtype(dtype), numpy.floating):
            predictor = 3
            break
        if numpy.issubdtype(numpy.dtype(dtype), numpy.integer):
            predictor = 2
    return predictor


def convert_geotiff_to_cog(
    input_path: str | Path,
    output_path: str | Path,
    *,
    dst_crs: CRS | None = None,
    resampling: Resampling = Resampling.bilinear,
    overview_levels: Iterable[int] | None = None,
    overview_resampling: Resampling | None = None,
    blocksize: int = DEFAULT_BLOCKSIZE,
    compression: str = DEFAULT_COMPRESSION,
    predictor: int | None = None,
    bigtiff: str | None = "IF_SAFER",
    num_threads: str | None = None,
    overwrite: bool = False,
) -> Path:
    """Convert a GeoTIFF into a Cloud Optimized GeoTIFF.

    Parameters mirror the CLI, covering reprojection, tiling, and overview
    generation. The function raises ``FileExistsError`` if the output already
    exists and ``overwrite`` is ``False``.
    """

    src_path = Path(input_path)
    if not src_path.exists():
        raise FileNotFoundError(f"GeoTIFF not found: {src_path}")

    dst_path = Path(output_path)
    if dst_path.exists() and not overwrite:
        raise FileExistsError(f"Output already exists: {dst_path}")

    dst_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        src = rasterio.open(src_path)
    except RasterioIOError as exc:  # pragma: no cover - surface upstream error
        raise RasterioIOError(str(exc)) from exc

    with src:
        src_crs = src.crs
        if dst_crs is None:
            if src_crs is None:
                raise ValueError(
                    "Source dataset has no CRS; specify --dst-crs to define the target reference system"
                )
            dst_crs_obj = src_crs
        else:
            dst_crs_obj = CRS.from_user_input(dst_crs)

        if src_crs is None and dst_crs_obj is not None and dst_crs_obj != src_crs:
            # We cannot reproject without a source CRS; treat as metadata assignment only.
            need_reproject = False
        else:
            need_reproject = src_crs is not None and src_crs != dst_crs_obj

        if need_reproject:
            transform, width, height = calculate_default_transform(
                src_crs,
                dst_crs_obj,
                src.width,
                src.height,
                *src.bounds,
            )
        else:
            transform = src.transform
            width = src.width
            height = src.height

        profile = src.profile.copy()
        profile.update(
            driver="GTiff",
            height=height,
            width=width,
            transform=transform,
            crs=dst_crs_obj,
            tiled=True,
            blockxsize=blocksize,
            blockysize=blocksize,
            compress=compression,
            bigtiff=bigtiff,
        )
        if num_threads:
            profile["NUM_THREADS"] = num_threads
        else:
            profile.pop("NUM_THREADS", None)

        if predictor is None:
            predictor = _detect_predictor(src.dtypes)
        if predictor:
            profile["predictor"] = predictor

        if overview_levels:
            levels = tuple(
                sorted(int(level) for level in overview_levels if int(level) > 1)
            )
        else:
            levels = _auto_overview_levels(width, height)

        overview_resampling = overview_resampling or resampling

        with rasterio.open(dst_path, "w", **profile) as dst:
            for idx in range(1, src.count + 1):
                if need_reproject:
                    reproject(
                        source=rasterio.band(src, idx),
                        destination=rasterio.band(dst, idx),
                        src_transform=src.transform,
                        src_crs=src_crs,
                        dst_transform=transform,
                        dst_crs=dst_crs_obj,
                        resampling=resampling,
                        src_nodata=src.nodata,
                        dst_nodata=profile.get("nodata"),
                    )
                else:
                    data = src.read(idx)
                    dst.write(data, idx)

            if levels:
                dst.build_overviews(levels, overview_resampling)
                dst.update_tags(ns="rio_overview", resampling=overview_resampling.name)

        # Ensure overviews were flushed; reopen in read mode to validate
        with rasterio.open(dst_path) as check_ds:
            if levels and not check_ds.overviews(1):
                raise RuntimeError("Overview generation failed for COG output")

    return dst_path


__all__ = ["convert_geotiff_to_cog"]
