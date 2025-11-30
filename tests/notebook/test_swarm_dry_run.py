# SPDX-License-Identifier: Apache-2.0
import json
import subprocess
from pathlib import Path

import pytest

from zyra.notebook import create_session


@pytest.mark.skip(reason="requires zyra CLI runtime; enable in full env")
def test_swarm_dry_run_pipeline(tmp_path, monkeypatch):
    monkeypatch.setenv("ZYRA_NOTEBOOK_DIR", str(tmp_path))
    sess = create_session(workdir=tmp_path)

    def dummy(ns):  # pragma: no cover - minimal stub
        return "ok"

    sess.process.register("dummy", dummy, returns="object")
    sess.process.dummy()
    pipeline = sess.to_pipeline()
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps({"agents": pipeline}, indent=2), encoding="utf-8")

    cmd = [
        "poetry",
        "run",
        "zyra",
        "swarm",
        "--plan",
        str(plan_path),
        "--stage",
        "process",
        "--max-rounds",
        "1",
    ]
    # Dry-run: if CLI is available, this should exit 0; otherwise skip.
    try:
        proc = subprocess.run(cmd, cwd=Path.cwd(), capture_output=True, text=True)
    except FileNotFoundError:
        pytest.skip("zyra CLI not available in test env")
    assert proc.returncode == 0
