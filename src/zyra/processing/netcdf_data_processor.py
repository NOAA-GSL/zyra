import os
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from typing import Any, Iterable, Iterator


def _has_wgrib2() -> bool:
    """Check whether the wgrib2 CLI is available on PATH.

    Returns
    -------
    bool
        True if a wgrib2 executable is found, otherwise False.
    """
    return shutil.which("wgrib2") is not None


@contextmanager
def load_netcdf(path_or_bytes: str | bytes) -> Iterator[Any]:
    """Context manager that opens a NetCDF dataset from a path or bytes.

    Uses xarray under the hood. For byte inputs, a temporary file is created.
    Always closes the dataset and removes any temporary file when the context
    exits.

    Parameters
    ----------
    path_or_bytes : str or bytes
        Filesystem path to a NetCDF file or the raw bytes of one.

    Yields
    ------
    xarray.Dataset
        The opened dataset, valid within the context.

    Raises
    ------
    RuntimeError
        If the dataset cannot be opened or xarray is missing.
    """
    try:
        import xarray as xr  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError("xarray is required to load NetCDF data") from exc

    tmp_path: str | None = None
    ds = None
    try:
        if isinstance(path_or_bytes, (bytes, bytearray)):
            fd, tmp_path = tempfile.mkstemp(suffix=".nc")
            with os.fdopen(fd, "wb") as f:
                f.write(path_or_bytes)  # type: ignore[arg-type]
            path = tmp_path
        else:
            path = str(path_or_bytes)
        ds = xr.open_dataset(path)
        yield ds
    except Exception as exc:
        raise RuntimeError(f"Failed to open NetCDF: {exc}") from exc
    finally:
        if ds is not None:
            from contextlib import suppress

            with suppress(Exception):
                ds.close()
        if tmp_path is not None:
            from contextlib import suppress
            from pathlib import Path

            with suppress(Exception):
                Path(tmp_path).unlink()


def subset_netcdf(
    dataset: Any,
    variables: Iterable[str] | None = None,
    bbox: tuple[float, float, float, float] | None = None,
    time_range: tuple[Any, Any] | None = None,
) -> Any:
    """Subset an ``xarray.Dataset`` by variables, spatial extent, and time.

    Applies up to three filters in order: variable selection, spatial bounding
    box, and time window. Any filter can be omitted by passing ``None``.

    Parameters
    ----------
    dataset : xarray.Dataset
        Dataset returned by ``load_netcdf`` or other xarray operations.
    variables : iterable of str, optional
        Variable names to keep. If ``None``, keep all variables.
    bbox : tuple of float, optional
        Spatial bounding box as ``(min_lon, min_lat, max_lon, max_lat)``.
        Requires the dataset to have ``lat``/``latitude`` and ``lon``/``longitude``
        coordinates for selection.
    time_range : tuple[Any, Any], optional
        Start and end values compatible with ``xarray`` time selection, e.g.
        strings, datetimes, or numpy datetime64.

    Returns
    -------
    xarray.Dataset
        A new dataset view with the requested subset applied.

    Raises
    ------
    ValueError
        If ``bbox`` is provided but the dataset does not expose recognizable
        latitude/longitude coordinates for spatial selection.

    Examples
    --------
    Select temperature over a region and time range:

    >>> ds = subset_netcdf(ds, variables=["t2m"], bbox=(-110, 30, -90, 40), time_range=("2024-01-01", "2024-01-02"))
    """
    ds = dataset
    if variables:
        ds = ds[sorted(set(variables))]

    # Spatial selection
    if bbox is not None:
        min_lon, min_lat, max_lon, max_lat = bbox
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
        if not lat_name or not lon_name:
            raise ValueError("Dataset lacks lat/lon coordinates for bbox selection")
        ds = ds.sel(
            {lat_name: slice(min_lat, max_lat), lon_name: slice(min_lon, max_lon)}
        )

    if time_range is not None and "time" in ds.coords:
        start, end = time_range
        ds = ds.sel(time=slice(start, end))

    return ds


def convert_to_grib2(dataset: Any) -> bytes:
    """Convert a NetCDF dataset to GRIB2 via external tooling.

    Note: wgrib2 does not support generic NetCDF→GRIB2 conversion. Common
    practice is to use CDO (Climate Data Operators) with something like
    ``cdo -f grb2 copy in.nc out.grb2``. This function will attempt to use
    CDO if available; otherwise it raises a clear error and asks the caller
    to specify the desired tool.

    Parameters
    ----------
    dataset : xarray.Dataset
        Dataset to convert.

    Returns
    -------
    bytes
        Raw GRIB2 file content.

    Raises
    ------
    RuntimeError
        If no supported CLI is available or the conversion fails.
    """
    cdo_path = shutil.which("cdo")
    if cdo_path is None:  # pragma: no cover - external tool
        raise RuntimeError(
            "NetCDF→GRIB2 conversion requires an external tool (e.g., CDO). "
            "Please install CDO or specify your preferred converter."
        )

    nc_tmp = tempfile.NamedTemporaryFile(suffix=".nc", delete=False)
    nc_path = nc_tmp.name
    nc_tmp.close()
    grib_tmp = tempfile.NamedTemporaryFile(suffix=".grib2", delete=False)
    grib_path = grib_tmp.name
    grib_tmp.close()
    try:
        # Prefer on-disk export to avoid engine limitations
        dataset.to_netcdf(nc_path)

        res = subprocess.run(
            [cdo_path, "-f", "grb2", "copy", nc_path, grib_path],
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode != 0:  # pragma: no cover - external tool
            raise RuntimeError(res.stderr.strip() or "CDO conversion failed")
        from pathlib import Path

        return Path(grib_path).read_bytes()
    finally:
        from contextlib import suppress
        from pathlib import Path

        for p in (nc_path, grib_path):
            with suppress(Exception):
                Path(p).unlink()
