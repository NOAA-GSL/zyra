import textwrap
from pathlib import Path


def test_workflow_watch_dataset_update_runs(tmp_path: Path, monkeypatch):
    from zyra.cli import main as cli_main

    # Create a tiny trigger file
    trg = tmp_path / "trigger.txt"
    trg.write_text("x", encoding="utf-8")

    wf = tmp_path / "workflow.yml"
    wf.write_text(
        textwrap.dedent(
            f"""
            on:
              dataset-update:
                - path: "{trg}"
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

    # Ensure outputs under tmp_path
    monkeypatch.chdir(tmp_path)
    demo_nc = Path(__file__).resolve().parents[2] / "tests/testdata/demo.nc"
    assert demo_nc.exists()
    monkeypatch.setenv("ZYRA_DEFAULT_STDIN", str(demo_nc))

    state = tmp_path / "state.json"
    rc = cli_main(
        ["run", str(wf), "--watch", "--state-file", str(state), "--run-on-first"]
    )
    assert rc == 0
    # State should be written
    assert state.exists()
    content = state.read_text(encoding="utf-8")
    assert content.strip().startswith("{")
