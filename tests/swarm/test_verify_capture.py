# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import asyncio
from typing import Any

from zyra.swarm.core import StageContext, SwarmAgentProtocol, SwarmOrchestrator
from zyra.swarm.spec import StageAgentSpec


class _DummyVerifyAgent(SwarmAgentProtocol):
    def __init__(self) -> None:
        self.spec = StageAgentSpec(
            id="verify_stage",
            stage="verify",
            command="evaluate",
            args={"metric": "completeness"},
        )

    async def run(self, context: StageContext) -> dict[str, Any]:
        return {
            self.spec.id: b"verify evaluate: completeness FAILED - 2 missing frame(s)"
        }


def test_swarm_captures_verify_results():
    agent = _DummyVerifyAgent()
    logged: list[tuple[str, dict[str, Any]]] = []

    def hook(name: str, payload: dict[str, Any]) -> None:
        logged.append((name, payload))

    ctx = StageContext(metadata={})
    ctx.event_hook = hook
    ctx.state["event_hook"] = hook
    orch = SwarmOrchestrator([agent], event_hook=hook)
    asyncio.run(orch.execute(ctx))
    verify_results = ctx.metadata.get("verify_results")
    assert isinstance(verify_results, list)
    entry = verify_results[0]
    assert entry["verdict"] == "failed"
    assert "missing frame" in entry["message"]
    verify_events = [evt for evt in logged if evt[0] == "agent_verify_result"]
    assert verify_events, f"expected verify event in {logged}"
    payload = verify_events[0][1]
    assert payload.get("verdict") == "failed"
