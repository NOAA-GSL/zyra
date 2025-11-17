# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import pytest

from zyra.swarm import StageAgentSpec
from zyra.swarm.cli import (
    _dump_memory,
    _execute_specs,
    _format_dry_run,
    _load_plan,
    _resolve_specs,
)


def test_load_and_resolve_plan(tmp_path) -> None:
    plan_path = tmp_path / "plan.yaml"
    plan_path.write_text(
        """
metadata:
  description: test plan
agents:
  - id: simulate
    stage: simulate
    outputs: [simulated_output]
  - id: narrate
    stage: narrate
    depends_on: [simulate]
    stdin_from: simulated_output
    outputs: [narrative]
""",
        encoding="utf-8",
    )
    plan = _load_plan(str(plan_path))
    specs = _resolve_specs(plan)
    assert [spec.id for spec in specs] == ["simulate", "narrate"]
    assert isinstance(specs[0], StageAgentSpec)
    dry = _format_dry_run(specs)
    assert "simulate" in dry and "narrate" in dry


def test_execute_specs_produces_mock_outputs(tmp_path) -> None:
    plan = {
        "metadata": {"description": "unit-test"},
        "agents": [
            {"id": "simulate", "stage": "simulate", "outputs": ["sim"]},
            {
                "id": "narrate",
                "stage": "narrate",
                "depends_on": ["simulate"],
                "stdin_from": "sim",
                "outputs": ["story"],
            },
        ],
    }
    specs = _resolve_specs(plan)
    outputs = _execute_specs(
        specs,
        plan=plan,
        plan_path="memory",
        max_workers=None,
        max_rounds=1,
        memory="-",
        guardrails=None,
        strict_guardrails=False,
        log_events=False,
    )
    assert set(outputs) == {"sim", "story"}
    assert outputs["story"]["stage"] == "narrate"


@pytest.mark.filterwarnings("ignore:'decimate' is deprecated")
def test_log_events_and_dump_memory(tmp_path, capsys) -> None:
    plan = {
        "metadata": {"description": "integration"},
        "agents": [
            {
                "id": "narrate",
                "stage": "narrate",
                "command": "describe",
                "outputs": ["summary"],
                "args": {"topic": "demo"},
            },
            {
                "id": "export",
                "stage": "disseminate",
                "command": "local",
                "stdin_from": "summary",
                "outputs": ["artifact"],
                "args": {"input": "-", "path": str(tmp_path / "out.txt")},
            },
            {"id": "verify", "stage": "verify", "behavior": "mock"},
        ],
    }
    specs = _resolve_specs(plan)
    db = tmp_path / "prov.db"
    _execute_specs(
        specs,
        plan=plan,
        plan_path="integration",
        max_workers=None,
        max_rounds=1,
        memory=str(db),
        guardrails=None,
        strict_guardrails=False,
        log_events=True,
    )
    log_out = capsys.readouterr().out
    assert "[event run_started]" in log_out
    assert db.exists()
    _dump_memory(str(db))
    dump_out = capsys.readouterr().out
    assert "Run" in dump_out
