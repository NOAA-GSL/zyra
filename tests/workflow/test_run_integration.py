import textwrap
from pathlib import Path


def test_zyra_run_executes_workflow_yaml(tmp_path: Path, monkeypatch):
    from zyra.cli import main as cli_main

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
    # Ensure outputs under tmp_path and seed stdin
    monkeypatch.chdir(tmp_path)
    demo_nc = Path(__file__).resolve().parent.parent / "testdata/demo.nc"
    monkeypatch.setenv("ZYRA_DEFAULT_STDIN", str(demo_nc))

    rc = cli_main(["run", str(wf)])
    assert rc == 0
    assert (tmp_path / "out.nc").exists()
