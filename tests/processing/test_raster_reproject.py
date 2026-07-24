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


def test_auto_dst_bounds_crops_to_source_footprint(tmp_path):
    src = str(tmp_path / "polar.tif")
    out = str(tmp_path / "cropped.tif")
    _write_polar_stereo_marker(src)

    result = reproject_raster(src, out, dst_bounds="auto", width=1024)
    from rasterio.warp import transform_bounds

    expected = transform_bounds(CRS.from_epsg(3413), CRS.from_epsg(4326), *PS_BOUNDS)
    with rasterio.open(out) as ds:
        got = ds.bounds
        assert ds.width == 1024
        # Height follows the extent's aspect ratio and is even.
        lon_span = expected[2] - expected[0]
        lat_span = expected[3] - expected[1]
        assert ds.height == max(2, int(round(1024 * lat_span / lon_span / 2)) * 2)
        assert ds.height == result.height
    for got_v, exp_v in zip(got, expected):
        assert got_v == pytest.approx(exp_v, abs=1e-6)


def test_auto_dst_bounds_with_explicit_bounds(tmp_path):
    # Plain image + --s-srs/--bounds + auto: the target extent derives
    # from the supplied source bounds.
    png = str(tmp_path / "disk.png")
    from rasterio.io import MemoryFile

    data = np.full((1, 32, 32), 128, dtype=np.uint8)
    with MemoryFile() as mem:
        with mem.open(
            driver="GTiff", width=32, height=32, count=1, dtype="uint8"
        ) as tmp:
            tmp.write(data)
        with mem.open() as tmp:
            import rasterio.shutil as rio_shutil

            rio_shutil.copy(tmp, png, driver="PNG")

    out = str(tmp_path / "o.tif")
    result = reproject_raster(
        png, out, s_srs="EPSG:3413", bounds=PS_BOUNDS, dst_bounds="auto", width=512
    )
    from rasterio.warp import transform_bounds

    expected = transform_bounds(CRS.from_epsg(3413), CRS.from_epsg(4326), *PS_BOUNDS)
    with rasterio.open(out) as ds:
        assert ds.bounds.left == pytest.approx(expected[0], abs=1e-6)
        assert ds.bounds.top == pytest.approx(expected[3], abs=1e-6)
    assert result.width == 512


def _write_small_4326(path: str, *, value=9, dtype="uint8", nodata=None) -> None:
    """A 10x10-degree source at (0..10E, 0..10N) for padded-warp tests."""
    transform = from_bounds(0.0, 0.0, 10.0, 10.0, 64, 64)
    data = np.full((1, 64, 64), value, dtype=dtype)
    profile = dict(
        driver="GTiff",
        width=64,
        height=64,
        count=1,
        dtype=dtype,
        crs=CRS.from_epsg(4326),
        transform=transform,
    )
    if nodata is not None:
        profile["nodata"] = nodata
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data)


PADDED = (-5.0, -5.0, 15.0, 15.0)  # source occupies the middle quarter


def test_dst_nodata_fills_outside_footprint(tmp_path):
    src = str(tmp_path / "small.tif")
    out = str(tmp_path / "o.tif")
    _write_small_4326(src)
    reproject_raster(src, out, dst_bounds=PADDED, width=200, height=200, dst_nodata=255)
    with rasterio.open(out) as ds:
        assert ds.nodata == 255
        warped = ds.read(1)
    assert warped[0, 0] == 255  # padded corner: outside source footprint
    assert warped[100, 100] != 255  # center: covered by source


def test_dst_nodata_nan_for_float_source(tmp_path):
    src = str(tmp_path / "small_f32.tif")
    out = str(tmp_path / "o.tif")
    _write_small_4326(src, value=7.5, dtype="float32")
    reproject_raster(
        src, out, dst_bounds=PADDED, width=200, height=200, dst_nodata=float("nan")
    )
    with rasterio.open(out) as ds:
        # The nodata tag must be written, not just the fill applied.
        assert ds.nodata is not None and np.isnan(ds.nodata)
        warped = ds.read(1)
    assert np.isnan(warped[0, 0])
    assert np.nanmax(warped) == pytest.approx(7.5)


def test_source_nodata_propagates_by_default(tmp_path):
    src = str(tmp_path / "small_nd.tif")
    out = str(tmp_path / "o.tif")
    _write_small_4326(src, nodata=200)
    reproject_raster(src, out, dst_bounds=PADDED, width=200, height=200)
    with rasterio.open(out) as ds:
        assert ds.nodata == 200
        assert ds.read(1)[0, 0] == 200


