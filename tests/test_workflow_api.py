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


def test_workflow_run_stage_with_args_override(monkeypatch):
    captured_cmds: list[list[str]] = []

    def fake_run(cmd, capture_output=False, text=False, check=False):
        captured_cmds.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(wf_api.subprocess, "run", fake_run)
    wf = Workflow.from_dict(
        {"stages": [{"stage": "process", "command": "demo", "args": {"key1": "val1"}}]}
    )
    res = wf.run_stage(0, args={"key2": "val2"}, capture=True)
    assert res.returncode == 0
    assert captured_cmds
    joined = " ".join(captured_cmds[0])
    assert "key1" in joined
    assert "key2" in joined


def test_workflow_run_stream_writes_stdout(monkeypatch, capsys):
    captured_cmds: list[list[str]] = []

    def fake_run(cmd, capture_output=False, text=False, check=False):
        captured_cmds.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="hello", stderr="world")

    monkeypatch.setattr(wf_api.subprocess, "run", fake_run)
    wf = Workflow.from_dict({"stages": [{"stage": "process", "command": "demo"}]})
    result = wf.run(capture=True, stream=True)
    out = capsys.readouterr()
    assert "hello" in out.out
    assert "world" in out.err
    assert result.stages[0].stdout == "hello"
    assert result.stages[0].stderr == "world"


def test_workflow_run_continue_on_error(monkeypatch):
    calls: list[list[str]] = []

    # First stage fails, others succeed
    def fake_run(cmd, capture_output=False, text=False, check=False):
        calls.append(cmd)
        rc = 1 if len(calls) == 1 else 0
        return subprocess.CompletedProcess(cmd, rc, stdout="", stderr="")

    monkeypatch.setattr(wf_api.subprocess, "run", fake_run)
    wf = Workflow.from_dict(
        {
            "stages": [
                {"stage": "process", "command": "one"},
                {"stage": "process", "command": "two"},
            ]
        }
    )
    # Default (continue_on_error=False) stops after first failure
    result = wf.run(capture=True)
    assert len(result.stages) == 1
    assert result.stages[0].returncode == 1
    # With continue_on_error=True, both stages attempted
    calls.clear()
    result2 = wf.run(capture=True, continue_on_error=True)
    assert len(result2.stages) == 2
    assert result2.stages[0].returncode == 1
    assert result2.stages[1].returncode == 0
