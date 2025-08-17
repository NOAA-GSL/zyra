import json
import sys
from pathlib import Path

from datavizhub.pipeline_runner import run_pipeline


def test_failure_diagnostics_shows_stage_and_command(tmp_path, monkeypatch, capsys):
    cfg = {
        "stages": [
            {
                "stage": "acquire",
                "command": "http",
                "args": {"url": "https://x", "list": True},
            },
        ]
    }
    p = tmp_path / "p.json"
    p.write_text(json.dumps(cfg))

    def fake_main(argv=None):
        raise SystemExit(2)

    monkeypatch.setattr("datavizhub.cli.main", fake_main)
    rc = run_pipeline(str(p), [], print_argv=False, dry_run=False)
    assert rc == 2
    err = capsys.readouterr().err
    assert "Stage 1 [acquire] failed" in err
    assert "datavizhub acquire http" in err
