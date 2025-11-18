# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import asyncio

from zyra.swarm.core import SwarmAgentProtocol, SwarmOrchestrator
from zyra.swarm.guardrails import BaseGuardrailsAdapter


class DummySpec:
    def __init__(self, agent_id: str) -> None:
        self.id = agent_id
        self.role = "specialist"
        self.prompt_ref = None
        self.params = {}
        self.depends_on = []


class DummyAgent(SwarmAgentProtocol):
    def __init__(self, agent_id: str, output: dict[str, str]) -> None:
        self.spec = DummySpec(agent_id)
        self._output = output

    async def run(self, context):  # noqa: ANN001
        return dict(self._output)


class RecordingAdapter(BaseGuardrailsAdapter):
    def __init__(self, fail: bool = False) -> None:
        self.calls: list[str] = []
        self.fail = fail

    def validate(self, agent, outputs):  # noqa: ANN001
        self.calls.append(agent.spec.id)
        if self.fail:
            raise RuntimeError("guardrails failure")
        return {k: f"validated:{v}" for k, v in outputs.items()}


def test_guardrails_adapter_applies_changes() -> None:
    agent = DummyAgent("summary", {"text": "hello"})
    adapter = RecordingAdapter()
    orch = SwarmOrchestrator([agent], guardrails=adapter)
    result = asyncio.run(orch.execute({}))
    assert result["text"] == "validated:hello"
    assert adapter.calls == ["summary"]


def test_guardrails_failure_marks_agent() -> None:
    agent = DummyAgent("summary", {"text": "hello"})
    adapter = RecordingAdapter(fail=True)
    orch = SwarmOrchestrator([agent], guardrails=adapter)
    result = asyncio.run(orch.execute({}))
    assert result == {}
    assert "summary" in orch.failed_agents
    assert adapter.calls == ["summary"]
