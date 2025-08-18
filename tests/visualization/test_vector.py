import os

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


def test_cli_vector_quiver_npy_smoke(ensure_uv_stacks):
    try:
        import matplotlib  # noqa: F401
    except Exception as e:
        import pytest

        pytest.skip(f"Visualization deps missing: {e}")

    import subprocess
    import sys
    import tempfile

    up, vp = ensure_uv_stacks
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "vec.png")
        cmd = [
            sys.executable,
            "-m",
            "datavizhub.cli",
            "vector",
            "--u",
            up,
            "--v",
            vp,
            "--output",
            out,
            "--width",
            "320",
            "--height",
            "160",
            "--density",
            "0.3",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        assert proc.returncode == 0, proc.stderr
        assert os.path.exists(out)
        assert os.path.getsize(out) > 0
