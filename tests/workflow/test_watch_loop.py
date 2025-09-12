# SPDX-License-Identifier: Apache-2.0
import textwrap
from pathlib import Path

from tests.helpers import project_root


def test_watch_loop_runs_multiple_iterations(tmp_path: Path, monkeypatch):
    from zyra.cli import main as cli_main

    wf = tmp_path / "workflow.yml"
    wf.write_text(
        textwrap.dedent(
            """
            on:
              schedule:
                - cron: "* * * * *"
              dataset-update:
                - path: "{TMP}/trigger.txt"
                  check: size
            jobs:
              a:
                steps:
                  - "process convert-format - netcdf --stdout"
              b:
                needs: a
                steps:
                  - "decimate local -i - out.nc"
            """
        ).replace("{TMP}", str(tmp_path)),
        encoding="utf-8",
    )
    # Ensure outputs under tmp_path and seed stdin
    monkeypatch.chdir(tmp_path)
    repo_root = project_root(Path(__file__))
    demo_nc = repo_root / "tests/testdata/demo.nc"
    monkeypatch.setenv("ZYRA_DEFAULT_STDIN", str(demo_nc))

    (tmp_path / "trigger.txt").write_text("x", encoding="utf-8")
    rc = cli_main(
        [
            "run",
            str(wf),
            "--watch",
            "--watch-interval",
            "0.01",
            "--watch-count",
            "2",
            "--run-on-first",
        ]
    )
    assert rc == 0
