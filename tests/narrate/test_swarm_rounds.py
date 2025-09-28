# SPDX-License-Identifier: Apache-2.0
import asyncio
from typing import Any

from zyra.narrate.swarm import Agent, AgentSpec, SwarmOrchestrator


class CountingAgent(Agent):
    def __init__(
        self,
        spec: AgentSpec,
        audience: list[str] | None = None,
        style: str | None = None,
        llm: Any | None = None,
    ) -> None:
        super().__init__(spec, audience=audience, style=style, llm=llm)
        self.calls: int = 0

    async def run(self, context: dict[str, Any]) -> dict[str, Any]:
        self.calls += 1
        return await super().run(context)


def test_rounds_critic_runs_multiple_times():
    # summary (specialist) and critic; with max_rounds=2, critic should run twice, summary once
    s = CountingAgent(AgentSpec(id="summary", outputs=["summary"]))
    c = CountingAgent(AgentSpec(id="critic", role="critic", outputs=["critic_notes"]))
    orch = SwarmOrchestrator([s, c], max_workers=None, max_rounds=2)
    out = asyncio.run(orch.execute({}))
    assert "summary" in out and "critic_notes" in out
    assert s.calls == 1
    assert c.calls == 2
