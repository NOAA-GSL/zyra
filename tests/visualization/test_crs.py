import os
import tempfile
import pytest

# Skip Cartopy-heavy tests unless explicitly enabled
_has_cartopy = False
try:  # pragma: no cover - import guard
    import cartopy  # noqa: F401

    _has_cartopy = True
except Exception:
    pass

_skip_cartopy_heavy = (not _has_cartopy) or os.environ.get(
    "DATAVIZHUB_RUN_CARTOPY_TESTS"
) != "1"
pytestmark = pytest.mark.skipif(
    _skip_cartopy_heavy,
    reason="Cartopy-heavy tests require cartopy and opt-in (DATAVIZHUB_RUN_CARTOPY_TESTS=1)",
)


def _make_netcdf_with_crs(path: str, epsg: str = "EPSG:3857"):
    import numpy as np
    import xarray as xr

    data = (np.random.rand(4, 6)).astype("float32")
    da = xr.DataArray(data, dims=("y", "x"))
    ds = xr.Dataset({"var": da})
    ds.attrs["crs"] = epsg
    ds.to_netcdf(path)


def test_cli_heatmap_crs_warning():
    try:
        import cartopy  # noqa: F401
        import matplotlib  # noqa: F401
        import xarray  # noqa: F401
    except Exception as e:
        import pytest

        pytest.skip(f"Visualization deps missing: {e}")

    import subprocess, sys

    with tempfile.TemporaryDirectory() as td:
        nc = os.path.join(td, "crs.nc")
        _make_netcdf_with_crs(nc, epsg="EPSG:3857")
        out = os.path.join(td, "out.png")
        cmd = [
            sys.executable,
            "-m",
            "datavizhub.cli",
            "heatmap",
            "--input",
            nc,
            "--var",
            "var",
            "--output",
            out,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        assert proc.returncode == 0, proc.stderr
        # Expect a mismatch warning in stderr
        assert "differs from display CRS" in (proc.stderr or "")


def test_cli_heatmap_crs_override_suppresses_warning():
    try:
        import cartopy  # noqa: F401
        import matplotlib  # noqa: F401
        import xarray  # noqa: F401
    except Exception as e:
        import pytest

        pytest.skip(f"Visualization deps missing: {e}")

    import subprocess, sys

    with tempfile.TemporaryDirectory() as td:
        nc = os.path.join(td, "crs.nc")
        _make_netcdf_with_crs(nc, epsg="EPSG:3857")
        out = os.path.join(td, "out.png")
        cmd = [
            sys.executable,
            "-m",
            "datavizhub.cli",
            "heatmap",
            "--input",
            nc,
            "--var",
            "var",
            "--output",
            out,
            "--crs",
            "EPSG:4326",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        assert proc.returncode == 0, proc.stderr
        # No mismatch warning because user forced CRS to 4326
        assert "differs from display CRS" not in (proc.stderr or "")
