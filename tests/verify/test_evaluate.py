# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

import zyra.verify as verify_module


def _write_meta(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "meta.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_completeness_pass(tmp_path: Path, capsys):
    data = {"missing_count": 0, "analysis": {"duplicate_timestamps": []}}
    meta = _write_meta(tmp_path, data)
    rc = verify_module._cmd_evaluate(Namespace(metric="completeness", input=str(meta)))
    captured = capsys.readouterr().out
    assert rc == 0
    assert "PASSED" in captured


def test_completeness_fail(tmp_path: Path, capsys):
    data = {
        "missing_timestamps": ["2024-01-01T00:30:00"],
        "analysis": {"duplicate_timestamps": ["2024-01-01T00:10:00"]},
    }
    meta = _write_meta(tmp_path, data)
    rc = verify_module._cmd_evaluate(Namespace(metric="completeness", input=str(meta)))
    captured = capsys.readouterr().out
    assert rc == 1
    assert "FAILED" in captured
    assert "examples" in captured


def test_completeness_missing_file(capsys):
    rc = verify_module._cmd_evaluate(
        Namespace(metric="completeness", input="/tmp/not-here.json")
    )
    captured = capsys.readouterr().out
    assert rc == 2
    assert "metadata not found" in captured
