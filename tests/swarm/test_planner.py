# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
from argparse import Namespace

import zyra.swarm.value_engine as value_engine
from zyra.swarm import planner as planner_cli
from zyra.swarm.planner import (
    _apply_suggestion_templates,
    _collect_arg_gaps,
    _detect_clarifications,
    _drop_placeholder_args,
    _field_help_text,
    _map_to_capabilities,
    _normalize_args_for_command,
    _propagate_inferred_args,
    _validate_manifest,
    planner,
)
from zyra.swarm.value_engine import suggest as suggest_augmentations


def test_mock_rule_produces_manifest():
    manifest = planner.plan("mock swarm pipeline")
    assert manifest["agents"][0]["id"] == "simulate"
    assert manifest["agents"][1]["depends_on"] == ["simulate"]
    assert manifest["agents"][1]["stage"] == "narrate"


def test_cli_dump(capsys):
    ns = Namespace(
        intent="mock swarm plan",
        intent_file=None,
        output="-",
        guardrails=None,
        strict=False,
        memory=None,
        no_clarify=True,
        verbose=False,
    )
    rc = planner_cli._cmd_plan(ns)
    assert rc == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["agents"][0]["stage"] == "simulate"
    assert payload.get("suggestions") is not None


def test_validation_detects_duplicate():
    manifest = {
        "agents": [
            {"id": "a", "stage": "simulate"},
            {"id": "a", "stage": "narrate"},
        ]
    }
    errs = _validate_manifest(manifest)
    assert any("duplicate" in e for e in errs)


def test_detect_clarifications(tmp_path):
    manifest = {
        "agents": [
            {
                "id": "viz",
                "stage": "visualize",
                "args": {"basemap": str(tmp_path / "missing.png")},
            }
        ]
    }
    clarifications = _detect_clarifications(manifest)
    assert clarifications


def test_detect_clarifications_missing_required(monkeypatch):
    fake_caps = {
        "stage_commands": {
            "acquire": {
                "ftp": {
                    "positionals": [{"name": "path", "required": True}],
                    "options": {},
                }
            }
        },
    }
    monkeypatch.setattr(planner_cli, "_load_capabilities", lambda: fake_caps)
    manifest = {
        "agents": [
            {
                "id": "ftp",
                "stage": "acquire",
                "command": "ftp",
                "args": {},
            }
        ]
    }
    clarifications = _detect_clarifications(manifest)
    assert any("missing required argument" in msg for msg in clarifications)


def test_detect_clarifications_placeholder(monkeypatch):
    fake_caps = {
        "stage_commands": {
            "acquire": {
                "ftp": {
                    "positionals": [{"name": "path", "required": True}],
                    "options": {},
                }
            }
        },
    }
    monkeypatch.setattr(planner_cli, "_load_capabilities", lambda: fake_caps)
    manifest = {
        "agents": [
            {
                "id": "ftp",
                "stage": "acquire",
                "command": "ftp",
                "args": {"path": "ftp://example.org/data"},
            }
        ]
    }
    clarifications = _detect_clarifications(manifest)
    assert any("placeholder value" in msg for msg in clarifications)


def test_drop_placeholder_args_removes_example_path():
    args = {
        "path": "ftp://example.org/data",
        "pattern": "^Frame_[0-9]{8}\\.png$",
    }
    clean = _drop_placeholder_args(args)
    assert "path" not in clean


def test_normalize_args_drops_pattern_without_path():
    args = {"pattern": "^Frame_[0-9]{8}\\.png$"}
    normalized = _normalize_args_for_command("acquire", "ftp", args)
    assert "pattern" not in normalized


def test_value_engine_suggests_narrate_and_verify():
    manifest = {
        "agents": [
            {"id": "import", "stage": "import"},
            {"id": "viz", "stage": "visualize"},
        ]
    }
    suggestions = suggest_augmentations(manifest)
    stages = {s["stage"] for s in suggestions}
    assert "narrate" in stages
    assert "verify" in stages
    for s in suggestions:
        assert s.get("intent_text") is not None


def test_value_engine_llm_integration(monkeypatch):
    class FakeClient:
        name = "openai"
        model = "mock"

        def generate(self, system_prompt: str, user_prompt: str, images=None):
            return '[{"stage":"diagnostics","description":"LLM suggested QC plot","confidence":0.91}]'

    monkeypatch.setattr(value_engine, "_load_llm_client", lambda: FakeClient())
    manifest = {"agents": [{"id": "viz", "stage": "visualize"}]}
    suggestions = value_engine.suggest(manifest, intent="please enrich plan")
    assert any(s["stage"] == "diagnostics" for s in suggestions)


