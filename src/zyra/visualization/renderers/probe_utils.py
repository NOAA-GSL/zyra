# SPDX-License-Identifier: Apache-2.0
"""Helpers for preparing structured probe datasets for interactive viewers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import xarray as xr

LAT_NAMES = {"lat", "latitude", "y", "ylat"}
LON_NAMES = {"lon", "longitude", "x", "xlon"}
MAX_PROBE_POINTS = 10_000


class ProbeDatasetError(Exception):
    """Raised when probe dataset conversion fails."""


def prepare_probe_dataset_file(
    source: Path,
    dest_dir: Path,
    *,
    variable: str | None = None,
    max_points: int = MAX_PROBE_POINTS,
) -> tuple[Path, dict[str, Any]]:
    """Convert structured datasets into JSON probe points written under ``dest_dir``.

    Parameters
    ----------
    source:
        Input file path (e.g., NetCDF).
    dest_dir:
        Target directory inside the bundle's assets.
    variable:
        Optional variable name to extract (required when dataset has multiple data vars).
    max_points:
        Maximum number of probe points to emit.

    Returns
    -------
    Path, dict
        Tuple of the generated JSON file path and metadata (e.g., units, variable name).

    Raises
    ------
    ProbeDatasetError
        When the dataset cannot be converted.
    """

    source = source.expanduser()
    suffix = source.suffix.lower()
    if suffix not in {".nc", ".nc4", ".cdf"}:
        raise ProbeDatasetError(f"Unsupported probe dataset format: {source}")

    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / f"{source.stem}_probe_points.json"

    points, metadata = _extract_points_from_netcdf(
        source, variable=variable, max_points=max_points
    )

    dest_path.write_text(json.dumps(points, indent=2), encoding="utf-8")
    return dest_path, metadata


def _extract_points_from_netcdf(
    source: Path,
    *,
    variable: str | None,
    max_points: int = MAX_PROBE_POINTS,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    ds = xr.open_dataset(source)
    try:
        data_var = variable or _select_default_variable(ds)
        arr = ds[data_var]
        arr = _collapse_extra_dims(arr)
        lat_dim, lon_dim = _detect_lat_lon_dims(arr)

        lat_vals = arr.coords[lat_dim].values
        lon_vals = arr.coords[lon_dim].values

        lat_idx = _sample_indices(lat_vals.size, max_points)
        lon_idx = _sample_indices(lon_vals.size, max_points)

        arr_sample = arr.isel({lat_dim: lat_idx, lon_dim: lon_idx})
        lat_sample = lat_vals[lat_idx]
        lon_sample = lon_vals[lon_idx]
        values = arr_sample.values

        units = arr.attrs.get("units")

        points: list[dict[str, Any]] = []
        for i, lat in enumerate(np.asarray(lat_sample).astype(float)):
            for j, lon in enumerate(np.asarray(lon_sample).astype(float)):
                value = values[i, j]
                if not np.isfinite(value):
                    continue
                point: dict[str, Any] = {
                    "lat": float(lat),
                    "lon": float(lon),
                    "value": float(value),
                }
                if units:
                    point["units"] = str(units)
                points.append(point)
        metadata = {"variable": data_var}
        if units:
            metadata["units"] = str(units)
    finally:
        ds.close()
    if not points:
        raise ProbeDatasetError("No finite probe points extracted from dataset.")
    return points, metadata


def _select_default_variable(ds: xr.Dataset) -> str:
    data_vars = list(ds.data_vars)
    if not data_vars:
        raise ProbeDatasetError("Dataset contains no data variables for probing.")
    if len(data_vars) == 1:
        return data_vars[0]
    raise ProbeDatasetError(
        "Dataset has multiple variables; specify --probe-var to select one."
    )


def _collapse_extra_dims(arr: xr.DataArray) -> xr.DataArray:
    collapsible_dims = [dim for dim in arr.dims if dim not in arr.coords]
    for dim in collapsible_dims:
        arr = arr.isel({dim: 0})
    while arr.ndim > 2:
        dim = arr.dims[0]
        if dim in LAT_NAMES or dim in LON_NAMES:
            break
        arr = arr.isel({dim: 0})
    return arr


def _detect_lat_lon_dims(arr: xr.DataArray) -> tuple[str, str]:
    lat_dim = None
    lon_dim = None
    for dim in arr.dims:
        name = dim.lower()
        if name in LAT_NAMES:
            lat_dim = dim
        elif name in LON_NAMES:
            lon_dim = dim
    if lat_dim and lon_dim:
        return lat_dim, lon_dim
    for coord_name in arr.coords:
        name = coord_name.lower()
        coord = arr.coords[coord_name]
        if coord.ndim != 1:
            continue
        if not lat_dim and name in LAT_NAMES:
            lat_dim = coord_name
        elif not lon_dim and name in LON_NAMES:
            lon_dim = coord_name
    if not lat_dim or not lon_dim:
        raise ProbeDatasetError(
            "Unable to identify latitude/longitude coordinates for probe dataset."
        )
    return lat_dim, lon_dim


def _sample_indices(size: int, max_points: int) -> np.ndarray:
    if size <= 0:
        return np.array([0])
    target = max(1, int(np.sqrt(max_points)))
    sample = min(size, target)
    return np.unique(np.linspace(0, size - 1, sample, dtype=int))
