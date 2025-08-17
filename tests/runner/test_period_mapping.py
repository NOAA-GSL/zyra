import io
import json
from pathlib import Path

from datavizhub.pipeline_runner import run_pipeline


def test_period_and_since_period_mapping(tmp_path, monkeypatch, capsys):
    cfg = {
        "name": "period mapping",
        "stages": [
            {
                "stage": "acquire",
                "command": "ftp",
                "args": {"path": "host/path", "since_period": "P1D"},
            },
            {
                "stage": "acquire",
                "command": "ftp",
                "args": {"path": "host/path", "period": "1D"},
            },
        ],
    }
    p = tmp_path / "p.yaml"
    p.write_text(json.dumps(cfg))

    # Monkeypatch CLI main to just print argv and succeed
    def fake_main(argv=None):
        return 0

    monkeypatch.setattr("datavizhub.cli.main", fake_main)

    # Dry-run prints argv; ensure both stages got a computed --since
    rc = run_pipeline(str(p), [], print_argv=True, dry_run=True)
    assert rc == 0
    out = capsys.readouterr().out
    assert "--since" in out
