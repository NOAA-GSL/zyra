# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json

from zyra.swarm import proposals as proposals_module
from zyra.swarm.proposals import ToolProposalRequest


def test_generate_proposal_via_llm(monkeypatch):
    captured: dict[str, str] = {}

    class FakeClient:
        def generate(self, system_prompt, user_prompt):
            captured["system"] = system_prompt
            captured["user"] = user_prompt
            return json.dumps(
                {
                    "stage_id": "verify_1",
                    "command": "evaluate",
                    "args": {"metric": "RMSE"},
                    "justification": "LLM-selected",
                }
            )

    monkeypatch.setattr(proposals_module, "_load_llm_client", lambda: FakeClient())
    monkeypatch.setattr(
        proposals_module,
        "_load_stage_command_catalog",
        lambda: {
            "verify": {
                "evaluate": {
                    "description": "evaluate stage",
                    "positionals": [],
                    "options": {"--metric": {"help": "Metric name", "required": True}},
                }
            }
        },
    )
    request = ToolProposalRequest(
        stage_id="verify_1",
        stage="verify",
        options=["evaluate"],
        defaults={"metric": "RMSE"},
        context={"intent": "Check animation completeness"},
        instructions="Confirm the animation has the expected number of frames.",
    )
    proposal = proposals_module.generate_proposal(request)
    assert proposal.command == "evaluate"
    assert proposal.args["metric"] == "RMSE"
    assert "instructions" in captured["user"]


def test_generate_proposal_fallback(monkeypatch):
    monkeypatch.setattr(proposals_module, "_load_llm_client", lambda: None)
    request = ToolProposalRequest(
        stage_id="narrate_1",
        stage="narrate",
        options=["describe"],
        defaults={"preset": "kids_policy_basic"},
    )
    proposal = proposals_module.generate_proposal(request)
    assert proposal.command == "describe"
    assert proposal.args["preset"] == "kids_policy_basic"
