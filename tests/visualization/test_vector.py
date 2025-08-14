import os


def test_cli_vector_quiver_npy_smoke(ensure_uv_stacks):
    try:
        import matplotlib  # noqa: F401
    except Exception as e:
        import pytest

        pytest.skip(f"Visualization deps missing: {e}")

    import subprocess, sys, tempfile

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
