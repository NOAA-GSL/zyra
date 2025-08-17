import subprocess
import sys

import pytest


@pytest.mark.cli()
@pytest.mark.parametrize(
    "cmd",
    [
        ["visualize", "heatmap", "--help"],
        ["visualize", "contour", "--help"],
        ["visualize", "timeseries", "--help"],
        ["visualize", "vector", "--help"],
        ["visualize", "animate", "--help"],
        ["visualize", "compose-video", "--help"],
        ["visualize", "interactive", "--help"],
    ],
)
def test_visualize_subcommand_help_exits_zero(cmd):
    proc = subprocess.run(
        [sys.executable, "-m", "datavizhub.cli", *cmd], capture_output=True
    )
    assert proc.returncode == 0, proc.stderr.decode(errors="ignore")
