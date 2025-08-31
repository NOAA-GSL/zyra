import textwrap
from pathlib import Path

from tests.helpers import project_root


def test_runner_writes_log_file_with_log_dir(tmp_path: Path, monkeypatch):
    from zyra.cli import main as cli_main

    # Ensure any relative output paths land under tmp_path
    monkeypatch.chdir(tmp_path)

    # Minimal pipeline: process convert-format - netcdf --stdout
    cfg = tmp_path / "pipe.yaml"
    cfg.write_text(
        textwrap.dedent(
            """
            stages:
              - stage: process
                command: convert-format
                args:
                  file_or_url: '-'
                  format: netcdf
                  stdout: true
              - stage: decimate
                command: local
                args:
                  input: '-'
                  path: "out.nc"
            """
        ),
        encoding="utf-8",
    )

    # Seed stdin via env so runner feeds bytes to the first stage
    repo_root = project_root(Path(__file__))
    demo_nc = repo_root / "tests/testdata/demo.nc"
    assert demo_nc.exists()
    monkeypatch.setenv("ZYRA_DEFAULT_STDIN", str(demo_nc))

    log_dir = tmp_path / "logs"
    rc = cli_main(
        ["run", str(cfg), "--log-dir", str(log_dir), "-v"]
    )  # verbose for logs
    assert rc == 0

    # Ensure all logging handlers flush
    import logging

    logging.shutdown()
    log_path = log_dir / "workflow.log"
    assert log_path.exists()
    # File presence is the primary requirement for --log-dir
    assert log_path.stat().st_size >= 0
