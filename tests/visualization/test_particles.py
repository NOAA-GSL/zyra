import json
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


def test_cli_particles_npy_smoke(ensure_uv_stacks):
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
            "datavizhub.cli",
            "animate",
            "--mode",
            "particles",
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
            "--particles",
            "50",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        assert proc.returncode == 0, proc.stderr
        assert os.path.exists(manifest)
        data = json.loads(open(manifest).read())
        assert data["count"] >= 1
        # At least frame_0000.png should exist
        path = os.path.join(outdir, "frame_0000.png")
        assert os.path.exists(path)
        assert os.path.getsize(path) > 0
