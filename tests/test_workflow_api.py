# SPDX-License-Identifier: Apache-2.0
import subprocess
from pathlib import Path

import pytest

from zyra.workflow import api as wf_api
from zyra.workflow.api import Workflow


def test_workflow_describe_loads_sample():
    sample = Path("samples/workflows/minimal.yml")
    wf = Workflow.load(str(sample))
    desc = wf.describe()
    assert desc["stages"][0]["stage"] == "narrate"
    assert desc["stages"][0]["command"] == "describe"


def test_workflow_run_capture(monkeypatch):
    captured_cmds: list[list[str]] = []

    def fake_run(cmd, capture_output=False, text=False, check=False):
        captured_cmds.append(cmd)
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout="ok" if capture_output else None,
            stderr="err" if capture_output else None,
        )

    monkeypatch.setattr(wf_api.subprocess, "run", fake_run)
    wf = Workflow.from_dict({"stages": [{"stage": "process", "command": "demo"}]})
    result = wf.run(capture=True)
    assert result.succeeded
    assert captured_cmds
    assert "zyra.cli" in captured_cmds[0]
    assert result.stages[0].stdout == "ok"


def test_workflow_run_stage(monkeypatch):
    captured_cmds: list[list[str]] = []

    def fake_run(cmd, capture_output=False, text=False, check=False):
        captured_cmds.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(wf_api.subprocess, "run", fake_run)
    wf = Workflow.from_dict({"stages": [{"stage": "narrate", "command": "describe"}]})
    res = wf.run_stage(0, capture=True)
    assert res.returncode == 0
    assert captured_cmds and "narrate" in " ".join(captured_cmds[0])


def test_workflow_run_stage_invalid_index():
    wf = Workflow.from_dict({"stages": []})
    with pytest.raises(IndexError):
        wf.run_stage(0)


def test_workflow_run_stage_invalid_name():
    wf = Workflow.from_dict({"stages": [{"stage": "narrate", "command": "describe"}]})
    with pytest.raises(IndexError):
        wf.run_stage("missing")
