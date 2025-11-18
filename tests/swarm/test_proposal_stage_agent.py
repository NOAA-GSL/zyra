# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import asyncio

import pytest

from zyra.swarm import StageAgentSpec
from zyra.swarm import agents as agents_module
from zyra.swarm.agents import ProposalStageAgent
from zyra.swarm.proposals import ToolProposal


def test_proposal_stage_agent_requires_required_args(monkeypatch):
    spec = StageAgentSpec(
        id="fetch_frames",
        stage="acquire",
        behavior="proposal",
        metadata={"proposal_options": ["ftp"]},
    )
    agent = ProposalStageAgent(spec)

    def fake_generate(request):
        assert request.stage_id == "fetch_frames"
        return ToolProposal(stage_id="fetch_frames", command="ftp", args={})

    events: list[str] = []

    def event_hook(name, payload):
        events.append(name)

    monkeypatch.setattr(agents_module, "generate_proposal", fake_generate)
    context = {"event_hook": event_hook}

    with pytest.raises(ValueError, match="missing required arguments"):
        asyncio.run(agent.run(context))

    assert "agent_proposal_invalid" in events


def test_proposal_stage_agent_applies_guardrails(monkeypatch):
    spec = StageAgentSpec(
        id="narrate_stage",
        stage="narrate",
        behavior="proposal",
        metadata={
            "proposal_options": ["swarm"],
            "proposal_guardrails": "dummy.rail",
        },
    )

    class FakeAdapter:
        def validate(self, agent, outputs):
            proposal = dict(outputs["proposal"])
            proposal["command"] = "describe"
            proposal["args"] = {"topic": "Weekly drought animation"}
            return {"proposal": proposal}

    def fake_generate(request):
        return ToolProposal(
            stage_id=request.stage_id,
            command="swarm",
            args={"topic": "placeholder"},
        )

    cli_calls: list[dict[str, str]] = []

    async def fake_cli_run(self, context):
        cli_calls.append(
            {"stage": self.spec.stage, "command": self.spec.command, **self.spec.args}
        )
        return {"summary": "ok"}

    monkeypatch.setattr(
        agents_module,
        "build_guardrails_adapter",
        lambda schema, strict=False: FakeAdapter(),
    )
    monkeypatch.setattr(agents_module, "generate_proposal", fake_generate)
    monkeypatch.setattr(agents_module.CliStageAgent, "run", fake_cli_run, raising=False)

    agent = ProposalStageAgent(spec)
    outputs = asyncio.run(agent.run({"event_hook": lambda *_: None}))

    assert cli_calls and cli_calls[0]["command"] == "describe"
    assert cli_calls[0]["topic"] == "Weekly drought animation"
    assert outputs["summary"] == "ok"


def test_proposal_request_includes_spec_args(monkeypatch):
    spec = StageAgentSpec(
        id="narrate_animation",
        stage="narrate",
        behavior="proposal",
        args={"input": "data/drought_animation.mp4"},
        metadata={
            "proposal_options": ["swarm"],
            "proposal_defaults": {"preset": "kids_policy_basic"},
        },
    )

    captured: dict[str, dict[str, str]] = {}

    def fake_generate(request):
        captured["defaults"] = request.defaults
        return ToolProposal(
            stage_id=request.stage_id,
            command="describe",
            args={
                "input": request.defaults.get("input", ""),
                "preset": request.defaults.get("preset"),
            },
        )

    async def fake_cli_run(self, context):  # pragma: no cover - deterministic stub
        return {"narration": "ok"}

    monkeypatch.setattr(agents_module, "generate_proposal", fake_generate)
    monkeypatch.setattr(agents_module.CliStageAgent, "run", fake_cli_run, raising=False)

    agent = ProposalStageAgent(spec)
    asyncio.run(agent.run({"event_hook": lambda *_: None}))

    defaults = captured["defaults"]
    assert defaults["input"] == "data/drought_animation.mp4"
    assert defaults["preset"] == "kids_policy_basic"
