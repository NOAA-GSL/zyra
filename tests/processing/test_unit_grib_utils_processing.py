import json
from types import SimpleNamespace

import pytest


def test_variable_not_found_error():
    xr = pytest.importorskip("xarray")
    from zyra.processing.grib_utils import (
        DecodedGRIB,
        VariableNotFoundError,
        extract_variable,
    )

    ds = xr.Dataset({"a": xr.DataArray([1, 2, 3], dims=["x"])})
    decoded = DecodedGRIB(backend="cfgrib", dataset=ds)
    with pytest.raises(VariableNotFoundError):
        extract_variable(decoded, r"^b$")


def test_geotiff_multivar_requires_var():
    xr = pytest.importorskip("xarray")
    from zyra.processing.grib_utils import DecodedGRIB, convert_to_format

    ds = xr.Dataset(
        {
            "a": xr.DataArray([[1, 2], [3, 4]], dims=["y", "x"]),
            "b": xr.DataArray([[5, 6], [7, 8]], dims=["y", "x"]),
        }
    )
    decoded = DecodedGRIB(backend="cfgrib", dataset=ds)
    with pytest.raises(ValueError):
        convert_to_format(decoded, "geotiff")


def test_wgrib2_json_fallback(monkeypatch):
    from zyra.processing.grib_utils import extract_variable, grib_decode

    # Pretend wgrib2 exists
    monkeypatch.setattr(
        "shutil.which", lambda name: "/usr/bin/wgrib2" if name == "wgrib2" else None
    )

    # Return simple JSON with one variable
    out = json.dumps(
        [{"shortName": "UGRD", "name": "u wind", "date": "20240101", "forecastTime": 3}]
    )

    def fake_run(args, capture_output, text, check):
        assert "-json" in args
        return SimpleNamespace(returncode=0, stdout=out, stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)

    dec = grib_decode(b"dummy", backend="wgrib2")
    matches = extract_variable(dec, r"UGRD")
    assert isinstance(matches, list) and matches and matches[0]["shortName"] == "UGRD"


def test_cdo_netcdf_to_grib2(monkeypatch):
    xr = pytest.importorskip("xarray")
    from zyra.processing.netcdf_data_processor import convert_to_grib2

    ds = xr.Dataset({"a": xr.DataArray([[1, 2], [3, 4]], dims=["y", "x"])})

    # Pretend CDO exists
    monkeypatch.setattr(
        "shutil.which", lambda name: "/usr/bin/cdo" if name == "cdo" else None
    )

    # Capture output target and write fake grib bytes
    def fake_run(args, capture_output, text, check):
        out_path = args[-1]
        with open(out_path, "wb") as f:
            f.write(b"GRIB2DATA")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)

    grib_bytes = convert_to_grib2(ds)
    assert grib_bytes == b"GRIB2DATA"
