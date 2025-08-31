import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.cli
def test_cli_timeseries_samples_csv(tmp_path):
    try:
        import matplotlib  # noqa: F401
        import pandas  # noqa: F401
    except Exception as e:
        pytest.skip(f"Visualization deps missing: {e}")

    from tests.helpers import project_root

    repo_root = project_root(Path(__file__))
    csv_path = repo_root / "samples" / "timeseries.csv"
    if not csv_path.exists():
        pytest.skip("samples/timeseries.csv not found")

    out = tmp_path / "ts_sample.png"
    cmd = [
        sys.executable,
        "-m",
        "zyra.cli",
        "visualize",
        "timeseries",
        "--input",
        str(csv_path),
        "--x",
        "time",
        "--y",
        "value",
        "--output",
        str(out),
        "--width",
        "320",
        "--height",
        "200",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    assert out.exists()
    assert out.stat().st_size > 0
