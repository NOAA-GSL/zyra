import os
import tempfile
from pathlib import Path

import numpy as np

from ..helpers import project_root


def test_interactive_folium_heatmap_html():
    try:
        import folium  # noqa: F401
    except Exception as e:
        import pytest

        pytest.skip(f"Optional interactive deps missing: {e}")

    import subprocess
    import sys

    arr = np.random.rand(10, 20).astype("float32")
    with tempfile.TemporaryDirectory() as td:
        npy = os.path.join(td, "arr.npy")
        out = os.path.join(td, "interactive.html")
        np.save(npy, arr)
        cmd = [
            sys.executable,
            "-m",
            "zyra.cli",
            "interactive",
            "--input",
            npy,
            "--output",
            out,
            "--engine",
            "folium",
            "--mode",
            "heatmap",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        assert proc.returncode == 0, proc.stderr
        assert os.path.exists(out)
        # Basic HTML structure
        text = Path(out).read_text(encoding="utf-8")[:200].lower()
        assert "<html" in text


def test_interactive_plotly_heatmap_html():
    try:
        import plotly  # noqa: F401
    except Exception as e:
        import pytest

        pytest.skip(f"Optional interactive deps missing: {e}")

    import subprocess
    import sys

    arr = np.random.rand(6, 12).astype("float32")
    with tempfile.TemporaryDirectory() as td:
        npy = os.path.join(td, "arr.npy")
        out = os.path.join(td, "interactive_plotly.html")
        np.save(npy, arr)
        cmd = [
            sys.executable,
            "-m",
            "zyra.cli",
            "interactive",
            "--input",
            npy,
            "--output",
            out,
            "--engine",
            "plotly",
            "--mode",
            "heatmap",
            "--width",
            "400",
            "--height",
            "300",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        assert proc.returncode == 0, proc.stderr
        assert os.path.exists(out)
        text = Path(out).read_text(encoding="utf-8")[:200].lower()
        assert "<html" in text


def test_interactive_folium_points_html():
    try:
        import folium  # noqa: F401
    except Exception as e:
        import pytest

        pytest.skip(f"Optional interactive deps missing: {e}")

    import os
    import subprocess
    import sys
    import tempfile

    # Use provided samples/points.csv
    repo_root = project_root(Path(__file__))
    points_csv = repo_root / "samples" / "points.csv"
    if not points_csv.exists():
        import pytest

        pytest.skip("samples/points.csv not found")

    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "points.html")
        cmd = [
            sys.executable,
            "-m",
            "zyra.cli",
            "interactive",
            "--input",
            str(points_csv),
            "--output",
            out,
            "--engine",
            "folium",
            "--mode",
            "points",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        assert proc.returncode == 0, proc.stderr
        assert os.path.exists(out)
        text = Path(out).read_text(encoding="utf-8")[:200].lower()
        assert "<html" in text


def test_interactive_folium_vector_quiver_html():
    try:
        import folium  # noqa: F401
    except Exception as e:
        import pytest

        pytest.skip(f"Optional interactive deps missing: {e}")

    import os
    import subprocess
    import sys
    import tempfile

    import numpy as np

    ny, nx = 10, 20
    U = np.ones((ny, nx), dtype="float32") * 0.5
    V = np.zeros((ny, nx), dtype="float32")
    with tempfile.TemporaryDirectory() as td:
        up = os.path.join(td, "u.npy")
        vp = os.path.join(td, "v.npy")
        out = os.path.join(td, "vec.html")
        np.save(up, U)
        np.save(vp, V)
        cmd = [
            sys.executable,
            "-m",
            "zyra.cli",
            "interactive",
            "--mode",
            "vector",
            "--u",
            up,
            "--v",
            vp,
            "--output",
            out,
            "--engine",
            "folium",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        assert proc.returncode == 0, proc.stderr
        assert os.path.exists(out)
        text = Path(out).read_text(encoding="utf-8")[:200].lower()
        assert "<html" in text


def test_interactive_folium_vector_streamlines_html():
    try:
        import folium  # noqa: F401
    except Exception as e:
        import pytest

        pytest.skip(f"Optional interactive deps missing: {e}")

    import os
    import subprocess
    import sys
    import tempfile

    import numpy as np

    ny, nx = 10, 20
    # rotational field
    x = np.linspace(-1.0, 1.0, nx)
    y = np.linspace(-1.0, 1.0, ny)
    X, Y = np.meshgrid(x, y)
    U = -Y.astype("float32")
    V = X.astype("float32")
    with tempfile.TemporaryDirectory() as td:
        up = os.path.join(td, "u.npy")
        vp = os.path.join(td, "v.npy")
        out = os.path.join(td, "vec_stream.html")
        np.save(up, U)
        np.save(vp, V)
        cmd = [
            sys.executable,
            "-m",
            "zyra.cli",
            "interactive",
            "--mode",
            "vector",
            "--u",
            up,
            "--v",
            vp,
            "--output",
            out,
            "--engine",
            "folium",
            "--streamlines",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        assert proc.returncode == 0, proc.stderr
        assert os.path.exists(out)
        text = Path(out).read_text(encoding="utf-8")[:200].lower()
        assert "<html" in text
