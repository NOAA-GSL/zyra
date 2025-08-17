import os
import tempfile

import numpy as np
import pytest

from importlib.resources import files, as_file

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


def _get_basemap_path():
    res = files("datavizhub.assets").joinpath("images/earth_vegetation.jpg")
    with as_file(res) as p:
        return str(p)


def test_heatmap_manager_renders_png():
    try:
        from datavizhub.visualization import HeatmapManager
    except Exception as e:
        # Skip if optional visualization deps are missing
        import pytest

        pytest.skip(f"Visualization deps missing: {e}")

    data = np.linspace(0, 1, 64 * 128, dtype=float).reshape(64, 128)
    hm = HeatmapManager(basemap=_get_basemap_path())

    fig = hm.render(data, width=256, height=128, dpi=96)
    assert fig is not None

    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "heatmap.png")
        path = hm.save(out)
        assert path and os.path.exists(path)
        assert os.path.getsize(path) > 0


def test_contour_manager_renders_png():
    try:
        from datavizhub.visualization import ContourManager
    except Exception as e:
        import pytest

        pytest.skip(f"Visualization deps missing: {e}")

    x = np.linspace(-3, 3, 100)
    y = np.linspace(-3, 3, 50)
    X, Y = np.meshgrid(x, y)
    Z = np.exp(-(X**2 + Y**2))

    cm = ContourManager(basemap=_get_basemap_path(), filled=True)
    fig = cm.render(Z, width=256, height=128, dpi=96, levels=8)
    assert fig is not None

    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "contour.png")
        path = cm.save(out)
        assert path and os.path.exists(path)
        assert os.path.getsize(path) > 0


def test_cli_heatmap_smoke():
    # Smoke run CLI with a small .npy array
    try:
        import cartopy  # noqa: F401
        import matplotlib  # noqa: F401
    except Exception as e:
        import pytest

        pytest.skip(f"Visualization deps missing: {e}")

    arr = np.random.rand(16, 32).astype("float32")
    with tempfile.TemporaryDirectory() as td:
        npy = os.path.join(td, "a.npy")
        out = os.path.join(td, "out.png")
        np.save(npy, arr)

        import subprocess, sys

        cmd = [
            sys.executable,
            "-m",
            "datavizhub.visualization.cli",
            "heatmap",
            "--input",
            npy,
            "--output",
            out,
            "--width",
            "256",
            "--height",
            "128",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        assert proc.returncode == 0, proc.stderr
        assert os.path.exists(out)
        assert os.path.getsize(out) > 0
