# SPDX-License-Identifier: Apache-2.0
"""convert-format must never fabricate output (issue: dummy dataset).

A failed conversion previously returned a placeholder — a NetCDF with
one variable literally named 'dummy', or a 1x1 zero GeoTIFF — with
exit 0. Failures must raise so callers see the real error.
"""

from __future__ import annotations

import re

import pytest

xr = pytest.importorskip("xarray")
np = pytest.importorskip("numpy")

from zyra.processing.grib_utils import (  # noqa: E402
    DecodedGRIB,
    _netcdf_bytes,
    convert_to_format,
)


class _Unwritable:
    """Quacks like a Dataset but always fails to serialize."""

    def to_netcdf(self, *a, **k):
        raise OSError("disk on fire")


def test_failed_netcdf_conversion_raises_not_fabricates():
    decoded = DecodedGRIB(backend="cfgrib", dataset=_Unwritable(), path=None)
    with pytest.raises(RuntimeError, match="NetCDF conversion failed"):
        convert_to_format(decoded, "netcdf")


def test_geotiff_without_xarray_backend_raises():
    decoded = DecodedGRIB(backend="pygrib", messages=[], path=None)
    with pytest.raises(RuntimeError, match="no GeoTIFF path"):
        convert_to_format(decoded, "geotiff")


def test_netcdf_bytes_roundtrip_real_dataset(tmp_path):
    ds = xr.Dataset({"t": (("y", "x"), np.arange(6, dtype="float32").reshape(2, 3))})
    out = _netcdf_bytes(ds)
    assert out[:3] == b"CDF" or out[:4] == b"\x89HDF"
    # Re-open via a real file: file-like reads only work with some
    # engines (e.g. scipy/h5netcdf), while a path works with any
    # installed NetCDF engine — mirrors load_netcdf's approach.
    p = tmp_path / "roundtrip.nc"
    p.write_bytes(out)
    with xr.open_dataset(p) as back:
        assert "t" in back and float(back["t"].values[1, 2]) == 5.0


def test_no_dummy_variable_can_escape():
    # Regression guard: no fabricated 'dummy' dataset construction may
    # reappear in any conversion path. Regex-based so it survives
    # formatting changes.
    import inspect

    import zyra.processing.grib_utils as gu

    src = inspect.getsource(gu)
    assert not re.search(r"Dataset\(\s*\{\s*[\"']dummy[\"']", src)
