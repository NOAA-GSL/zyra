# SPDX-License-Identifier: Apache-2.0
"""GeoTIFF input for heatmap/contour (issue: pipelines needed a shim).

`process reproject` emits GeoTIFF, but the raster visualizers only read
.nc/.npy — bridging required an out-of-band script, which CLI-stage-
allowlisted runners (e.g. TerraViz workflows) cannot express. The
loader now reads GeoTIFF band data directly with nodata mapped to NaN.
"""

from __future__ import annotations

import os

import numpy as np
import pytest

rasterio = pytest.importorskip("rasterio")

from rasterio.crs import CRS  # noqa: E402
from rasterio.transform import from_bounds  # noqa: E402

from zyra.visualization.cli_utils import (  # noqa: E402
    load_data_array,
    load_geotiff_array,
)


def _write_tif(path, data, *, nodata=None, count=1):
    height, width = data.shape[-2], data.shape[-1]
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=width,
        height=height,
        count=count,
        dtype=str(data.dtype),
        crs=CRS.from_epsg(4326),
        transform=from_bounds(-180, -90, 180, 90, width, height),
        nodata=nodata,
    ) as dst:
        if data.ndim == 2:
            dst.write(data, 1)
        else:
            dst.write(data)


def test_load_geotiff_band1_default(tmp_path):
    tif = str(tmp_path / "x.tif")
    data = np.arange(12, dtype="float32").reshape(3, 4)
    _write_tif(tif, data)
    out = load_geotiff_array(tif)
    assert out.shape == (3, 4)
    assert float(out[2, 3]) == 11.0


def test_load_geotiff_nodata_maps_to_nan(tmp_path):
    tif = str(tmp_path / "nd.tif")
    data = np.full((4, 4), 7.0, dtype="float32")
    data[0, 0] = -999.0
    _write_tif(tif, data, nodata=-999.0)
    out = load_geotiff_array(tif)
    assert np.isnan(out[0, 0])
    assert float(out[1, 1]) == 7.0
    # Only the nodata cell is masked.
    assert int(np.isnan(out).sum()) == 1


def test_load_geotiff_integer_nodata(tmp_path):
    tif = str(tmp_path / "int.tif")
    data = np.full((3, 3), 5, dtype="uint8")
    data[1, 1] = 0
    _write_tif(tif, data, nodata=0)
    out = load_geotiff_array(tif)
    # Output is float so nodata can be NaN even for integer sources.
    assert out.dtype == np.float32
    assert np.isnan(out[1, 1])
    assert float(out[0, 0]) == 5.0


def test_load_geotiff_band_selection(tmp_path):
    tif = str(tmp_path / "multi.tif")
    data = np.stack(
        [np.full((2, 2), 1.0, dtype="float32"), np.full((2, 2), 2.0, dtype="float32")]
    )
    _write_tif(tif, data, count=2)
    assert float(load_geotiff_array(tif, band=2)[0, 0]) == 2.0
    # Default stays band 1.
    assert float(load_geotiff_array(tif)[0, 0]) == 1.0


def test_load_geotiff_band_out_of_range(tmp_path):
    tif = str(tmp_path / "one.tif")
    _write_tif(tif, np.zeros((2, 2), dtype="float32"))
    with pytest.raises(ValueError, match="out of range"):
        load_geotiff_array(tif, band=3)
    with pytest.raises(ValueError, match="out of range"):
        load_geotiff_array(tif, band=0)


def test_load_data_array_routes_tif(tmp_path):
    tif = str(tmp_path / "route.tif")
    _write_tif(tif, np.full((2, 2), 3.0, dtype="float32"))
    out = load_data_array(tif)
    assert float(out[0, 0]) == 3.0


def test_load_data_array_unsupported_suffix_message(tmp_path):
    with pytest.raises(ValueError, match=r"\.tif"):
        load_data_array(str(tmp_path / "x.grib2"))


def test_cli_parser_accepts_band():
    # Assert against the PUBLIC registrar (package __init__), which the
    # Domain API parser and manifest service consume. It delegates to
    # cli_register — a duplicate definition previously lived here and
    # drifted from the real CLI surface.
    import argparse

    import zyra.visualization as vpkg

    parser = argparse.ArgumentParser()
    vpkg.register_cli(parser.add_subparsers(dest="cmd"))
    ns = parser.parse_args(
        ["heatmap", "--input", "x.tif", "--output", "o.png", "--band", "2"]
    )
    assert ns.band == 2
    ns = parser.parse_args(["contour", "--input", "x.tif", "--output", "o.png"])
    assert ns.band == 1


def test_public_and_module_registrars_agree():
    # Guard against the registrar split reappearing: both entry points
    # must expose identical option sets for heatmap/contour.
    import argparse

    import zyra.visualization as vpkg
    from zyra.visualization import cli_register

    def options(fn, cmd):
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="cmd")
        fn(sub)
        return {a for act in sub.choices[cmd]._actions for a in act.option_strings}

    for cmd in ("heatmap", "contour"):
        assert options(vpkg.register_cli, cmd) == options(
            cli_register.register_cli, cmd
        )


