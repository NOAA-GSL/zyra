# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from pathlib import Path

from zyra.pipeline_runner import _run_cli


def test_run_cli_captures_stdout(tmp_path: Path) -> None:
    meta = tmp_path / "frames.json"
    meta.write_text(
        '{"missing_count": 0, "analysis": {"duplicate_timestamps": []}}',
        encoding="utf-8",
    )
    rc, stdout, stderr = _run_cli(
        [
            "verify",
            "evaluate",
            "--metric",
            "completeness",
            "--input",
            str(meta),
        ],
        None,
    )
    assert rc == 0, stderr
    assert b"PASSED" in stdout
