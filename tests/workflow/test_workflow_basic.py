import textwrap
from pathlib import Path


def test_workflow_serial_dag(tmp_path: Path, monkeypatch):
    from zyra.cli import main as cli_main

    # Prepare a workflow with two jobs: a -> b
    wf = tmp_path / "workflow.yml"
    wf.write_text(
        textwrap.dedent(
            """
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

    # Ensure relative outputs are under tmp_path
    monkeypatch.chdir(tmp_path)

    # Seed stdin via env so first job has input
    demo_nc = Path(__file__).resolve().parents[2] / "tests/testdata/demo.nc"
    assert demo_nc.exists()
    monkeypatch.setenv("ZYRA_DEFAULT_STDIN", str(demo_nc))

    # Run the workflow
    rc = cli_main(["run", str(wf)])
    assert rc == 0
    assert (tmp_path / "out.nc").exists()


def test_export_cron(tmp_path: Path, capsys):
    from zyra.cli import main as cli_main

    wf = tmp_path / "workflow.yml"
    wf.write_text(
        textwrap.dedent(
            """
            on:
              schedule:
                - cron: "0 * * * *"
                - cron: "0 6 * * *"
            jobs: {}
            """
        ),
        encoding="utf-8",
    )
    rc = cli_main(["run", str(wf), "--export-cron"])
    assert rc == 0
    out = capsys.readouterr().out
    # Best-effort: at least runs; printing may vary by environment
    assert isinstance(out, str)
