import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace


def test_transform_enrich_metadata_reads_from_stdin(monkeypatch, tmp_path: Path):
    from zyra.cli import main as cli_main

    base = {
        "start_datetime": "2025-01-01T00:00:00",
        "end_datetime": "2025-01-02T00:00:00",
    }
    data = (json.dumps(base) + "\n").encode()
    fake_stdin = SimpleNamespace(buffer=io.BytesIO(data))
    monkeypatch.setattr(sys, "stdin", fake_stdin)

    out_path = tmp_path / "out.json"

    rc = cli_main(
        [
            "transform",
            "enrich-metadata",
            "--read-frames-meta-stdin",
            "--dataset-id",
            "dataset123",
            "-o",
            str(out_path),
        ]
    )
    assert rc == 0
    js = json.loads(out_path.read_text(encoding="utf-8"))
    assert js.get("dataset_id") == "dataset123"
    assert js.get("start_datetime") == base["start_datetime"]
    assert js.get("end_datetime") == base["end_datetime"]
