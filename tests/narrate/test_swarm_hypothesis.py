# SPDX-License-Identifier: Apache-2.0
import asyncio

import pytest

from zyra.narrate.swarm import Agent, AgentSpec, SwarmOrchestrator

hyp = pytest.importorskip("hypothesis")
st = pytest.importorskip("hypothesis.strategies")


def _expected_runs(agent_ids: list[str], rounds: int) -> dict[str, int]:
    # Round 1: all
    counts = {aid: 1 for aid in agent_ids}
    # Subsequent rounds: critic/editor only
    extra = max(0, rounds - 1)
    if extra:
        for aid in agent_ids:
            role = (
                "critic"
                if aid == "critic"
                else ("editor" if aid == "editor" else "specialist")
            )
            if role in {"critic", "editor"}:
                counts[aid] = counts.get(aid, 0) + extra
    return counts


@hyp.given(
    st.lists(
        st.sampled_from(["summary", "context", "critic", "editor", "audience_adapter"]),
        min_size=1,
        max_size=4,
    ).map(lambda xs: list(dict.fromkeys(xs))),
    st.integers(min_value=1, max_value=3),
)
def test_orchestrator_provenance_counts(agent_ids, rounds):
    # Build agents with single output each
    def out_for(aid: str) -> str:
        return (
            "critic_notes"
            if aid == "critic"
            else ("edited" if aid == "editor" else aid)
        )

    agents = [
        Agent(
            AgentSpec(
                id=aid,
                role=(
                    "critic"
                    if aid == "critic"
                    else ("editor" if aid == "editor" else "specialist")
                ),
                outputs=[out_for(aid)],
            )
        )
        for aid in agent_ids
    ]
    orch = SwarmOrchestrator(agents, max_workers=None, max_rounds=rounds)
    _ = asyncio.run(orch.execute({}))
    # Tally provenance per agent id
    got = {}
    for p in orch.provenance:
        got[p.get("agent")] = got.get(p.get("agent"), 0) + 1
    assert got == _expected_runs(agent_ids, rounds)
