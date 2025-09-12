import os
import tempfile


def test_timeseries_manager_csv():
    try:
        import matplotlib  # noqa: F401

        from zyra.visualization import TimeSeriesManager
    except Exception as e:
        import pytest

        pytest.skip(f"Visualization deps missing: {e}")

    # Create a tiny CSV
    import numpy as np
    import pandas as pd

    with tempfile.TemporaryDirectory() as td:
        csv_path = os.path.join(td, "ts.csv")
        x = np.arange(10)
        y = np.sin(x / 3.0)
        pd.DataFrame({"time": x, "value": y}).to_csv(csv_path, index=False)

        mgr = TimeSeriesManager(title="Demo", xlabel="time", ylabel="value")
        mgr.render(
            input_path=csv_path, x="time", y="value", width=320, height=200, dpi=96
        )
        out = os.path.join(td, "ts.png")
        path = mgr.save(out)
        assert path and os.path.exists(path)
        assert os.path.getsize(path) > 0


def test_cli_timeseries_csv_smoke():
    try:
        import matplotlib  # noqa: F401
        import pandas  # noqa: F401
    except Exception as e:
        import pytest

        pytest.skip(f"Visualization deps missing: {e}")

    import subprocess
    import sys

    import numpy as np
    import pandas as pd

    with tempfile.TemporaryDirectory() as td:
        csv_path = os.path.join(td, "ts.csv")
        out = os.path.join(td, "ts.png")
        x = np.arange(10)
        y = np.cos(x / 2.0)
        pd.DataFrame({"t": x, "v": y}).to_csv(csv_path, index=False)

        cmd = [
            sys.executable,
            "-m",
            "zyra.cli",
            "visualize",
            "timeseries",
            "--input",
            csv_path,
            "--x",
            "t",
            "--y",
            "v",
            "--output",
            out,
            "--width",
            "320",
            "--height",
            "200",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        assert proc.returncode == 0, proc.stderr
        assert os.path.exists(out)
        assert os.path.getsize(out) > 0
