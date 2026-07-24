# SPDX-License-Identifier: Apache-2.0
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Any


class VariableNotFoundError(KeyError):
    """Raised when a requested GRIB variable cannot be found."""


@dataclass
class DecodedGRIB:
    """Container for decoded GRIB2 content.

    Attributes
    ----------
    backend : str
        The backend used to decode the data: "cfgrib", "pygrib" or "wgrib2".
    dataset : Any, optional
        An xarray.Dataset when using the cfgrib backend, if available.
    messages : list, optional
        A list of pygrib messages when using the pygrib backend.
    path : str, optional
        Path to a temporary GRIB2 file on disk. Some backends keep file access.
    meta : dict, optional
        Optional metadata extracted by a CLI tool such as wgrib2.
    """

    backend: str
    dataset: Any | None = None
    messages: list[Any] | None = None
    path: str | None = None
    meta: dict[str, Any] | None = None


def _write_temp_file(data: bytes, suffix: str = ".grib2") -> str:
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    return path


def _has_wgrib2() -> bool:
    return shutil.which("wgrib2") is not None


def grib_decode(data: bytes, backend: str = "cfgrib") -> DecodedGRIB:
    """Decode GRIB2 bytes into Python structures.

    Prefers xarray+cfgrib when available, with fallbacks to pygrib and the
    wgrib2 CLI for difficult edge-cases.

    Parameters
    ----------
    data : bytes
        Raw GRIB2 file content (possibly subsetted by byte ranges).
    backend : str, default "cfgrib"
        One of: "cfgrib", "pygrib", or "wgrib2".

    Returns
    -------
    DecodedGRIB
        A container describing what was decoded and how to access it.

    Raises
    ------
    ValueError
        If an unsupported backend is requested.
    RuntimeError
        If decoding fails for the chosen backend.
    """
    backend = (backend or "cfgrib").lower()
    temp_path = _write_temp_file(data, suffix=".grib2")

    try:
        if backend == "cfgrib":
            try:
                import xarray as xr  # type: ignore

                # indexpath="" disables cfgrib's index sidecar: the input
                # is a one-shot temp file, and the previous ":auto:" value
                # was not cfgrib magic — it became a literal pickle file
                # named ':auto:' in the caller's working directory.
                ds = xr.open_dataset(
                    temp_path,
                    engine="cfgrib",
                    backend_kwargs={"indexpath": ""},
                )
                return DecodedGRIB(backend="cfgrib", dataset=ds, path=temp_path)
            except ModuleNotFoundError as exc:  # pragma: no cover - optional dep
                # User explicitly requested cfgrib but xarray/cfgrib are missing
                raise RuntimeError(
                    "cfgrib backend requested but xarray/cfgrib are not available. "
                    "Install the focused GRIB2 extras (e.g., 'pip install zyra[grib2]' or 'poetry install -E grib2'), "
                    "or choose a different backend (pygrib or wgrib2)."
                ) from exc
            except Exception as exc:  # pragma: no cover - backend optional
                # If cfgrib fails for other reasons, proceed to try pygrib and then wgrib2 in sequence
                if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                    raise
                pass

        if backend in ("pygrib", "cfgrib"):
            try:
                import pygrib  # type: ignore

                grbs = pygrib.open(temp_path)
                messages = list(grbs)
                grbs.close()
                return DecodedGRIB(backend="pygrib", messages=messages, path=temp_path)
            except (
                ImportError,
                OSError,
                pygrib.GribError,
            ) as exc:  # pragma: no cover - backend optional
                if backend == "pygrib":
                    raise RuntimeError(f"pygrib decoding failed: {exc}") from exc
                # else fall through to wgrib2

        if backend == "wgrib2" or _has_wgrib2():
            try:
                # JSON output provides a machine-friendly structure
                # Note: not all wgrib2 builds include -json. Fallback to -V if needed.
                result = subprocess.run(
                    ["wgrib2", temp_path, "-json", "-"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if result.returncode != 0:
                    raise RuntimeError(result.stderr.strip() or "wgrib2 failed")
                meta = json.loads(result.stdout)
                return DecodedGRIB(backend="wgrib2", meta=meta, path=temp_path)
            except Exception as exc:  # pragma: no cover - external tool
                raise RuntimeError(f"wgrib2 decoding failed: {exc}") from exc

        raise RuntimeError(
            "Failed to decode GRIB2: cfgrib and pygrib unavailable; wgrib2 not found."
        )
    except Exception:
        # Keep temp on disk for inspection by caller; they can delete when done.
        raise


def _list_variables(decoded: DecodedGRIB) -> list[str]:
    if decoded.backend == "cfgrib" and decoded.dataset is not None:
        return list(decoded.dataset.data_vars)
    if decoded.backend == "pygrib" and decoded.messages is not None:
        names: list[str] = []
        for m in decoded.messages:
            try:
                names.append(getattr(m, "shortName", None) or getattr(m, "name", ""))
            except Exception:
                continue
        return [n for n in names if n]
    if decoded.backend == "wgrib2" and decoded.meta is not None:
        # meta structure depends on build; try to extract names heuristically
        vars_found: list[str] = []
        try:
            for entry in decoded.meta:
                v = entry.get("shortName") or entry.get("name")
                if v:
                    vars_found.append(v)
        except Exception:
            pass
        return vars_found
    return []


def extract_variable(decoded: DecodedGRIB, var_name: str) -> Any:
    """Extract a single variable by exact name or regex.

    Parameters
    ----------
    decoded : DecodedGRIB
        The decoded GRIB content returned by ``grib_decode``.
    var_name : str
        Either an exact name or a Python regex pattern. For the cfgrib backend,
        matches ``dataset.data_vars``. For pygrib, matches ``shortName`` or
        full ``name``.

    Returns
    -------
    Any
        Backend-specific object: an xarray.DataArray (cfgrib) or a list of
        pygrib messages matching the pattern.

    Raises
    ------
    VariableNotFoundError
        If no variable matches the selection.
    """
    # Regex or exact match
    pattern = re.compile(var_name)

    if decoded.backend == "cfgrib" and decoded.dataset is not None:
        matches = [v for v in decoded.dataset.data_vars if pattern.search(v)]
        if not matches:
            raise VariableNotFoundError(f"Variable not found: {var_name}")
        # Return the first match for simplicity; callers can refine if needed
        return decoded.dataset[matches[0]]

    if decoded.backend == "pygrib" and decoded.messages is not None:
        out = []
        for m in decoded.messages:
            sname = getattr(m, "shortName", "")
            fname = getattr(m, "name", "")
            if pattern.search(sname) or pattern.search(fname):
                out.append(m)
        if not out:
            raise VariableNotFoundError(f"Variable not found: {var_name}")
        return out

    if decoded.backend == "wgrib2" and decoded.meta is not None:
        out = []
        for entry in decoded.meta:
            sname = entry.get("shortName", "")
            fname = entry.get("name", "")
            if pattern.search(sname) or pattern.search(fname):
                out.append(entry)
        if not out:
            raise VariableNotFoundError(f"Variable not found: {var_name}")
        return out

    raise RuntimeError("Unsupported decoded structure for variable extraction.")


def _grib_georeference(da: Any) -> tuple[Any, Any, bool] | None:
    """Derive ``(crs, transform, flip_rows)`` from cfgrib ``GRIB_*`` attrs.

    Supports ``regular_ll`` and ``lambert`` grids (the NOAA projected
    products — HRRR, NAM, RRFS — are Lambert). Returns ``None`` for
    unrecognized grid types or incomplete metadata; callers keep their
    previous (ungeoreferenced) behavior in that case.

    ``flip_rows`` is True when the GRIB scans south-first
    (``jScansPositively=1``) and rows must be flipped to GeoTIFF's
    north-up convention.

    Notes
    -----
    cfgrib does not expose the earth radius; the GRIB2 sphere default
    of 6371229 m (shapeOfTheEarth=6) is assumed for projected grids,
    which matches NOAA's operational products.
    """
    attrs = getattr(da, "attrs", {}) or {}
    grid_type = attrs.get("GRIB_gridType")
    try:
        from rasterio.crs import CRS
        from rasterio.transform import from_origin
    except ImportError:
        return None
    try:
        ny = int(attrs["GRIB_Ny"])
        flip = bool(attrs.get("GRIB_jScansPositively", 0))
        lat_first = float(attrs["GRIB_latitudeOfFirstGridPointInDegrees"])
        lon_first = float(attrs["GRIB_longitudeOfFirstGridPointInDegrees"])
    except (KeyError, TypeError, ValueError):
        return None
    if lon_first > 180.0:
        lon_first -= 360.0

    if grid_type == "regular_ll":
        try:
            dlon = float(attrs["GRIB_iDirectionIncrementInDegrees"])
            dlat = float(attrs["GRIB_jDirectionIncrementInDegrees"])
        except (KeyError, TypeError, ValueError):
            return None
        north = (lat_first + (ny - 1) * dlat) if flip else lat_first
        transform = from_origin(lon_first - dlon / 2, north + dlat / 2, dlon, dlat)
        return CRS.from_epsg(4326), transform, flip

    if grid_type == "lambert":
        try:
            import pyproj

            dx = float(attrs["GRIB_DxInMetres"])
            dy = float(attrs["GRIB_DyInMetres"])
            crs = CRS.from_dict(
                {
                    "proj": "lcc",
                    "lat_1": float(attrs["GRIB_Latin1InDegrees"]),
                    "lat_2": float(attrs["GRIB_Latin2InDegrees"]),
                    "lat_0": float(attrs["GRIB_LaDInDegrees"]),
                    "lon_0": float(attrs["GRIB_LoVInDegrees"]),
                    "R": 6371229.0,
                }
            )
            tr = pyproj.Transformer.from_crs("EPSG:4326", crs, always_xy=True)
            x_first, y_first = tr.transform(lon_first, lat_first)
            # (x_first, y_first) is the center of the first grid point.
            west = x_first - dx / 2
            top_center = y_first + (ny - 1) * dy if flip else y_first
            transform = from_origin(west, top_center + dy / 2, dx, dy)
            return crs, transform, flip
        except Exception:
            return None
    return None


def _netcdf_bytes(data_to_write: Any) -> bytes:
    """Serialize an xarray object to NetCDF bytes.

    Tries the in-memory writer first, normalizing the return types seen
    in the wild (bytes, memoryview, file-like, numpy); falls back to a
    temp file (netCDF4/h5netcdf engines write files, not buffers).
    Raises on failure — callers decide on recovery.
    """
    try:
        maybe_bytes = data_to_write.to_netcdf()
        if isinstance(maybe_bytes, (bytes, bytearray)):
            return bytes(maybe_bytes)
        if isinstance(maybe_bytes, memoryview):
            return maybe_bytes.tobytes()
        read = getattr(maybe_bytes, "read", None)
        if callable(read):
            return read()
        tobytes = getattr(maybe_bytes, "tobytes", None)
        if callable(tobytes):
            return tobytes()
        raise TypeError(f"Unexpected return type from to_netcdf(): {type(maybe_bytes)}")
    except Exception:
        tmp = tempfile.NamedTemporaryFile(suffix=".nc", delete=False)
        tmp_path = tmp.name
        tmp.close()
        try:
            data_to_write.to_netcdf(tmp_path)
            from pathlib import Path as _P

            return _P(tmp_path).read_bytes()
        finally:
            import contextlib
            from pathlib import Path as _P

            with contextlib.suppress(Exception):
                _P(tmp_path).unlink()


def convert_to_format(
    decoded: DecodedGRIB,
    format_type: str,
    var: str | None = None,
) -> Any:
    """Convert decoded GRIB to a requested format.

    Supported formats:
    - "dataframe": Pandas DataFrame (requires xarray backend)
    - "xarray": xarray.Dataset or DataArray
    - "netcdf": NetCDF bytes (xarray+netcdf4 or wgrib2 fallback)
    - "geotiff": Bytes of a GeoTIFF (requires rioxarray or rasterio). Only a
      single variable is supported; specify ``var`` if the dataset has multiple
      variables.

    Parameters
    ----------
    decoded : DecodedGRIB
        Object returned by ``grib_decode``.
    format_type : str
        Target format: one of {"dataframe", "xarray", "netcdf", "geotiff"}.
    var : str, optional
        When multiple variables are present, choose one by exact or regex
        pattern. If omitted for xarray backend, returns the dataset as-is.

    Returns
    -------
    Any
        Converted object or bytes depending on ``format_type``.

    Raises
    ------
    ValueError
        If an unsupported format is requested or required dependencies are
        missing.
    RuntimeError
        If conversion fails.
    """
    ftype = (format_type or "").lower()

    # Early NetCDF passthrough for environments without xarray/netcdf4
    # If the on-disk file is already NetCDF (classic CDF or HDF5-based NetCDF4)
    # and the requested format is NetCDF with no variable selection, return
    # the bytes directly without decoding.
    if ftype == "netcdf" and decoded.path and not var:
        try:
            from pathlib import Path as _P

            _head = _P(decoded.path).read_bytes()[:4]
            if _head.startswith(b"CDF") or _head.startswith(b"\x89HDF"):
                return _P(decoded.path).read_bytes()
        except Exception:
            # If detection fails, continue with backend-specific handling
            pass

    if decoded.backend == "cfgrib" and decoded.dataset is not None:
        ds = decoded.dataset
        obj: Any = ds
        if var:
            obj = extract_variable(decoded, var)

        if ftype == "xarray":
            return obj

        if ftype == "dataframe":
            try:
                import pandas as pd  # noqa: F401  # type: ignore

                if hasattr(obj, "to_dataframe"):
                    return obj.to_dataframe().reset_index()
            except Exception as exc:  # pragma: no cover - optional dep
                raise ValueError(
                    "Pandas/xarray required for DataFrame conversion"
                ) from exc
            raise ValueError("Unsupported object for DataFrame conversion")

        if ftype == "netcdf":
            data_to_write = obj if hasattr(obj, "to_netcdf") else ds
            try:
                return _netcdf_bytes(data_to_write)
            except Exception as exc:
                # Known xarray failure mode: decoding cfgrib's 'step'
                # coordinate can assert on non-nanosecond timedeltas.
                # Re-open without timedelta decoding and retry before
                # reaching for wgrib2.
                if decoded.path:
                    try:
                        import xarray as xr  # type: ignore

                        # indexpath="" skips the .idx sidecar for the
                        # one-shot temp file; the context manager closes
                        # the retry dataset after serialization.
                        with xr.open_dataset(
                            decoded.path,
                            engine="cfgrib",
                            backend_kwargs={"indexpath": ""},
                            decode_timedelta=False,
                        ) as ds_raw:
                            obj_raw: Any = ds_raw
                            if var:
                                obj_raw = extract_variable(
                                    DecodedGRIB(backend="cfgrib", dataset=ds_raw), var
                                )
                            return _netcdf_bytes(obj_raw)
                    except Exception:
                        pass
                wgrib2_detail = ""
                if _has_wgrib2() and decoded.path:
                    tmp = tempfile.NamedTemporaryFile(suffix=".nc", delete=False)
                    tmp_path = tmp.name
                    tmp.close()
                    try:
                        res = subprocess.run(
                            ["wgrib2", decoded.path, "-netcdf", tmp_path],
                            capture_output=True,
                            text=True,
                            check=False,
                        )
                        if res.returncode == 0:
                            from pathlib import Path as _P

                            return _P(tmp_path).read_bytes()
                        # Surface the fallback's own failure detail; the
                        # original exception alone hides what wgrib2 said.
                        wgrib2_detail = (
                            f"; wgrib2 fallback failed (exit {res.returncode})"
                        )
                        if (res.stderr or "").strip():
                            wgrib2_detail += f": {res.stderr.strip()}"
                    finally:
                        import contextlib
                        from pathlib import Path as _P

                        with contextlib.suppress(Exception):
                            _P(tmp_path).unlink()
                # A failed conversion is an error. Never fabricate output:
                # a placeholder dataset returned as success poisons every
                # downstream consumer (this previously emitted a Dataset
                # with a single variable literally named 'dummy').
                raise RuntimeError(
                    f"NetCDF conversion failed: {exc}{wgrib2_detail}"
                ) from exc

        if ftype == "geotiff":
            # Enforce single-variable requirement up-front to avoid optional deps
            if var is None and hasattr(ds, "data_vars") and len(ds.data_vars) > 1:
                raise ValueError(
                    "GeoTIFF conversion supports a single variable. Provide 'var' to select one."
                )
            data_array = obj
            if hasattr(data_array, "data_vars"):
                # A Dataset (single variable — enforced above): take the
                # variable itself so the GRIB_* attrs are visible; cfgrib
                # stores grid metadata on variables, not the dataset.
                data_array = data_array[next(iter(data_array.data_vars))]
            # Prefer explicit georeferencing derived from the GRIB grid
            # metadata: rioxarray's to_raster writes no CRS/transform for
            # cfgrib datasets (2D lat/lon coords), and GRIB scan order
            # (south-first) must be normalized to GeoTIFF north-up.
            georef = _grib_georeference(data_array)
            if georef is not None:
                import numpy as np  # type: ignore
                from rasterio.io import MemoryFile

                crs, transform, flip = georef
                values = np.squeeze(np.asarray(data_array.values))
                if values.ndim != 2:
                    raise ValueError(
                        "GeoTIFF conversion needs a single 2D field; select one "
                        "level/time with 'var' or extract-variable first."
                    )
                if flip:
                    values = values[::-1, :]
                profile = {
                    "driver": "GTiff",
                    "width": values.shape[1],
                    "height": values.shape[0],
                    "count": 1,
                    "dtype": values.dtype.name,
                    "crs": crs,
                    "transform": transform,
                }
                with MemoryFile() as mem:
                    with mem.open(**profile) as dst:
                        dst.write(values, 1)
                    return mem.read()
            try:
                # Fallback: rioxarray for data that carries its own
                # georeferencing via the rio accessor.
                import rioxarray  # noqa: F401  # type: ignore

                tmp = tempfile.NamedTemporaryFile(suffix=".tif", delete=False)
                tmp_path = tmp.name
                tmp.close()
                data_array.rio.to_raster(tmp_path)  # type: ignore
                from pathlib import Path as _P

                return _P(tmp_path).read_bytes()
            except Exception as exc:  # pragma: no cover - optional dep
                raise ValueError(
                    "GeoTIFF conversion requires rioxarray/rasterio and georeferencing"
                ) from exc
            finally:
                import contextlib
                from pathlib import Path as _P

                with contextlib.suppress(Exception):
                    _P(tmp_path).unlink()  # type: ignore

    # Fallbacks for non-xarray backends
    if ftype == "netcdf" and decoded.path and _has_wgrib2():
        # Try wgrib2 if available to convert GRIB->NetCDF regardless of backend
        tmp = tempfile.NamedTemporaryFile(suffix=".nc", delete=False)
        tmp_path = tmp.name
        tmp.close()
        try:
            res = subprocess.run(
                ["wgrib2", decoded.path, "-netcdf", tmp_path],
                capture_output=True,
                text=True,
                check=False,
            )
            if res.returncode != 0:
                # A failed conversion is an error, never fabricated output.
                raise RuntimeError(res.stderr.strip() or "wgrib2 -netcdf failed")
            from pathlib import Path as _P

            return _P(tmp_path).read_bytes()
        finally:
            import contextlib
            from pathlib import Path as _P

            with contextlib.suppress(Exception):
                _P(tmp_path).unlink()

    if ftype == "geotiff":
        # No xarray dataset to rasterize. This previously fabricated a
        # 1x1 zero GeoTIFF "to satisfy header checks" — silent fake
        # output; a failed conversion must fail.
        raise RuntimeError(
            "GeoTIFF conversion requires the cfgrib backend (xarray dataset); "
            f"decoded backend {decoded.backend!r} has no GeoTIFF path."
        )

    # Non-xarray paths require explicit tooling; keep behavior clear
    raise ValueError(
        "Unsupported conversion for this backend. Prefer cfgrib/xarray or provide wgrib2."
    )


def validate_subset(decoded: DecodedGRIB, expected_fields: list[str]) -> None:
    """Validate that a decoded subset contains expected variables and shapes.

    This function currently validates variable presence. Shape and timestep
    validation is backend- and dataset-specific, and can be extended when
    stricter contracts are needed.

    Parameters
    ----------
    decoded : DecodedGRIB
        Decoded GRIB container.
    expected_fields : list of str
        Variable names that must be present. Regex patterns are allowed.

    Raises
    ------
    AssertionError
        If one or more variables are missing.
    """
    available = _list_variables(decoded)
    missing: list[str] = []
    for ef in expected_fields:
        pat = re.compile(ef)
        if not any(pat.search(v) for v in available):
            missing.append(ef)
    if missing:
        raise AssertionError(f"Missing expected variables: {', '.join(missing)}")


def extract_metadata(decoded: DecodedGRIB) -> dict[str, Any]:
    """Extract common metadata from a decoded GRIB subset.

    Returned keys include:
    - model_run: string or datetime-like when available
    - forecast_hour: integer forecast step when available
    - variables: list of variable names
    - grid: projection/grid information when available
    - bbox: (min_lon, min_lat, max_lon, max_lat) if coordinates present

    Parameters
    ----------
    decoded : DecodedGRIB
        Decoded GRIB container.

    Returns
    -------
    dict
        Metadata dictionary. Missing fields may be absent or set to None.
    """
    meta: dict[str, Any] = {"backend": decoded.backend}
    meta["variables"] = _list_variables(decoded)

    if decoded.backend == "cfgrib" and decoded.dataset is not None:
        ds = decoded.dataset
        # Model run / reference time and forecast step are commonly encoded in cfgrib coords
        for key in ("time", "valid_time", "analysis_time"):
            if key in ds.coords:
                try:
                    meta["model_run"] = ds.coords[key].values.tolist()
                    break
                except Exception:
                    pass
        if "step" in ds.coords:
            try:
                # Convert to hours if a pandas/np timedelta
                step_vals = ds.coords["step"].values
                meta["forecast_hour"] = getattr(
                    step_vals, "astype", lambda *_: step_vals
                )("timedelta64[h]").tolist()  # type: ignore
            except Exception:
                meta["forecast_hour"] = None
        # Bounding box from coordinates if present
        try:
            lat_name = (
                "latitude"
                if "latitude" in ds.coords
                else ("lat" if "lat" in ds.coords else None)
            )
            lon_name = (
                "longitude"
                if "longitude" in ds.coords
                else ("lon" if "lon" in ds.coords else None)
            )
            if lat_name and lon_name:
                lats = ds.coords[lat_name].values
                lons = ds.coords[lon_name].values
                meta["bbox"] = (
                    float(getattr(lons, "min", lambda: lons.min())()),
                    float(getattr(lats, "min", lambda: lats.min())()),
                    float(getattr(lons, "max", lambda: lons.max())()),
                    float(getattr(lats, "max", lambda: lats.max())()),
                )
        except Exception:
            pass
        # Projection info when available
        grid_keys = [
            k
            for k in ds.attrs
            if k.lower().startswith("grib") or k.lower().endswith("grid")
        ]
        if grid_keys:
            meta["grid"] = {k: ds.attrs.get(k) for k in grid_keys}

    elif decoded.backend == "pygrib" and decoded.messages:
        try:
            first = decoded.messages[0]
            meta["model_run"] = getattr(first, "analDate", None) or getattr(
                first, "validDate", None
            )
            meta["forecast_hour"] = getattr(first, "forecastTime", None)
            try:
                lats, lons = first.latlons()
                meta["bbox"] = (
                    float(lons.min()),
                    float(lats.min()),
                    float(lons.max()),
                    float(lats.max()),
                )
            except Exception:
                pass
        except Exception:
            pass

    elif decoded.backend == "wgrib2" and decoded.meta:
        try:
            # Best-effort parse
            entry0 = (
                decoded.meta[0]
                if isinstance(decoded.meta, list) and decoded.meta
                else {}
            )
            meta["model_run"] = entry0.get("date") or entry0.get("refTime")
            meta["forecast_hour"] = entry0.get("fcst_time") or entry0.get(
                "forecastTime"
            )
        except Exception:
            pass

    return meta
