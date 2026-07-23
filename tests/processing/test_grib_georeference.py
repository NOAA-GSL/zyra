# SPDX-License-Identifier: Apache-2.0
"""GeoTIFF conversion must carry georeferencing derived from GRIB attrs.

Previously `convert-format geotiff` wrote correct pixels with no CRS,
an identity transform, and GRIB scan order (south-first → upside-down
image). The attrs below mirror a real HRRR composite-reflectivity
message from the public noaa-hrrr-bdp-pds bucket.
"""

from __future__ import annotations

import numpy as np
import pytest

xr = pytest.importorskip("xarray")
rasterio = pytest.importorskip("rasterio")
pytest.importorskip("pyproj")

from zyra.processing.grib_utils import (  # noqa: E402
    DecodedGRIB,
    _grib_georeference,
    convert_to_format,
)

HRRR_ATTRS = {
    "GRIB_gridType": "lambert",
    "GRIB_Nx": 1799,
    "GRIB_Ny": 1059,
    "GRIB_DxInMetres": 3000.0,
    "GRIB_DyInMetres": 3000.0,
    "GRIB_Latin1InDegrees": 38.5,
    "GRIB_Latin2InDegrees": 38.5,
    "GRIB_LaDInDegrees": 38.5,
    "GRIB_LoVInDegrees": 262.5,
    "GRIB_jScansPositively": 1,
    "GRIB_latitudeOfFirstGridPointInDegrees": 21.138123,
    "GRIB_longitudeOfFirstGridPointInDegrees": 237.280472,
}
# Projected bounds of the HRRR CONUS grid, verified against the live
# message with pygrib (corner center minus half a cell).
HRRR_WEST, HRRR_NORTH = -2699020.1, 1588193.8


def _hrrr_like_array(ny=6, nx=9):
    attrs = dict(HRRR_ATTRS)
    attrs["GRIB_Ny"], attrs["GRIB_Nx"] = ny, nx
    data = np.arange(ny * nx, dtype="float32").reshape(ny, nx)
    return xr.DataArray(data, dims=("y", "x"), attrs=attrs)


def test_lambert_georeference_matches_live_hrrr_values():
    da = _hrrr_like_array(ny=1059, nx=1799)
    georef = _grib_georeference(da)
    assert georef is not None
    crs, transform, flip = georef
    assert flip is True
    d = crs.to_dict()
    assert d["proj"] == "lcc"
    assert d["lon_0"] == pytest.approx(262.5)
    assert transform.c == pytest.approx(HRRR_WEST, abs=1.0)  # west edge
    assert transform.f == pytest.approx(HRRR_NORTH, abs=1.0)  # north edge
    assert transform.a == pytest.approx(3000.0)


def test_regular_ll_georeference():
    attrs = {
        "GRIB_gridType": "regular_ll",
        "GRIB_Nx": 360,
        "GRIB_Ny": 181,
        "GRIB_iDirectionIncrementInDegrees": 1.0,
        "GRIB_jDirectionIncrementInDegrees": 1.0,
        "GRIB_jScansPositively": 0,
        "GRIB_latitudeOfFirstGridPointInDegrees": 90.0,
        "GRIB_longitudeOfFirstGridPointInDegrees": 0.0,
    }
    da = xr.DataArray(
        np.zeros((181, 360), dtype="float32"), dims=("y", "x"), attrs=attrs
    )
    crs, transform, flip = _grib_georeference(da)
    assert crs.to_epsg() == 4326
    assert flip is False
    assert transform.f == pytest.approx(90.5)
    assert transform.c == pytest.approx(-0.5)


def test_unknown_grid_returns_none():
    da = xr.DataArray(np.zeros((4, 4)), dims=("y", "x"), attrs={"GRIB_gridType": "??"})
    assert _grib_georeference(da) is None


def test_convert_geotiff_carries_georeference_and_north_up():
    da = _hrrr_like_array(ny=6, nx=9)
    ds = xr.Dataset({"refc": da})
    decoded = DecodedGRIB(backend="cfgrib", dataset=ds)
    tif_bytes = convert_to_format(decoded, "geotiff")
    from rasterio.io import MemoryFile

    with MemoryFile(tif_bytes) as mem, mem.open() as out:
        assert out.crs is not None
        assert not out.transform.is_identity
        a = out.read(1)
    # South-first GRIB rows must come out north-up: the source's last
    # row (values 45..53 for the 6x9 grid) is the image's first row.
    assert a[0, 0] == pytest.approx(45.0)
    assert a[-1, 0] == pytest.approx(0.0)
