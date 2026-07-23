# SPDX-License-Identifier: Apache-2.0
"""Tests for ``process reproject`` (issue: warp pre-rendered rasters).

The round-trip test is the acceptance criterion from the issue: a
synthetic polar-stereographic raster with a marker at a known
geographic location must land at the predicted pixel of the EPSG:4326
full-globe grid.
"""

import numpy as np
import pytest

rasterio = pytest.importorskip("rasterio")

from rasterio.crs import CRS  # noqa: E402
from rasterio.transform import from_bounds  # noqa: E402
from rasterio.warp import transform as crs_transform  # noqa: E402

from zyra.processing.raster_reproject import (  # noqa: E402
    FULL_GLOBE_BOUNDS,
    ReprojectError,
    reproject_raster,
)

# EPSG:3413 (NSIDC Sea Ice Polar Stereographic North) extent used for
# the synthetic source raster, in projected meters.
PS_BOUNDS = (-4_000_000.0, -4_000_000.0, 4_000_000.0, 4_000_000.0)
MARKER_LON, MARKER_LAT = 45.0, 80.0


def _write_polar_stereo_marker(path: str, size: int = 400) -> None:
    """Write an EPSG:3413 GeoTIFF with a bright marker at (45E, 80N)."""
    crs = CRS.from_epsg(3413)
    transform = from_bounds(*PS_BOUNDS, size, size)
    data = np.zeros((1, size, size), dtype=np.uint8)
    # Project the marker's lon/lat into EPSG:3413, then into pixel space.
    [x], [y] = crs_transform(CRS.from_epsg(4326), crs, [MARKER_LON], [MARKER_LAT])
    col, row = (~transform) * (x, y)
    row, col = int(row), int(col)
    data[0, row - 4 : row + 5, col - 4 : col + 5] = 255
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=size,
        height=size,
        count=1,
        dtype="uint8",
        crs=crs,
        transform=transform,
    ) as dst:
        dst.write(data)


def test_round_trip_polar_stereo_marker(tmp_path):
    src = str(tmp_path / "polar.tif")
    out = str(tmp_path / "equirect.tif")
    _write_polar_stereo_marker(src)

    width, height = 2048, 1024
    result = reproject_raster(src, out, width=width, height=height)
    assert result.crs == "EPSG:4326"
    assert (result.width, result.height) == (width, height)

    with rasterio.open(out) as ds:
        warped = ds.read(1)
    # Predicted pixel of (45E, 80N) on the full-globe grid.
    west, south, east, north = FULL_GLOBE_BOUNDS
    exp_col = int((MARKER_LON - west) / (east - west) * width)
    exp_row = int((north - MARKER_LAT) / (north - south) * height)
    window = warped[exp_row - 6 : exp_row + 7, exp_col - 6 : exp_col + 7]
    assert window.max() > 128, "marker did not land at the predicted pixel"
    # Outside the marker's latitude band the grid must stay dark. (Near
    # 80N a ~180 km marker legitimately smears across many columns —
    # meridians converge — so only the vertical placement is asserted
    # strictly.)
    far = warped.copy()
    far[exp_row - 30 : exp_row + 31, :] = 0
    assert far.max() == 0


def test_identity_reproject_preserves_content(tmp_path):
    src = str(tmp_path / "global.tif")
    out = str(tmp_path / "out.tif")
    width, height = 360, 180
    transform = from_bounds(*FULL_GLOBE_BOUNDS, width, height)
    gradient = np.linspace(0, 255, width, dtype=np.uint8)
    data = np.tile(gradient, (height, 1))[np.newaxis, :, :]
    with rasterio.open(
        src,
        "w",
        driver="GTiff",
        width=width,
        height=height,
        count=1,
        dtype="uint8",
        crs=CRS.from_epsg(4326),
        transform=transform,
    ) as dst:
        dst.write(data)

    reproject_raster(src, out, width=width, height=height, resampling="nearest")
    with rasterio.open(out) as ds:
        warped = ds.read(1)
    assert np.array_equal(warped, data[0])


def test_plain_png_requires_srs_and_bounds(tmp_path):
    # A bare PNG has no CRS: reprojecting it without --s-srs must fail
    # with a clear message, and with --s-srs but no --bounds likewise.
    png = str(tmp_path / "plain.png")
    from rasterio.io import MemoryFile

    data = np.zeros((1, 8, 8), dtype=np.uint8)
    with MemoryFile() as mem:
        with mem.open(driver="GTiff", width=8, height=8, count=1, dtype="uint8") as tmp:
            tmp.write(data)
        with mem.open() as tmp:
            import rasterio.shutil as rio_shutil

            rio_shutil.copy(tmp, png, driver="PNG")

    out = str(tmp_path / "out.tif")
    with pytest.raises(ReprojectError, match="no embedded CRS"):
        reproject_raster(png, out)
    with pytest.raises(ReprojectError, match="pass --bounds"):
        reproject_raster(png, out, s_srs="EPSG:3413")


def test_plain_png_with_srs_and_bounds_works(tmp_path):
    png = str(tmp_path / "disk.png")
    from rasterio.io import MemoryFile

    data = np.full((1, 64, 64), 200, dtype=np.uint8)
    with MemoryFile() as mem:
        with mem.open(
            driver="GTiff", width=64, height=64, count=1, dtype="uint8"
        ) as tmp:
            tmp.write(data)
        with mem.open() as tmp:
            import rasterio.shutil as rio_shutil

            rio_shutil.copy(tmp, png, driver="PNG")

    out = str(tmp_path / "out.png")
    result = reproject_raster(
        png,
        out,
        s_srs="EPSG:3413",
        bounds=PS_BOUNDS,
        width=256,
        height=128,
    )
    assert result.band_count == 1
    with rasterio.open(out) as ds:
        warped = ds.read(1)
    # The polar-stereo disk covers the north pole: content must appear
    # in the top (northern) half of the equirect grid.
    assert warped[:40, :].max() == 200


def test_invalid_args_rejected(tmp_path):
    with pytest.raises(ReprojectError, match="resampling"):
        reproject_raster("x.tif", "y.tif", resampling="cubic")
    with pytest.raises(ReprojectError, match="positive"):
        reproject_raster("x.tif", "y.tif", width=0, height=100)
    with pytest.raises(ReprojectError, match="dst-bounds"):
        reproject_raster("x.tif", "y.tif", t_srs="EPSG:3857")


def test_cli_reproject_end_to_end(tmp_path):
    import subprocess
    import sys

    src = str(tmp_path / "polar.tif")
    out = str(tmp_path / "cli_out.png")
    _write_polar_stereo_marker(src)
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "zyra.cli",
            "process",
            "reproject",
            "-i",
            src,
            "-o",
            out,
            "--width",
            "512",
            "--height",
            "256",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    with rasterio.open(out) as ds:
        assert (ds.width, ds.height) == (512, 256)
