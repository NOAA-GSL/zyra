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


def test_sos_single_render_failure_exits_nonzero(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from zyra.visualization import cli_sos

    # Simulate a render failure (PlotManager returns None -> sos_plot_data None).
    monkeypatch.setattr(cli_sos, "_render_one", lambda ns, src, dest: None)
    ns = SimpleNamespace(inputs=None, input="a.npy", output=str(tmp_path / "o.png"))
    with pytest.raises(SystemExit):
        cli_sos.handle_sos(ns)


def test_sos_batch_render_failure_exits_nonzero(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from zyra.visualization import cli_sos

    monkeypatch.setattr(cli_sos, "_render_one", lambda ns, src, dest: None)
    ns = SimpleNamespace(
        inputs=["a.npy", "b.npy"], input=None, output_dir=str(tmp_path / "frames")
    )
    with pytest.raises(SystemExit):
        cli_sos.handle_sos(ns)


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
    from PIL import Image

    from zyra.visualization.plot_manager import PlotManager

    # Two frames that share a large constant mid-value (25) but have different
    # overall ranges: A spans [0, 25] and B spans [25, 50]. A single corner cell
    # (far from the image center) sets each frame's min/max so that per-frame
    # self-scaling would map the shared value 25 to *different* colors.
    frame_a = np.full((32, 64), 25.0)
    frame_a[0, 0] = 0.0  # range [0, 25] -> 25 is the max
    frame_b = np.full((32, 64), 25.0)
    frame_b[0, 0] = 50.0  # range [25, 50] -> 25 is the min

    def _render(arr, name, **kw):
        pm = PlotManager(image_extent=[-180, 180, -90, 90])
        pm.sos_plot_data(
            arr,
            custom_cmap="YlOrBr",
            output_path=str(tmp_path / name),
            width=256,
            height=128,
            **kw,
        )
        return np.asarray(Image.open(tmp_path / name).convert("RGB"))

    def _center(img):
        # Sample the image center (lon=0, lat=0), far from the corner cell, so
        # the region is uniformly the shared value 25 in both frames.
        h, w = img.shape[:2]
        return img[int(h * 0.4) : int(h * 0.6), int(w * 0.4) : int(w * 0.6)]

    # Fixed scale: the shared value 25 maps to the same color in both frames.
    a_fixed = _center(_render(frame_a, "a_fixed.png", vmin=0.0, vmax=50.0))
    b_fixed = _center(_render(frame_b, "b_fixed.png", vmin=0.0, vmax=50.0))
    assert np.array_equal(a_fixed, b_fixed)

    # Teeth: without fixed scale, per-frame self-scaling maps 25 differently,
    # so the same center region renders with different colors. This guards
    # against the test passing if vmin/vmax were ignored.
    a_self = _center(_render(frame_a, "a_self.png"))
    b_self = _center(_render(frame_b, "b_self.png"))
    assert not np.array_equal(a_self, b_self)
