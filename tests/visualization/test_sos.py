# SPDX-License-Identifier: Apache-2.0
"""Tests for the ``visualize sos`` (Science On a Sphere) subcommand."""

import os
import subprocess
import sys
import tempfile

import numpy as np
import pytest

# Skip Cartopy-heavy render tests unless explicitly enabled (mirrors test_managers).
_has_cartopy = False
try:  # pragma: no cover - import guard
    import cartopy  # noqa: F401

    _has_cartopy = True
except Exception:
    pass

_skip_cartopy_heavy = (not _has_cartopy) or os.environ.get(
    "DATAVIZHUB_RUN_CARTOPY_TESTS"
) != "1"
_cartopy_skip = pytest.mark.skipif(
    _skip_cartopy_heavy,
    reason="Cartopy-heavy tests require cartopy and opt-in (DATAVIZHUB_RUN_CARTOPY_TESTS=1)",
)


@pytest.mark.cli
def test_sos_help_exits_zero():
    proc = subprocess.run(
        [sys.executable, "-m", "zyra.cli", "visualize", "sos", "--help"],
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stderr.decode(errors="ignore")
    out = proc.stdout.decode(errors="ignore")
    assert "--vmin" in out and "--vmax" in out
    assert "--inputs" in out and "--output-dir" in out


def test_sos_requires_input_or_inputs():
    from types import SimpleNamespace

    from zyra.visualization.cli_sos import handle_sos

    ns = SimpleNamespace(inputs=None, input=None, output=None)
    with pytest.raises(SystemExit):
        handle_sos(ns)


def test_sos_requires_output_dir_for_batch():
    from types import SimpleNamespace

    from zyra.visualization.cli_sos import handle_sos

    ns = SimpleNamespace(inputs=["a.npy"], output_dir=None)
    with pytest.raises(SystemExit):
        handle_sos(ns)


def test_load_data_array_npy_roundtrip():
    from zyra.visualization.cli_utils import load_data_array

    arr = np.random.rand(8, 16).astype("float32")
    with tempfile.TemporaryDirectory() as td:
        npy = os.path.join(td, "a.npy")
        np.save(npy, arr)
        loaded = load_data_array(npy)
        assert np.allclose(loaded, arr)


def test_load_data_array_unsupported_extension():
    from zyra.visualization.cli_utils import load_data_array

    with pytest.raises(ValueError):
        load_data_array("/tmp/does_not_matter.txt")


def test_load_data_array_nc_requires_var():
    from zyra.visualization.cli_utils import load_data_array

    with pytest.raises(ValueError):
        load_data_array("/tmp/some.nc", var=None)


@_cartopy_skip
def test_sos_single_render_is_2to1(tmp_path):
    from zyra.visualization.cli_sos import handle_sos

    arr = np.linspace(0, 50, 32 * 64, dtype=float).reshape(32, 64)
    npy = tmp_path / "frame.npy"
    np.save(npy, arr)
    out = tmp_path / "frame.png"

    from types import SimpleNamespace

    ns = SimpleNamespace(
        inputs=None,
        input=str(npy),
        output=str(out),
        output_dir=None,
        var=None,
        basemap=None,
        extent=[-180, 180, -90, 90],
        width=512,
        height=256,
        dpi=96,
        cmap="YlOrBr",
        vmin=0.0,
        vmax=50.0,
        flip=False,
        xarray_engine=None,
    )
    rc = handle_sos(ns)
    assert rc == 0
    assert out.exists() and out.stat().st_size > 0

    from PIL import Image

    with Image.open(out) as im:
        w, h = im.size
    # Edge-to-edge full globe should be a 2:1 image.
    assert abs(w - 2 * h) <= 2, f"expected 2:1, got {w}x{h}"


@_cartopy_skip
def test_sos_batch_renders_all_frames(tmp_path):
    from types import SimpleNamespace

    from zyra.visualization.cli_sos import handle_sos

    inputs = []
    for i in range(3):
        arr = np.full((16, 32), float(i * 10), dtype=float)
        p = tmp_path / f"f{i}.npy"
        np.save(p, arr)
        inputs.append(str(p))
    outdir = tmp_path / "frames"

    ns = SimpleNamespace(
        inputs=inputs,
        input=None,
        output=None,
        output_dir=str(outdir),
        var=None,
        basemap=None,
        extent=[-180, 180, -90, 90],
        width=256,
        height=128,
        dpi=96,
        cmap="YlOrBr",
        vmin=0.0,
        vmax=50.0,
        flip=False,
        xarray_engine=None,
    )
    rc = handle_sos(ns)
    assert rc == 0
    produced = sorted(outdir.glob("*.png"))
    assert len(produced) == 3
    assert all(p.stat().st_size > 0 for p in produced)


@_cartopy_skip
def test_sos_fixed_color_scale_is_consistent_across_frames(tmp_path):
    """A fixed vmin/vmax must map equal values to identical colors across frames.

    Without fixed scaling, two arrays with different ranges self-scale and the
    same physical value renders with different colors (the flicker source).
    """
    from zyra.visualization.plot_manager import PlotManager

    # Two frames whose ranges differ; both contain the constant value 25.
    frame_a = np.full((32, 64), 25.0)
    frame_b = np.full((32, 64), 25.0)

    out_a = tmp_path / "a.png"
    out_b = tmp_path / "b.png"

    for arr, out in ((frame_a, out_a), (frame_b, out_b)):
        pm = PlotManager(image_extent=[-180, 180, -90, 90])
        pm.sos_plot_data(
            arr,
            custom_cmap="YlOrBr",
            output_path=str(out),
            width=256,
            height=128,
            vmin=0.0,
            vmax=50.0,
        )

    from PIL import Image

    a = np.asarray(Image.open(out_a).convert("RGB"))
    b = np.asarray(Image.open(out_b).convert("RGB"))
    assert a.shape == b.shape
    # Identical inputs + identical fixed scale -> pixel-identical output.
    assert np.array_equal(a, b)