def test_dst_nodata_dtype_mismatch_rejected(tmp_path):
    src = str(tmp_path / "polar.tif")
    _write_polar_stereo_marker(src)
    with pytest.raises(ReprojectError, match="does not fit"):
        reproject_raster(
            src, str(tmp_path / "o.tif"), dst_nodata=float("nan"), width=64
        )
    # Out-of-range integers must be rejected, not silently wrapped
    # (np.full would turn -1 into 255 for uint8).
    with pytest.raises(ReprojectError, match="out of range"):
        reproject_raster(src, str(tmp_path / "o.tif"), dst_nodata=-1, width=64)
    with pytest.raises(ReprojectError, match="out of range"):
        reproject_raster(src, str(tmp_path / "o.tif"), dst_nodata=999, width=64)


def test_bad_dst_bounds_string_rejected():
    with pytest.raises(ReprojectError, match="'auto'"):
        reproject_raster("x.tif", "y.tif", dst_bounds="everything")


def test_invalid_args_rejected(tmp_path):
    with pytest.raises(ReprojectError, match="resampling"):
        reproject_raster("x.tif", "y.tif", resampling="cubic")
    with pytest.raises(ReprojectError, match="positive"):
        reproject_raster("x.tif", "y.tif", width=0, height=100)
    with pytest.raises(ReprojectError, match="dst-bounds"):
        reproject_raster("x.tif", "y.tif", t_srs="EPSG:3857")


def test_cli_bounds_wrong_length_is_clear_error(tmp_path):
    import subprocess
    import sys

    src = str(tmp_path / "polar.tif")
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
            str(tmp_path / "o.tif"),
            "--bounds",
            "1",
            "2",
            "3",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 2
    assert "exactly 4 values" in proc.stderr


