# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json

from zyra.swarm import planner as planner_cli


class FakeClient:
    name = "mock"
    model = "mock"

    def generate(self, system_prompt: str, user_prompt: str, images=None):
        agents = [
            {
                "id": "import_step",
                "stage": "import",
                "command": "http",
                "args": {"url": "https://example.com/data.nc", "output": "data.nc"},
            },
            {
                "id": "visualize_step",
                "stage": "visualize",
                "command": "heatmap",
                "depends_on": ["import_step"],
                "args": {"input": "data.nc", "output": "plot.png"},
            },
        ]
        return json.dumps({"agents": agents})


def test_llm_rule(monkeypatch):
    monkeypatch.setattr(planner_cli, "_load_llm_client", lambda: FakeClient())
    manifest = planner_cli.planner.plan("Create a heatmap from remote data")
    assert manifest["agents"][0]["id"] == "import_step"
    assert manifest["agents"][1]["depends_on"] == ["import_step"]


def test_llm_stage_alias_mapping(monkeypatch):
    class AliasClient:
        name = "mock"
        model = "mock"

        def generate(self, system_prompt: str, user_prompt: str, images=None):
            payload = {
                "agents": [
                    {
                        "id": "download",
                        "stage": "ftp_download",
                        "command": "ftp_download",
                        "args": {"path": "ftp://example.com"},
                    }
                ]
            }
            return json.dumps(payload)

    fake_caps = {
        "stage_commands": {"acquire": {"ftp": {"positionals": []}}},
        "stage_aliases": {"acquire": "acquire", "download": "acquire"},
        "command_aliases": {"acquire": {"ftp": "ftp", "ftp_download": "ftp"}},
        "prompt": {"stage_order": ["acquire"], "stages": []},
    }

    monkeypatch.setattr(planner_cli, "_load_llm_client", lambda: AliasClient())
    monkeypatch.setattr(planner_cli, "_load_capabilities", lambda: fake_caps)
    manifest = planner_cli.planner.plan("Download some FTP data")
    agent = manifest["agents"][0]
    assert agent["stage"] == "acquire"
    assert agent["command"] == "ftp"
