# SPDX-License-Identifier: Apache-2.0
import io
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


def test_enrich_metadata_invalid_utf8_stdin(monkeypatch, tmp_path: Path):
    from zyra.cli import main as cli_main

    # Invalid UTF-8 bytes
    bad = b"\xff\xfe\xfa\x00"
    fake_stdin = SimpleNamespace(buffer=io.BytesIO(bad))
    monkeypatch.setattr(sys, "stdin", fake_stdin)

    with pytest.raises(SystemExit) as exc:
        cli_main(
            [
                "transform",
                "enrich-metadata",
                "--read-frames-meta-stdin",
                "--dataset-id",
                "dataset123",
                "-o",
                str(tmp_path / "out.json"),
            ]
        )
    assert "Failed to decode stdin as UTF-8 for frames metadata" in str(exc.value)


def test_enrich_metadata_invalid_json_stdin(monkeypatch, tmp_path: Path):
    from zyra.cli import main as cli_main

    bad = b"{ not-json }"
    fake_stdin = SimpleNamespace(buffer=io.BytesIO(bad))
    monkeypatch.setattr(sys, "stdin", fake_stdin)

    with pytest.raises(SystemExit) as exc:
        cli_main(
            [
                "transform",
                "enrich-metadata",
                "--read-frames-meta-stdin",
                "--dataset-id",
                "dataset123",
                "-o",
                str(tmp_path / "out.json"),
            ]
        )
    assert "Invalid JSON on stdin for frames metadata" in str(exc.value)


def test_update_dataset_invalid_meta_json_stdin(monkeypatch, tmp_path: Path):
    from zyra.cli import main as cli_main

    # Minimal dataset index
    ds = tmp_path / "dataset.json"
    ds.write_text('{"datasets": [{"id": "x"}]}', encoding="utf-8")

    bad = b"{"  # truncated JSON
    fake_stdin = SimpleNamespace(buffer=io.BytesIO(bad))
    monkeypatch.setattr(sys, "stdin", fake_stdin)

    with pytest.raises(SystemExit) as exc:
        cli_main(
            [
                "transform",
                "update-dataset-json",
                "--input-file",
                str(ds),
                "--dataset-id",
                "x",
                "--read-meta-stdin",
                "-o",
                str(tmp_path / "out.json"),
            ]
        )
    assert "Invalid metadata JSON on stdin" in str(exc.value)