def test_cli_repeated_bounds_flags_accumulate(tmp_path):
    # The Domain API runner expands list args as repeated flags
    # (--bounds v1 --bounds v2 ...); action="extend" must accumulate
    # them into one 4-value extent.
    import subprocess
    import sys

    src = str(tmp_path / "polar.tif")
    out = str(tmp_path / "o.tif")
    _write_polar_stereo_marker(src)
    argv = [
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
        "128",
        "--height",
        "64",
    ]
    for v in PS_BOUNDS:
        argv += ["--bounds", str(v)]
    proc = subprocess.run(argv, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    with rasterio.open(out) as ds:
        assert (ds.width, ds.height) == (128, 64)


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


# ---- Batch mode (--inputs / --output-dir) ---------------------------------
# reproject was the only stage in the raster pipeline without a batch
# form, which made it the binding constraint on orchestrated runs that
# warp one frame per forecast hour under a fixed stage budget.


def _run_cli(argv):
    import subprocess
    import sys

    return subprocess.run(
        [sys.executable, "-m", "zyra.cli", "process", "reproject", *argv],
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_batch_writes_one_output_per_input(tmp_path):
    a = tmp_path / "a.tif"
    b = tmp_path / "b.tif"
    outdir = tmp_path / "out"
    _write_polar_stereo_marker(str(a))
    _write_polar_stereo_marker(str(b))

    proc = _run_cli(
        [
            "--inputs",
            str(a),
            str(b),
            "--output-dir",
            str(outdir),
            "--width",
            "128",
            "--height",
            "64",
        ]
    )
    assert proc.returncode == 0, proc.stderr
    for name in ("a.tif", "b.tif"):
        with rasterio.open(str(outdir / name)) as ds:
            assert (ds.width, ds.height) == (128, 64)
            assert ds.crs.to_string() == "EPSG:4326"

    # The same {"outputs": [...]} summary the other batch commands print,
    # in input order so downstream frame globs stay ordered.
    import json

    summary = json.loads(proc.stdout.strip().splitlines()[-1])
    assert [p.rsplit("/", 1)[-1] for p in summary["outputs"]] == ["a.tif", "b.tif"]


def test_cli_batch_preserves_source_suffix(tmp_path):
    # The driver comes from the output extension, so a .png input must
    # not silently become a GeoTIFF (and vice versa).
    src = tmp_path / "frame.png"
    _write_polar_stereo_marker(str(tmp_path / "seed.tif"))
    proc = _run_cli(
        [
            "-i",
            str(tmp_path / "seed.tif"),
            "-o",
            str(src),
            "--width",
            "64",
            "--height",
            "32",
        ]
    )
    assert proc.returncode == 0, proc.stderr

    outdir = tmp_path / "out"
    proc = _run_cli(
        [
            "--inputs",
            str(src),
            "--output-dir",
            str(outdir),
            "--s-srs",
            "EPSG:4326",
            "--bounds",
            "-180",
            "-90",
            "180",
            "90",
            "--width",
            "64",
            "--height",
            "32",
        ]
    )
    assert proc.returncode == 0, proc.stderr
    with rasterio.open(str(outdir / "frame.png")) as ds:
        assert ds.driver == "PNG"


def test_cli_batch_dst_bounds_auto_crops_each_input(tmp_path):
    # 'auto' derives bounds per input, so a batch of differently-placed
    # rasters each crops to its own footprint rather than sharing one.
    from rasterio.transform import from_bounds as _fb

    def _write(path, bounds):
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            width=32,
            height=32,
            count=1,
            dtype="uint8",
            crs=CRS.from_epsg(4326),
            transform=_fb(*bounds, 32, 32),
        ) as dst:
            dst.write(np.full((1, 32, 32), 7, dtype="uint8"))

    west = tmp_path / "west.tif"
    east = tmp_path / "east.tif"
    _write(str(west), (-120.0, 10.0, -100.0, 30.0))
    _write(str(east), (100.0, -30.0, 120.0, -10.0))

    outdir = tmp_path / "out"
    proc = _run_cli(
        [
            "--inputs",
            str(west),
            str(east),
            "--output-dir",
            str(outdir),
            "--dst-bounds",
            "auto",
            "--width",
            "64",
        ]
    )
    assert proc.returncode == 0, proc.stderr
    with rasterio.open(str(outdir / "west.tif")) as ds:
        assert ds.bounds.left == pytest.approx(-120.0, abs=0.5)
    with rasterio.open(str(outdir / "east.tif")) as ds:
        assert ds.bounds.left == pytest.approx(100.0, abs=0.5)


def test_cli_batch_repeated_inputs_flags_accumulate(tmp_path):
    # The Domain API runner expands lists as repeated flags; plain
    # nargs="+" would keep only the last one and silently drop frames.
    a = tmp_path / "a.tif"
    b = tmp_path / "b.tif"
    outdir = tmp_path / "out"
    _write_polar_stereo_marker(str(a))
    _write_polar_stereo_marker(str(b))
    proc = _run_cli(
        [
            "--inputs",
            str(a),
            "--inputs",
            str(b),
            "--output-dir",
            str(outdir),
            "--width",
            "64",
            "--height",
            "32",
        ]
    )
    assert proc.returncode == 0, proc.stderr
    assert (outdir / "a.tif").exists()
    assert (outdir / "b.tif").exists()


def test_cli_batch_argument_errors(tmp_path):
    src = tmp_path / "a.tif"
    _write_polar_stereo_marker(str(src))

    proc = _run_cli(["--inputs", str(src)])
    assert proc.returncode == 2
    assert "--output-dir is required" in proc.stderr

    proc = _run_cli(
        ["--inputs", str(src), "-i", str(src), "--output-dir", str(tmp_path / "o")]
    )
    assert proc.returncode == 2
    assert "cannot be combined" in proc.stderr

    # Dropping required=True must still reject "neither form given".
    proc = _run_cli(["-o", str(tmp_path / "o.tif")])
    assert proc.returncode == 2
    assert "--input is required" in proc.stderr
    assert "Traceback" not in proc.stderr

    proc = _run_cli(["-i", str(src)])
    assert proc.returncode == 2
    assert "--output is required" in proc.stderr


def test_cli_batch_rejects_colliding_and_in_place_outputs(tmp_path):
    # Two inputs with the same basename would silently overwrite each
    # other — losing a frame without a word. So would an --output-dir
    # that resolves to the inputs' own directory.
    d1 = tmp_path / "d1"
    d2 = tmp_path / "d2"
    d1.mkdir()
    d2.mkdir()
    _write_polar_stereo_marker(str(d1 / "f.tif"))
    _write_polar_stereo_marker(str(d2 / "f.tif"))
    proc = _run_cli(
        [
            "--inputs",
            str(d1 / "f.tif"),
            str(d2 / "f.tif"),
            "--output-dir",
            str(tmp_path / "out"),
        ]
    )
    assert proc.returncode == 2
    assert "share a filename" in proc.stderr
    assert not (tmp_path / "out").exists(), "collision must be caught before any warp"

    proc = _run_cli(["--inputs", str(d1 / "f.tif"), "--output-dir", str(d1)])
    assert proc.returncode == 2
    assert "would overwrite input" in proc.stderr


def test_api_schema_accepts_batch_args():
    from zyra.api.schemas.domain_args import ProcessReprojectArgs

    m = ProcessReprojectArgs(inputs=["a.tif", "b.tif"], output_dir="out")
    assert m.inputs == ["a.tif", "b.tif"]
    assert m.input is None and m.output is None
    # Single form still validates.
    assert ProcessReprojectArgs(input="a.tif", output="b.tif").output == "b.tif"
