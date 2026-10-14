# SPDX-License-Identifier: Apache-2.0
"""GeoTIFF conversion must carry georeferencing derived from GRIB attrs.

Previously `convert-format geotiff` wrote correct pixels with no CRS,
an identity transform, and GRIB scan order (south-first → upside-down
image). The attrs below mirror a real HRRR composite-reflectivity
message from the public noaa-hrrr-bdp-pds bucket.

The RRFS attrs mirror live records from noaa-rrfs-ops-pds and cover the
grid types cfgrib does not describe on its own — see issue #365. Their
expected corner coordinates were taken from ``pygrib.latlons()`` on the
same messages.
"""

from __future__ import annotations

import numpy as np
import pytest

xr = pytest.importorskip("xarray")
pytest.importorskip("rasterio")
pytest.importorskip("pyproj")

from zyra.processing.grib_utils import (  # noqa: E402
    _GRID_READ_KEYS,
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

# RRFS HI 2.5 km — mercator. cfgrib reports this grid as a flat 'values'
# dimension, which is what used to raise MissingSpatialDimensionError.
RRFS_HI_ATTRS = {
    "GRIB_gridType": "mercator",
    "GRIB_Nx": 321,
    "GRIB_Ny": 225,
    "GRIB_DiInMetres": 2500.0,
    "GRIB_DjInMetres": 2500.0,
    "GRIB_LaDInDegrees": 20.0,
    "GRIB_jScansPositively": 1,
    "GRIB_iScansNegatively": 0,
    "GRIB_latitudeOfFirstGridPointInDegrees": 18.072699,
    "GRIB_longitudeOfFirstGridPointInDegrees": 198.474999,
    "GRIB_radius": 6371229,
}
RRFS_HI_WEST, RRFS_HI_NORTH = -16879450.9, 2481834.7

# RRFS AK 3 km — polar stereographic, north pole.
RRFS_AK_ATTRS = {
    "GRIB_gridType": "polar_stereographic",
    "GRIB_Nx": 1649,
    "GRIB_Ny": 1105,
    "GRIB_DxInMetres": 2976.0,
    "GRIB_DyInMetres": 2976.0,
    "GRIB_LaDInDegrees": 60.0,
    "GRIB_orientationOfTheGridInDegrees": 210.0,
    "GRIB_projectionCentreFlag": 0,
    "GRIB_jScansPositively": 1,
    "GRIB_iScansNegatively": 0,
    "GRIB_latitudeOfFirstGridPointInDegrees": 40.53,
    "GRIB_longitudeOfFirstGridPointInDegrees": 181.429,
    "GRIB_radius": 6371229,
}

# RRFS NA 13 km — rotated pole. GRIB names the southern pole; the first
# grid point is in rotated coordinates.
RRFS_NA_ATTRS = {
    "GRIB_gridType": "rotated_ll",
    "GRIB_Nx": 1127,
    "GRIB_Ny": 683,
    "GRIB_iDirectionIncrementInDegrees": 0.1083,
    "GRIB_jDirectionIncrementInDegrees": 0.1083,
    "GRIB_latitudeOfSouthernPoleInDegrees": -35.0,
    "GRIB_longitudeOfSouthernPoleInDegrees": 247.0,
    "GRIB_angleOfRotationInDegrees": 0.0,
    "GRIB_jScansPositively": 1,
    "GRIB_iScansNegatively": 0,
    "GRIB_latitudeOfFirstGridPointInDegrees": -36.9303,
    "GRIB_longitudeOfFirstGridPointInDegrees": 299.0,
    "GRIB_radius": 6371229,
}


def _hrrr_like_array(ny=6, nx=9):
    attrs = dict(HRRR_ATTRS)
    attrs["GRIB_Ny"], attrs["GRIB_Nx"] = ny, nx
    data = np.arange(ny * nx, dtype="float32").reshape(ny, nx)
    return xr.DataArray(data, dims=("y", "x"), attrs=attrs)


def _grid_only(attrs):
    """A DataArray carrying grid attrs but no meaningful values.

    ``_grib_georeference`` reads attrs alone, so the georeferencing of a
    full-size operational grid can be checked without allocating it.
    """
    return xr.DataArray(np.zeros((1, 1), dtype="float32"), dims=("y", "x"), attrs=attrs)


def _pixel_center_lonlat(grid, row, col):
    """Longitude/latitude of a pixel center in the north-up image."""
    import pyproj

    x, y = grid.transform * (col + 0.5, row + 0.5)
    back = pyproj.Transformer.from_crs(grid.crs.to_wkt(), "EPSG:4326", always_xy=True)
    return back.transform(x, y)


def test_lambert_georeference_matches_live_hrrr_values():
    da = _hrrr_like_array(ny=1059, nx=1799)
    grid = _grib_georeference(da)
    assert grid is not None
    assert grid.flip_rows is True
    d = grid.crs.to_dict()
    assert d["proj"] == "lcc"
    assert d["lon_0"] == pytest.approx(262.5)
    assert grid.transform.c == pytest.approx(HRRR_WEST, abs=1.0)  # west edge
    assert grid.transform.f == pytest.approx(HRRR_NORTH, abs=1.0)  # north edge
    assert grid.transform.a == pytest.approx(3000.0)


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
    grid = _grib_georeference(da)
    assert grid.crs.to_epsg() == 4326
    assert grid.flip_rows is False
    assert grid.shape == (181, 360)
    assert grid.transform.f == pytest.approx(90.5)
    assert grid.transform.c == pytest.approx(-0.5)


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


def test_grid_definition_keys_are_requested_from_cfgrib(monkeypatch):
    """cfgrib describes mercator/polar grids only when asked to.

    Neither type appears in cfgrib's own GRID_TYPE_MAP, so without
    ``read_keys`` their messages arrive with no grid metadata at all.
    """
    seen: dict = {}

    def fake_open_dataset(path, **kwargs):
        seen.update(kwargs)
        return xr.Dataset({"x": xr.DataArray(np.zeros(1))})

    monkeypatch.setattr(xr, "open_dataset", fake_open_dataset)
    from zyra.processing.grib_utils import grib_decode

    grib_decode(b"GRIB-not-really")
    read_keys = seen["backend_kwargs"]["read_keys"]
    assert read_keys is _GRID_READ_KEYS
    for key in ("Nx", "Ny", "DiInMetres", "DxInMetres", "LaDInDegrees", "radius"):
        assert key in read_keys


def test_mercator_georeference_matches_live_rrfs_hi():
    grid = _grib_georeference(_grid_only(RRFS_HI_ATTRS))
    assert grid is not None
    d = grid.crs.to_dict()
    assert d["proj"] == "merc"
    assert d["lat_ts"] == pytest.approx(20.0)
    assert d["R"] == pytest.approx(6371229.0)
    assert grid.shape == (225, 321)
    assert grid.flip_rows is True
    assert grid.transform.a == pytest.approx(2500.0)
    assert grid.transform.c == pytest.approx(RRFS_HI_WEST, abs=1.0)
    assert grid.transform.f == pytest.approx(RRFS_HI_NORTH, abs=1.0)
    # North-west and south-west corners against the pygrib truth.
    lon, lat = _pixel_center_lonlat(grid, 0, 0)
    assert (lat, lon) == pytest.approx((23.08780, -161.52500), abs=1e-4)
    lon, lat = _pixel_center_lonlat(grid, 224, 320)
    assert (lat, lon) == pytest.approx((18.07270, -153.86901), abs=1e-4)


def test_mercator_values_dimension_converts_north_up():
    """cfgrib's flat 'values' dim used to raise MissingSpatialDimensionError."""
    ny, nx = 6, 9
    attrs = dict(RRFS_HI_ATTRS)
    attrs["GRIB_Ny"], attrs["GRIB_Nx"] = ny, nx
    da = xr.DataArray(
        np.arange(ny * nx, dtype="float32"), dims=("values",), attrs=attrs
    )
    decoded = DecodedGRIB(backend="cfgrib", dataset=xr.Dataset({"refc": da}))
    tif_bytes = convert_to_format(decoded, "geotiff")
    from rasterio.io import MemoryFile

    with MemoryFile(tif_bytes) as mem, mem.open() as out:
        assert out.crs is not None
        assert not out.transform.is_identity
        assert (out.height, out.width) == (ny, nx)
        a = out.read(1)
    # Folded row-major, then flipped south-first -> north-up.
    assert a[0, 0] == pytest.approx(45.0)
    assert a[-1, 0] == pytest.approx(0.0)


def test_polar_stereographic_georeference_matches_live_rrfs_ak():
    grid = _grib_georeference(_grid_only(RRFS_AK_ATTRS))
    assert grid is not None
    d = grid.crs.to_dict()
    assert d["proj"] == "stere"
    assert d["lat_0"] == pytest.approx(90.0)
    assert d["lat_ts"] == pytest.approx(60.0)
    assert d["lon_0"] == pytest.approx(-150.0)  # orientation 210 normalized
    assert grid.shape == (1105, 1649)
    assert grid.flip_rows is True
    assert grid.transform.a == pytest.approx(2976.0)
    # Every corner of the north-up image against the pygrib truth.
    lon, lat = _pixel_center_lonlat(grid, 0, 0)
    assert (lat, lon) == pytest.approx((61.396873, 150.201215), abs=1e-4)
    lon, lat = _pixel_center_lonlat(grid, 1104, 0)
    assert (lat, lon) == pytest.approx((40.53, -178.571), abs=1e-4)
    lon, lat = _pixel_center_lonlat(grid, 1104, 1648)
    assert (lat, lon) == pytest.approx((41.742794, -124.589823), abs=1e-4)


def test_polar_stereographic_south_pole_flag():
    attrs = dict(RRFS_AK_ATTRS)
    attrs["GRIB_projectionCentreFlag"] = 128
    d = _grib_georeference(_grid_only(attrs)).crs.to_dict()
    assert d["lat_0"] == pytest.approx(-90.0)
    assert d["lat_ts"] == pytest.approx(-60.0)


def test_rotated_ll_georeference_matches_live_rrfs_na():
    grid = _grib_georeference(_grid_only(RRFS_NA_ATTRS))
    assert grid is not None
    assert grid.shape == (683, 1127)
    assert grid.flip_rows is True
    # A rotated-pole CRS is not something GeoTIFF can hold.
    assert grid.warp_to_epsg4326 is True
    # The transform lives in rotated degrees, not metres.
    assert grid.transform.a == pytest.approx(0.1083)
    assert grid.transform.c == pytest.approx(-61.05415, abs=1e-4)
    assert grid.transform.f == pytest.approx(36.98445, abs=1e-4)
    # Rotating back must land on the real corners pygrib reports.
    lon, lat = _pixel_center_lonlat(grid, 0, 0)
    assert (lat, lon) == pytest.approx((41.459024, 135.891376), abs=1e-4)
    lon, lat = _pixel_center_lonlat(grid, 682, 0)
    assert (lat, lon) == pytest.approx((-1.557179, -157.378928), abs=1e-4)


def test_rotated_ll_geotiff_is_reprojected_to_epsg4326(caplog):
    ny, nx = 8, 10
    attrs = dict(RRFS_NA_ATTRS)
    attrs["GRIB_Ny"], attrs["GRIB_Nx"] = ny, nx
    da = xr.DataArray(
        np.arange(ny * nx, dtype="float32").reshape(ny, nx),
        dims=("y", "x"),
        attrs=attrs,
    )
    decoded = DecodedGRIB(backend="cfgrib", dataset=xr.Dataset({"colmd": da}))
    with caplog.at_level("WARNING"):
        tif_bytes = convert_to_format(decoded, "geotiff")
    assert "rotated-pole" in caplog.text
    from rasterio.io import MemoryFile

    with MemoryFile(tif_bytes) as mem, mem.open() as out:
        assert out.crs.to_epsg() == 4326
        assert not out.transform.is_identity
        # Outside the warped footprint is nodata, not a fabricated zero.
        assert np.isnan(out.nodata)


def test_east_first_scan_flips_columns():
    """iScansNegatively=1 puts the first grid point on the east edge."""
    ny, nx = 3, 4
    attrs = {
        "GRIB_gridType": "regular_ll",
        "GRIB_Nx": nx,
        "GRIB_Ny": ny,
        "GRIB_iDirectionIncrementInDegrees": 1.0,
        "GRIB_jDirectionIncrementInDegrees": 1.0,
        "GRIB_jScansPositively": 0,
        "GRIB_iScansNegatively": 1,
        "GRIB_latitudeOfFirstGridPointInDegrees": 10.0,
        "GRIB_longitudeOfFirstGridPointInDegrees": 3.0,
    }
    grid = _grib_georeference(_grid_only(attrs))
    assert grid.flip_cols is True
    # West edge is three cells back from the first point, minus half a cell.
    assert grid.transform.c == pytest.approx(-0.5)
    assert grid.transform.f == pytest.approx(10.5)

    da = xr.DataArray(
        np.arange(ny * nx, dtype="float32").reshape(ny, nx),
        dims=("y", "x"),
        attrs=attrs,
    )
    decoded = DecodedGRIB(backend="cfgrib", dataset=xr.Dataset({"t": da}))
    from rasterio.io import MemoryFile

    with MemoryFile(convert_to_format(decoded, "geotiff")) as mem, mem.open() as out:
        a = out.read(1)
    # Rows already run north-first; only the columns reverse.
    assert list(a[0]) == [3.0, 2.0, 1.0, 0.0]


def test_ungeoreferenced_grid_warns_before_falling_back(caplog):
    da = xr.DataArray(
        np.zeros((4, 4), dtype="float32"),
        dims=("y", "x"),
        attrs={"GRIB_gridType": "space_view"},
    )
    decoded = DecodedGRIB(backend="cfgrib", dataset=xr.Dataset({"t": da}))
    with caplog.at_level("WARNING"):
        convert_to_format(decoded, "geotiff")
    # The rioxarray fallback still writes the pixels, but the silent
    # upside-down output in issue #365 must now announce itself.
    assert "space_view" in caplog.text
    assert "without a CRS" in caplog.text