def test_cli_band_out_of_range_exits_2(tmp_path):
    # Input/validation errors are a clean logged error with exit code 2,
    # not a traceback with exit 1.
    import subprocess
    import sys

    tif = str(tmp_path / "one.tif")
    _write_tif(tif, np.zeros((2, 2), dtype="float32"))
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "zyra.cli",
            "visualize",
            "heatmap",
            "--input",
            tif,
            "--output",
            str(tmp_path / "o.png"),
            "--band",
            "99",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 2
    assert "out of range" in proc.stderr
    assert "Traceback" not in proc.stderr


# Cartopy-heavy render test: opt-in via DATAVIZHUB_RUN_CARTOPY_TESTS=1
# (repo convention). Heavy imports stay inside the test so collection
# succeeds in environments without matplotlib/cartopy.
_has_cartopy = False
try:  # pragma: no cover - import guard
    import cartopy  # noqa: F401

    _has_cartopy = True
except Exception:
    pass

_skip_cartopy_heavy = (not _has_cartopy) or os.environ.get(
    "DATAVIZHUB_RUN_CARTOPY_TESTS"
) != "1"


@pytest.mark.skipif(
    _skip_cartopy_heavy,
    reason="Cartopy-heavy tests require cartopy and opt-in (DATAVIZHUB_RUN_CARTOPY_TESTS=1)",
)
def test_heatmap_renders_geotiff_with_transparent_nodata(tmp_path):
    import matplotlib

    matplotlib.use("Agg")

    from zyra.visualization.heatmap_manager import HeatmapManager

    tif = str(tmp_path / "render.tif")
    data = np.full((20, 40), 30.0, dtype="float32")
    data[:, :20] = -999.0
    _write_tif(tif, data, nodata=-999.0)

    mgr = HeatmapManager(extent=[-180, 180, -90, 90])
    # Fixed scale keeps the constant data value mid-colormap (strongly
    # colored) instead of normalizing to the palette's pale bottom end.
    fig = mgr.render(input_path=tif, cmap="turbo", vmin=0, vmax=60)
    assert fig is not None
    out = str(tmp_path / "o.png")
    mgr.save(out)

    from PIL import Image

    img = np.asarray(Image.open(out).convert("RGB")).astype(int)
    # NaN cells are not painted by imshow: the nodata (left) half shows
    # the neutral axes background while the data (right) half carries
    # the colormap color — the two halves must differ clearly.
    h, w = img.shape[:2]
    left = img[h // 2, w // 4]
    right = img[h // 2, (3 * w) // 4]
    assert (
        abs(int(left.sum()) - int(right.sum())) > 60
    ), f"nodata half was painted with data color: left={left}, right={right}"
    # Background is neutral (grayscale-ish), data color is not.
    assert max(left) - min(left) < 30, f"nodata pixel not background-like: {left}"


@pytest.mark.skipif(
    _skip_cartopy_heavy,
    reason="Cartopy-heavy tests require cartopy and opt-in (DATAVIZHUB_RUN_CARTOPY_TESTS=1)",
)
def test_render_band_zero_surfaces_range_error(tmp_path):
    # Regression: band=0 must reach the loader's range check, not be
    # treated as falsy and silently replaced with band 1.
    import matplotlib

    matplotlib.use("Agg")

    from zyra.visualization.heatmap_manager import HeatmapManager

    tif = str(tmp_path / "z.tif")
    _write_tif(tif, np.zeros((2, 2), dtype="float32"))
    with pytest.raises(ValueError, match="out of range"):
        HeatmapManager(extent=[-180, 180, -90, 90]).render(input_path=tif, band=0)


def test_heatmap_batch_does_not_require_single_input():
    # --inputs/--output-dir is a documented batch mode; an argparse-level
    # required=True on --input made it unreachable (contour never had it).
    import argparse

    import zyra.visualization as vpkg

    parser = argparse.ArgumentParser()
    vpkg.register_cli(parser.add_subparsers(dest="cmd"))
    ns = parser.parse_args(
        ["heatmap", "--inputs", "a.tif", "b.tif", "--output-dir", "out"]
    )
    assert ns.inputs == ["a.tif", "b.tif"]
    assert ns.input is None


def test_heatmap_without_any_input_exits_2(tmp_path):
    # Dropping required=True must still reject "neither form given",
    # with a clear message rather than a traceback.
    import subprocess
    import sys

    proc = subprocess.run(
        [sys.executable, "-m", "zyra.cli", "visualize", "heatmap", "--output", "o.png"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 2
    assert "--input is required" in proc.stderr
    assert "Traceback" not in proc.stderr
