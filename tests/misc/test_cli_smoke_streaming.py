import importlib
import io
import subprocess
import sys
from pathlib import Path
from typing import Optional

import pytest


def _run_cli(args, input_bytes: Optional[bytes] = None) -> subprocess.CompletedProcess:
    # Use module invocation to avoid reliance on installed console scripts
    cmd = [sys.executable, "-m", "zyra.cli", *args]
    return subprocess.run(cmd, input=input_bytes, capture_output=True)


def _have_modules(*names: str) -> bool:
    for n in names:
        try:
            importlib.import_module(n)
        except Exception:
            return False
    return True


def _read_demo_nc_bytes() -> bytes:
    p = Path("tests/testdata/demo.nc")
    return p.read_bytes()


def test_decode_grib2_raw_passthrough_netcdf(monkeypatch, capsysbinary):
    # Simulate piping a NetCDF file into decode-grib2 --raw
    from zyra.cli import main

    demo = _read_demo_nc_bytes()
    fake_stdin = type("S", (), {"buffer": io.BytesIO(demo)})()
    monkeypatch.setattr(sys, "stdin", fake_stdin)

    rc = main(["process", "decode-grib2", "-", "--raw"])
    assert rc == 0
    captured = capsysbinary.readouterr()
    # stdout should contain the exact bytes we piped in
    assert captured.out == demo
    assert captured.err == b""


def test_extract_variable_stdout_netcdf_simulated(monkeypatch, capsysbinary):
    # Simulate wgrib2 producing NetCDF bytes for the selected variable
    from types import SimpleNamespace

    from zyra.cli import main

    demo = _read_demo_nc_bytes()
    fake_stdin = type("S", (), {"buffer": io.BytesIO(b"GRIBDUMMY")})()
    monkeypatch.setattr(sys, "stdin", fake_stdin)

    # Pretend wgrib2 exists
    monkeypatch.setattr(
        "shutil.which", lambda name: "/usr/bin/wgrib2" if name == "wgrib2" else None
    )

    # Fake subprocess to write demo.nc to the requested output path
    def fake_run(args, capture_output, text, check):
        # last arg is output path for -netcdf/-grib
        out_path = args[-1]
        Path(out_path).write_bytes(demo)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)

    rc = main(
        ["process", "extract-variable", "-", "TMP", "--stdout", "--format", "netcdf"]
    )
    assert rc == 0
    captured = capsysbinary.readouterr()
    # Output should be exactly the NetCDF bytes produced by fake wgrib2
    assert captured.out == demo


def test_convert_format_autodetect_netcdf_from_stdin(monkeypatch, capsysbinary):
    # Feed NetCDF bytes on stdin and request NetCDF (round-trip)
    from zyra.cli import main

    demo = _read_demo_nc_bytes()
    fake_stdin = type("S", (), {"buffer": io.BytesIO(demo)})()
    monkeypatch.setattr(sys, "stdin", fake_stdin)

    rc = main(["process", "convert-format", "-", "netcdf", "--stdout"])
    assert rc == 0
    captured = capsysbinary.readouterr()
    # Check magic bytes for NetCDF classic (CDF) or NetCDF4/HDF5
    # Be tolerant of HDF5 variants across environments: allow just "\x89HDF"
    assert captured.out.startswith(b"CDF") or captured.out.startswith(b"\x89HDF")


@pytest.mark.cli
def test_grib2_raw_matches_file_bytes():
    if not Path("tests/testdata/demo.grib2").exists():
        pytest.skip("demo.grib2 not found", allow_module_level=True)
    # datavizhub decode-grib2 tests/testdata/demo.grib2 --raw
    demo_path = Path("tests/testdata/demo.grib2")
    expected = demo_path.read_bytes()
    res = _run_cli(["process", "decode-grib2", str(demo_path), "--raw"])
    assert res.returncode == 0, res.stderr.decode(errors="ignore")
    assert res.stdout == expected
    assert res.stderr == b""


@pytest.mark.cli
def test_grib2_to_netcdf_pipeline_header_check():
    if not Path("tests/testdata/demo.grib2").exists():
        pytest.skip("demo.grib2 not found", allow_module_level=True)
    if not _have_modules("xarray", "cfgrib"):
        pytest.skip("xarray/cfgrib not available for NetCDF conversion")
    # Pipe raw GRIB2 into: datavizhub convert-format - netcdf --stdout
    demo_path = Path("tests/testdata/demo.grib2")
    raw = _run_cli(["process", "decode-grib2", str(demo_path), "--raw"]).stdout
    res = _run_cli(
        ["process", "convert-format", "-", "netcdf", "--stdout"], input_bytes=raw
    )
    assert res.returncode == 0, res.stderr.decode(errors="ignore")
    # Validate NetCDF magic numbers: classic CDF or HDF5-based NetCDF4
    assert res.stdout.startswith(b"CDF") or res.stdout.startswith(b"\x89HDF")


@pytest.mark.cli
def test_grib2_extract_variable_stdout_netcdf_header():
    if not Path("tests/testdata/demo.grib2").exists():
        pytest.skip("demo.grib2 not found", allow_module_level=True)
    if not _have_modules("xarray", "cfgrib"):
        pytest.skip("xarray/cfgrib not available for NetCDF conversion")
    # datavizhub extract-variable tests/testdata/demo.grib2 "TMP" --stdout --format netcdf
    demo_path = Path("tests/testdata/demo.grib2")
    res = _run_cli(
        [
            "process",
            "extract-variable",
            str(demo_path),
            "TMP",
            "--stdout",
            "--format",
            "netcdf",
        ]
    )
    assert res.returncode == 0, res.stderr.decode(errors="ignore")
    assert res.stdout.startswith(b"CDF") or res.stdout.startswith(b"\x89HDF")


@pytest.mark.cli
def test_grib2_to_geotiff_pipeline_header_check():
    if not Path("tests/testdata/demo.grib2").exists():
        pytest.skip("demo.grib2 not found", allow_module_level=True)
    if not _have_modules("xarray", "cfgrib"):
        pytest.skip("xarray/cfgrib not available for GeoTIFF conversion")
    if not _have_modules("rioxarray"):
        pytest.skip("rioxarray not available for GeoTIFF conversion")
    # Pipe raw GRIB2 into: datavizhub convert-format - geotiff --stdout
    demo_path = Path("tests/testdata/demo.grib2")
    raw = _run_cli(["process", "decode-grib2", str(demo_path), "--raw"]).stdout
    res = _run_cli(
        ["process", "convert-format", "-", "geotiff", "--stdout"], input_bytes=raw
    )
    assert res.returncode == 0, res.stderr.decode(errors="ignore")
    # GeoTIFF header is either little-endian "II" or big-endian "MM"
    assert res.stdout.startswith(b"II") or res.stdout.startswith(b"MM")
