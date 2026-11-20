# SPDX-License-Identifier: Apache-2.0
"""Guard the binary test fixtures against silent corruption.

These fixtures were once committed while `* text eol=lf` applied to every
file, so git rewrote CRLF byte pairs inside them and they stopped decoding.
Tests that only pipe the bytes through kept passing. The structural checks
below need no optional dependencies, so they run everywhere; the decode
checks run when the matching reader is installed.
"""

import ast
import shutil
import struct
import subprocess
from pathlib import Path

import pytest

GRIB2 = Path("tests/testdata/demo.grib2")
NETCDF = [Path("tests/testdata/demo.nc"), Path("samples/demo.nc")]
NPY = Path("samples/demo.npy")
HDF5_SIGNATURE = b"\x89HDF\r\n\x1a\n"


def test_grib2_messages_are_complete():
    data = GRIB2.read_bytes()
    offset = 0
    messages = 0
    while offset < len(data):
        assert data[offset : offset + 4] == b"GRIB", f"no GRIB header at {offset}"
        assert data[offset + 7] == 2, "expected GRIB edition 2"
        length = struct.unpack(">Q", data[offset + 8 : offset + 16])[0]
        assert (
            data[offset + length - 4 : offset + length] == b"7777"
        ), f"message {messages} does not end with 7777 at its declared length"
        offset += length
        messages += 1
    assert messages >= 1
    assert offset == len(data), "trailing bytes after the last GRIB message"


@pytest.mark.parametrize("path", NETCDF, ids=str)
def test_netcdf4_superblock_matches_file_size(path):
    data = path.read_bytes()
    assert data[:8] == HDF5_SIGNATURE, "HDF5 signature damaged"
    version = data[8]
    assert version in (2, 3), f"unexpected HDF5 superblock version {version}"
    size_of_offsets = data[9]
    base = int.from_bytes(data[12 : 12 + size_of_offsets], "little")
    eof_field = 12 + 2 * size_of_offsets
    eof = int.from_bytes(data[eof_field : eof_field + size_of_offsets], "little")
    assert base + eof == len(data), "HDF5 end-of-file address != file size"


def test_npy_header_matches_file_size():
    data = NPY.read_bytes()
    assert data[:6] == b"\x93NUMPY"
    major = data[6]
    header_start = 10 if major == 1 else 12
    fmt = "<H" if major == 1 else "<I"
    header_len = struct.unpack(fmt, data[8:header_start])[0]
    header = ast.literal_eval(
        data[header_start : header_start + header_len].decode("latin1")
    )
    count = 1
    for dim in header["shape"]:
        count *= dim
    itemsize = int("".join(c for c in header["descr"] if c.isdigit()))
    assert header_start + header_len + count * itemsize == len(data)


@pytest.mark.skipif(shutil.which("git") is None, reason="git not available")
def test_fixtures_are_stored_as_binary():
    paths = [str(GRIB2), *map(str, NETCDF), str(NPY)]
    res = subprocess.run(
        ["git", "check-attr", "binary", "--", *paths],
        capture_output=True,
        text=True,
    )
    if res.returncode != 0:
        pytest.skip("not a git checkout")
    for line in res.stdout.splitlines():
        assert line.endswith(": binary: set"), line


def test_grib2_decodes_with_cfgrib():
    xr = pytest.importorskip("xarray")
    try:
        import cfgrib  # noqa: F401
    except Exception as exc:  # cfgrib raises RuntimeError when ecCodes is missing
        pytest.skip(f"cfgrib/ecCodes not available: {exc}")
    with xr.open_dataset(
        GRIB2, engine="cfgrib", backend_kwargs={"indexpath": ""}
    ) as ds:
        t2m = ds["t2m"]
        assert dict(t2m.sizes) == {"latitude": 361, "longitude": 720}
        assert 150.0 < float(t2m.min()) < float(t2m.max()) < 350.0


@pytest.mark.parametrize("path", NETCDF, ids=str)
def test_netcdf_opens_with_netcdf4(path):
    netCDF4 = pytest.importorskip("netCDF4")
    with netCDF4.Dataset(path) as ds:
        assert ds.file_format == "NETCDF4"
        assert ds.variables["TMP"][:].shape == (5, 5)
