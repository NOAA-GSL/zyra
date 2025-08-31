import textwrap
from pathlib import Path

from tests.helpers import project_root


def test_parallel_dag_two_independent_jobs(tmp_path: Path, monkeypatch):
    from zyra.cli import main as cli_main

    wf = tmp_path / "workflow.yml"
    wf.write_text(
        textwrap.dedent(
            """
            jobs:
              a:
                steps:
                  - "process convert-format - netcdf --stdout"
                  - "decimate local -i - out1.nc"
              b:
                steps:
                  - "process convert-format - netcdf --stdout"
                  - "decimate local -i - out2.nc"
            """
        ),
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    repo_root = project_root(Path(__file__))
    demo_nc = repo_root / "tests/testdata/demo.nc"
    monkeypatch.setenv("ZYRA_DEFAULT_STDIN", str(demo_nc))

    rc = cli_main(["run", str(wf), "--max-workers", "2"])
    assert rc == 0
    assert (tmp_path / "out1.nc").exists()
    assert (tmp_path / "out2.nc").exists()