def test_cli_strict_validation(monkeypatch, capsys):
    def fake_plan(intent: str) -> dict[str, object]:
        return {"intent": intent, "agents": [{"id": "", "stage": "unknown"}]}

    monkeypatch.setattr(planner_cli, "planner", planner_cli.Planner())
    monkeypatch.setattr(planner_cli.planner, "plan", fake_plan)
    ns = Namespace(
        intent="bad",
        intent_file=None,
        output="-",
        guardrails=None,
        strict=True,
        memory=None,
        no_clarify=True,
        verbose=False,
    )
    rc = planner_cli._cmd_plan(ns)
    assert rc == 2


def test_map_to_capabilities_stage_alias():
    caps = {
        "stage_commands": {"acquire": {"ftp": {"positionals": []}}},
        "stage_aliases": {"acquire": "acquire", "download": "acquire"},
        "command_aliases": {"acquire": {"ftp": "ftp", "ftp_download": "ftp"}},
    }
    entry = {
        "id": "fetch",
        "stage": "ftp_download",
        "command": "ftp_download",
        "args": {"path": "ftp://example.com"},
    }
    mapped = _map_to_capabilities(entry, caps)
    assert mapped["stage"] == "acquire"
    assert mapped["command"] == "ftp"


def test_collect_arg_gaps_includes_optional_resolver(monkeypatch):
    fake_caps = {
        "stage_commands": {
            "acquire": {
                "ftp": {
                    "positionals": [{"name": "path", "required": True}],
                    "options": {},
                }
            }
        },
    }
    monkeypatch.setattr(planner_cli, "_load_capabilities", lambda: fake_caps)
    original_resolvers = list(planner_cli._ARG_RESOLVERS)
    planner_cli._ARG_RESOLVERS[:] = [
        {
            "stage": "acquire",
            "command": "ftp",
            "field": "pattern",
            "handler": lambda gap: False,
        }
    ]
    manifest = {
        "agents": [
            {
                "id": "ftp",
                "stage": "acquire",
                "command": "ftp",
                "args": {"path": "ftp://host/path"},
            }
        ]
    }
    gaps = _collect_arg_gaps(manifest)
    assert any(g["field"] == "pattern" for g in gaps)
    planner_cli._ARG_RESOLVERS[:] = original_resolvers


def test_field_help_text(monkeypatch):
    fake_caps = {
        "stage_commands": {
            "acquire": {
                "ftp": {
                    "positionals": [],
                    "options": {"--pattern": {"help": "Regex to filter list/sync"}},
                }
            }
        },
    }
    monkeypatch.setattr(planner_cli, "_load_capabilities", lambda: fake_caps)
    help_text = _field_help_text("acquire", "ftp", "pattern")
    assert "Regex" in help_text


def test_pad_missing_fill_mode_clarification():
    manifest = {
        "agents": [
            {
                "id": "fill",
                "stage": "process",
                "command": "pad-missing",
                "args": {"fill_mode": "basemap"},
            }
        ]
    }
    gaps = planner_cli._collect_arg_gaps(manifest)
    assert any(g["field"] == "fill_mode" for g in gaps)


def test_pad_missing_fill_mode_manual_skip():
    manifest = {
        "agents": [
            {
                "id": "fill",
                "stage": "process",
                "command": "pad-missing",
                "args": {"fill_mode": "basemap"},
                "_planner_manual_fields": ["fill_mode"],
            }
        ]
    }
    gaps = planner_cli._collect_arg_gaps(manifest)
    assert not any(g["field"] == "fill_mode" for g in gaps)


def test_apply_suggestion_template_adds_narrate():
    manifest = {
        "agents": [
            {
                "id": "viz",
                "stage": "visualize",
                "command": "compose-video",
                "args": {"output": "videos/out.mp4"},
            }
        ]
    }
    suggestions = [{"stage": "narrate", "description": "Add narrative"}]
    updated = _apply_suggestion_templates(manifest, suggestions)
    assert len(updated["agents"]) == 2
    narrate_agent = updated["agents"][-1]
    assert narrate_agent["stage"] == "narrate"
    assert narrate_agent["depends_on"] == ["viz"]
    assert narrate_agent["args"].get("input") == "videos/out.mp4"


def test_propagate_inferred_pattern(monkeypatch):
    manifest = {
        "agents": [
            {
                "id": "fetch",
                "stage": "acquire",
                "command": "ftp",
                "args": {"pattern": "^DroughtRisk_Weekly_[0-9]{8}\\.png$"},
            },
            {
                "id": "scan",
                "stage": "process",
                "command": "scan-frames",
                "depends_on": ["fetch"],
                "args": {"pattern": "^Frame_[0-9]{8}\\.png$"},
            },
        ]
    }
    updated = _propagate_inferred_args(manifest)
    scan_args = updated["agents"][1]["args"]
    assert scan_args["pattern"] == "^DroughtRisk_Weekly_[0-9]{8}\\.png$"
