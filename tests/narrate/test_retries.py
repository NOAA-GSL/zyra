# SPDX-License-Identifier: Apache-2.0
import asyncio

from zyra.narrate.swarm import Agent, AgentSpec, SwarmOrchestrator


class FlakyAgent(Agent):
    def __init__(self, *args, fail_times=0, **kwargs):  # type: ignore[no-untyped-def]
        super().__init__(*args, **kwargs)
        self._remaining = fail_times

    async def run(self, context):  # type: ignore[no-untyped-def]
        if self._remaining > 0:
            self._remaining -= 1
            raise RuntimeError("transient")
        return await super().run(context)


def test_retries_eventual_success_no_error():
    # Agent will fail twice then succeed; params allow 2 retries, zero backoff for speed
    spec = AgentSpec(
        id="summary", outputs=["summary"], params={"max_retries": 2, "backoff_ms": 0}
    )
    a = FlakyAgent(spec, fail_times=2)
    orch = SwarmOrchestrator([a], max_workers=None, max_rounds=1)
    out = asyncio.run(orch.execute({}))
    assert "summary" in out
    assert orch.failed_agents == []
    assert orch.errors == []


def test_retries_exhausted_records_error():
    # Agent fails 2 times but only 1 retry allowed → final failure recorded
    spec = AgentSpec(
        id="summary", outputs=["summary"], params={"max_retries": 1, "backoff_ms": 0}
    )
    a = FlakyAgent(spec, fail_times=2)
    orch = SwarmOrchestrator([a], max_workers=None, max_rounds=1)
    out = asyncio.run(orch.execute({}))
    assert "summary" not in out
    assert "summary" in orch.failed_agents
    assert (
        orch.errors
        and orch.errors[0]["agent"] == "summary"
        and orch.errors[0]["retried"] == 1
    )
