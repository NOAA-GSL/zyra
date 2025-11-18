# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import sqlite3

import pytest

from zyra.swarm import StageAgentSpec
from zyra.swarm import agents as agents_module
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


def test_proposal_events_recorded(tmp_path, monkeypatch, capsys) -> None:
    plan = {
        "metadata": {"description": "proposal-e2e"},
        "agents": [
            {
                "id": "story",
                "stage": "narrate",
                "behavior": "proposal",
                "metadata": {
                    "proposal_options": ["describe"],
                    "proposal_defaults": {"topic": "Weekly drought animation"},
                },
                "outputs": ["summary"],
            }
        ],
    }
    specs = _resolve_specs(plan)

    async def fake_cli_run(self, context):
        return {self.spec.stdout_key or self.spec.id: {"stage": self.spec.stage}}

    monkeypatch.setattr(agents_module.CliStageAgent, "run", fake_cli_run, raising=False)
    db_path = tmp_path / "proposal.db"
    outputs = _execute_specs(
        specs,
        plan=plan,
        plan_path="memory",
        max_workers=None,
        max_rounds=1,
        memory=str(db_path),
        guardrails=None,
        strict_guardrails=False,
        log_events=False,
    )
    assert outputs["story"]["stage"] == "narrate"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT event, payload FROM events ORDER BY id").fetchall()
    finally:
        conn.close()
    events = [row["event"] for row in rows]
    assert "agent_proposal_request" in events
    assert "agent_proposal_generated" in events
    assert "agent_proposal_validated" in events
    request_row = next(row for row in rows if row["event"] == "agent_proposal_request")
    payload = json.loads(request_row["payload"])
    assert payload["payload"]["stage"] == "narrate"
    completed_row = next(row for row in rows if row["event"] == "run_completed")
    completed_payload = json.loads(completed_row["payload"])
    assert completed_payload["proposals"]["story"]["command"] == "describe"
    _dump_memory(str(db_path))
    dump = capsys.readouterr().out
    assert "agent=story stage=narrate options" in dump
    assert "validated command=describe" in dump
    assert "proposals=story:describe" in dump
