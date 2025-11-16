# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from zyra.swarm import StageAgentSpec
from zyra.swarm.cli import (
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
    )
    assert set(outputs) == {"sim", "story"}
    assert outputs["story"]["stage"] == "narrate"
