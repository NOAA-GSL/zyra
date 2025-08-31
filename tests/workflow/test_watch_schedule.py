import textwrap
from datetime import datetime
from pathlib import Path


def test_watch_schedule_runs_on_match(tmp_path: Path, monkeypatch):
    from zyra.cli import main as cli_main

    now = datetime.now()
    cron = f"* {now.hour} * * *"

    wf = tmp_path / "workflow.yml"
    wf.write_text(
        textwrap.dedent(
            f"""
            on:
              schedule:
                - cron: "{cron}"
              dataset-update:
                - path: "{tmp_path}/trigger.txt"
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
        ),
        encoding="utf-8",
    )

    # Ensure outputs under tmp_path and seed stdin
    monkeypatch.chdir(tmp_path)
    demo_nc = Path(__file__).resolve().parents[2] / "tests/testdata/demo.nc"
    monkeypatch.setenv("ZYRA_DEFAULT_STDIN", str(demo_nc))

    # Create trigger file referenced by dataset-update and run watch in single-poll mode
    (tmp_path / "trigger.txt").write_text("x", encoding="utf-8")
    rc = cli_main(["run", str(wf), "--watch", "--run-on-first"])
    assert rc == 0
