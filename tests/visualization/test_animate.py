import json
import os
import tempfile

import numpy as np
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


def test_cli_animate_heatmap_npy():
    try:
        import matplotlib  # noqa: F401
    except Exception as e:
        import pytest

        pytest.skip(f"Visualization deps missing: {e}")

    import subprocess
    import sys

    t, ny, nx = 3, 16, 32
    stack = np.random.rand(t, ny, nx).astype("float32")
    with tempfile.TemporaryDirectory() as td:
        npy = os.path.join(td, "stack.npy")
        outdir = os.path.join(td, "frames")
        manifest = os.path.join(td, "manifest.json")
        np.save(npy, stack)

        # Create a timestamps CSV of 3 lines
        ts_csv = os.path.join(td, "ts.csv")
        with open(ts_csv, "w", encoding="utf-8") as f:
            f.write("t0\n t1\n t2\n")

        cmd = [
            sys.executable,
            "-m",
            "zyra.cli",
            "animate",
            "--mode",
            "heatmap",
            "--input",
            npy,
            "--output-dir",
            outdir,
            "--manifest",
            manifest,
            "--colorbar",
            "--label",
            "Demo",
            "--units",
            "X",
            "--show-timestamp",
            "--timestamps-csv",
            ts_csv,
            "--width",
            "320",
            "--height",
            "160",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        assert proc.returncode == 0, proc.stderr
        # Check manifest and frames while temp dir is alive
        assert os.path.exists(manifest)
        data = json.loads(open(manifest).read())
        assert data["count"] == t
        for i in range(t):
            path = os.path.join(outdir, f"frame_{i:04d}.png")
            assert os.path.exists(path)
            assert os.path.getsize(path) > 0


def test_cli_animate_vector_npy(ensure_uv_stacks):
    try:
        import matplotlib  # noqa: F401
    except Exception as e:
        import pytest

        pytest.skip(f"Visualization deps missing: {e}")

    import subprocess
    import sys

    up, vp = ensure_uv_stacks
    with tempfile.TemporaryDirectory() as td:
        outdir = os.path.join(td, "frames")
        manifest = os.path.join(td, "manifest.json")

        cmd = [
            sys.executable,
            "-m",
            "zyra.cli",
            "animate",
            "--mode",
            "vector",
            "--u",
            up,
            "--v",
            vp,
            "--output-dir",
            outdir,
            "--manifest",
            manifest,
            "--width",
            "320",
            "--height",
            "160",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        assert proc.returncode == 0, proc.stderr
        # Check manifest and one frame exists
        assert os.path.exists(manifest)
        data = json.loads(open(manifest).read())
        assert data["count"] >= 1
        path = os.path.join(outdir, "frame_0000.png")
        assert os.path.exists(path)
        assert os.path.getsize(path) > 0
