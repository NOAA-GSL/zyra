# SPDX-License-Identifier: Apache-2.0
import asyncio

from zyra.narrate.swarm import Agent, AgentSpec, SwarmOrchestrator


class FailingAgent(Agent):
    async def run(self, context):  # type: ignore[no-untyped-def]
        raise RuntimeError("boom")


def test_dag_skips_unmet_deps_and_status():
    # Build a small DAG: summary -> critic; summary fails, so critic should still run in later rounds,
    # but DAG first pass marks summary as failed; status.completed should be False due to critical failure.
    s = FailingAgent(AgentSpec(id="summary", outputs=["summary"]))
    c = Agent(
        AgentSpec(
            id="critic", role="critic", outputs=["critic_notes"], depends_on=["summary"]
        )
    )
    orch = SwarmOrchestrator([s, c], max_workers=None, max_rounds=1)
    out = asyncio.run(orch.execute({}))
    assert "summary" not in out  # failed
    # critic skipped due to unmet deps in DAG phase
    assert "critic_notes" not in out
    assert "summary" in orch.failed_agents
    # Build pack-like status
    critical = {"summary", "critic", "editor"}
    completed = not any(a in set(orch.failed_agents) for a in critical)
    assert completed is False
