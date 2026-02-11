# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
import os
from argparse import Namespace

import pytest

import zyra.swarm.value_engine as value_engine
from zyra.swarm import planner as planner_cli
from zyra.swarm.planner import (
    _EXAMPLE_MANIFEST,
    _STAGE_SEQUENCE,
    _agent_reasoning,
    _apply_suggestion_templates,
    _collect_arg_gaps,
    _detect_clarifications,
    _drop_placeholder_args,
    _ensure_auto_verify_agent,
    _ensure_verify_agents_materialized,
    _field_help_text,
    _map_to_capabilities,
    _normalize_args_for_command,
    _propagate_inferred_args,
    _run_guardrails,
    _scan_frames_plan_details,
    _strip_internal_fields,
    _validate_manifest,
    planner,
)


def test_mock_rule_produces_manifest():
    manifest = planner.plan("mock swarm pipeline")
    assert manifest["agents"][0]["id"] == "simulate"
    assert manifest["agents"][1]["depends_on"] == ["simulate"]
    assert manifest["agents"][1]["stage"] == "narrate"


def test_example_fallback_manifest(monkeypatch):
    monkeypatch.setattr(planner_cli, "_load_llm_client", lambda: None)
    manifest = planner.plan("fallback manifest please")
    agents = manifest["agents"]
    assert agents[0]["id"] == "fetch_frames"
    assert any(agent["stage"] == "visualize" for agent in agents)


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
    assert isinstance(payload.get("plan_summary"), str)


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


def test_ftp_path_requires_confirmation(monkeypatch):
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
                "args": {"path": "ftp://droughtmonitor.unl.edu/weekly/frames/"},
            }
        ]
    }
    clarifications = _detect_clarifications(manifest)
    assert any("confirm" in msg.lower() for msg in clarifications)


def test_drop_placeholder_args_removes_example_path():
    args = {
        "path": "ftp://example.org/data",
        "pattern": "^Frame_[0-9]{8}\\.png$",
    }
    clean = _drop_placeholder_args(args)
    assert "path" not in clean


def test_friendly_gap_message_fallback(monkeypatch):
    monkeypatch.setattr(planner_cli, "_load_llm_client", lambda: None)
    gap = {
        "stage": "acquire",
        "command": "ftp",
        "field": "path",
        "reason": "missing_arg",
    }
    message = planner_cli._friendly_gap_message(gap, "Provide an FTP URL.")
    assert "acquire" in message
    assert "path" in message


def test_friendly_gap_message_with_llm(monkeypatch):
    class FakeClient:
        def generate(self, system_prompt, payload):
            data = json.loads(payload)
            return f"Please share {data['field']} for {data['stage']}"

    monkeypatch.setattr(planner_cli, "_load_llm_client", lambda: FakeClient())
    gap = {
        "stage": "narrate",
        "command": "describe",
        "field": "input",
        "reason": "missing_arg",
    }
    message = planner_cli._friendly_gap_message(gap, None)
    assert message == "Please share input for narrate"


def test_strip_internal_fields_drops_unconfirmed_ftp_args():
    manifest = {
        "agents": [
            {
                "id": "ftp",
                "stage": "acquire",
                "command": "ftp",
                "args": {
                    "path": "ftp://example.com/data/",
                    "pattern": "^Frame_[0-9]{8}\\.png$",
                },
            }
        ]
    }
    _strip_internal_fields(manifest)
    ftp_args = manifest["agents"][0]["args"]
    assert "path" not in ftp_args
    assert "pattern" not in ftp_args


def test_strip_internal_fields_preserves_manual_ftp_args():
    manifest = {
        "agents": [
            {
                "id": "ftp",
                "stage": "acquire",
                "command": "ftp",
                "args": {
                    "path": "ftp://real.host/data/",
                    "pattern": "^Frame_[0-9]{8}\\.png$",
                },
                "_planner_manual_fields": ["path"],
            }
        ]
    }
    _strip_internal_fields(manifest)
    ftp_args = manifest["agents"][0]["args"]
    assert ftp_args["path"] == "ftp://real.host/data/"
    assert ftp_args["pattern"] == "^Frame_[0-9]{8}\\.png$"


def test_scan_frames_reasoning_includes_stats(tmp_path):
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    (frames_dir / "frame_202401010000.png").write_bytes(b"a")
    (frames_dir / "frame_202401010010.png").write_bytes(b"b")
    agent = {
        "id": "scan",
        "stage": "process",
        "command": "scan-frames",
        "args": {
            "frames_dir": str(frames_dir),
            "datetime_format": "%Y%m%d%H%M",
        },
    }
    text = _agent_reasoning(agent, "download")
    assert "Stats" in text


def test_scan_frames_missing_dir_does_not_crash(monkeypatch):
    def fake_compute(*args, **kwargs):
        raise SystemExit("Frames directory not found: boom")

    monkeypatch.setattr(planner_cli, "_compute_frames_metadata", fake_compute)
    agent = {
        "id": "scan",
        "stage": "process",
        "command": "scan-frames",
        "args": {
            "frames_dir": "missing_dir",
        },
    }
    summary, meta = _scan_frames_plan_details(agent)
    assert summary is None and meta is None


def test_apply_suggestion_template_inserts_custom_agent():
    manifest = {"agents": []}
    suggestion = {
        "stage": "verify",
        "description": "Add completeness check",
        "agent_template": {
            "stage": "verify",
            "behavior": "cli",
            "command": "evaluate",
            "args": {"metric": "completeness"},
        },
    }
    updated = planner_cli._apply_suggestion_templates(manifest, [suggestion])
    verify_agent = next(a for a in updated["agents"] if a["stage"] == "verify")
    assert verify_agent["command"] == "evaluate"


def test_auto_verify_agent_inserted(tmp_path):
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    (frames_dir / "frame_202401010000.png").write_bytes(b"a")
    (frames_dir / "frame_202401010100.png").write_bytes(b"b")
    manifest = {
        "agents": [
            {
                "id": "scan",
                "stage": "process",
                "command": "scan-frames",
                "args": {
                    "frames_dir": str(frames_dir),
                    "datetime_format": "%Y%m%d%H%M",
                    "period_seconds": 1800,
                    "output": str(tmp_path / "meta.json"),
                },
            }
        ]
    }
    _ensure_auto_verify_agent(manifest)
    verify_agent = next(a for a in manifest["agents"] if a["stage"] == "verify")
    assert verify_agent["command"] == "evaluate"
    assert verify_agent["behavior"] == "cli"
    assert verify_agent["args"].get("input") == str(tmp_path / "meta.json")


def test_verify_proposal_materialized(tmp_path):
    frames_dir = tmp_path / "frames2"
    frames_dir.mkdir()
    (frames_dir / "frame_202401010000.png").write_bytes(b"a")
    manifest = {
        "agents": [
            {
                "id": "scan_custom",
                "stage": "process",
                "command": "scan-frames",
                "args": {
                    "frames_dir": str(frames_dir),
                    "output": str(tmp_path / "meta2.json"),
                },
            },
            {
                "id": "verify_animation",
                "stage": "verify",
                "behavior": "proposal",
                "command": None,
                "depends_on": [],
                "args": {},
            },
        ]
    }
    _ensure_verify_agents_materialized(manifest)
    verify_agent = next(a for a in manifest["agents"] if a["stage"] == "verify")
    assert verify_agent["behavior"] == "cli"
    assert verify_agent["command"] == "evaluate"
    assert verify_agent["args"]["input"] == str(tmp_path / "meta2.json")
    assert "scan_custom" in verify_agent["depends_on"]


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
    suggestions = value_engine.suggest(manifest)
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


def test_map_to_capabilities_narrate_proposal():
    caps = {
        "stage_commands": {"narrate": {"describe": {"positionals": []}}},
        "stage_aliases": {"narrate": "narrate"},
        "command_aliases": {"narrate": {"describe": "describe"}},
    }
    entry = {
        "id": "narrate_1",
        "stage": "narrate",
        "command": "describe",
        "depends_on": ["viz"],
        "args": {"input": "data/out.mp4"},
    }
    mapped = _map_to_capabilities(entry, caps)
    assert mapped["behavior"] == "proposal"
    assert mapped["stage"] == "narrate"
    assert mapped["depends_on"] == ["viz"]
    assert mapped["args"]["input"] == "data/out.mp4"
    assert "proposal_options" in mapped["metadata"]


def test_map_to_capabilities_verify_proposal():
    caps = {
        "stage_commands": {"verify": {"evaluate": {"positionals": []}}},
        "stage_aliases": {"verify": "verify"},
        "command_aliases": {"verify": {"evaluate": "evaluate"}},
    }
    entry = {
        "id": "verify_1",
        "stage": "verify",
        "command": "evaluate",
        "depends_on": ["proc"],
    }
    mapped = _map_to_capabilities(entry, caps)
    assert mapped["behavior"] == "proposal"
    assert mapped["metadata"].get("proposal_options") == ["evaluate"]
    assert mapped["depends_on"] == ["proc"]


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


def test_pad_missing_fill_mode_confirm_cache():
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
    confirm_cache: dict[tuple[str, str, str], str] = {}
    previous_cache = planner_cli._CURRENT_CONFIRM_CACHE
    try:
        planner_cli._CURRENT_CONFIRM_CACHE = confirm_cache
        planner_cli._remember_confirmation(
            "process", "pad-missing", "fill_mode", "basemap"
        )
        gaps = planner_cli._collect_arg_gaps(manifest)
        assert not any(g["field"] == "fill_mode" for g in gaps)
    finally:
        planner_cli._CURRENT_CONFIRM_CACHE = previous_cache


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
    assert narrate_agent["metadata"]["proposal_options"] == ["swarm", "describe"]


def test_apply_suggestion_template_adds_verify():
    manifest = {
        "agents": [
            {"id": "fetch", "stage": "acquire", "command": "ftp"},
            {
                "id": "proc",
                "stage": "process",
                "command": "scan-frames",
                "depends_on": ["fetch"],
            },
        ]
    }
    suggestions = [{"stage": "verify", "description": "Add verify"}]
    updated = _apply_suggestion_templates(manifest, suggestions)
    verify_agent = updated["agents"][-1]
    assert verify_agent["stage"] == "verify"
    assert verify_agent["behavior"] == "proposal"
    assert set(verify_agent["depends_on"]) == {"fetch", "proc"}
    metadata = verify_agent["metadata"]
    assert metadata["proposal_options"] == ["evaluate"]
    assert "proposal_instructions" in metadata


def test_apply_suggestion_template_diagnostics_alias():
    manifest = {"agents": [{"id": "fetch", "stage": "acquire", "command": "ftp"}]}
    updated = _apply_suggestion_templates(
        manifest, [{"stage": "diagnostics", "description": "Add diagnostics"}]
    )
    diag_agent = updated["agents"][-1]
    assert diag_agent["stage"] == "verify"
    assert diag_agent["behavior"] == "proposal"


def test_apply_suggestion_template_links_visual_dependency():
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
    suggestions = [
        {"stage": "narrate", "description": "Summarize the animation video output."}
    ]
    updated = _apply_suggestion_templates(manifest, suggestions)
    narrate_agent = updated["agents"][-1]
    assert narrate_agent["depends_on"] == ["viz"]


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


def test_propagate_ftp_args():
    manifest = {
        "agents": [
            {"id": "fetch", "stage": "acquire", "command": "ftp", "args": {}},
            {
                "id": "scan",
                "stage": "process",
                "command": "scan-frames",
                "depends_on": ["fetch"],
                "args": {
                    "datetime_format": "%Y%m%d",
                    "frames_dir": "data/frames_raw",
                },
            },
        ]
    }
    updated = _propagate_inferred_args(manifest)
    ftp_args = updated["agents"][0]["args"]
    assert ftp_args["sync_dir"] == "data/frames_raw"
    assert ftp_args["date_format"] == "%Y%m%d"


def test_pad_output_dir_and_compose_frames():
    manifest = {
        "agents": [
            {
                "id": "fetch",
                "stage": "acquire",
                "command": "ftp",
                "args": {"sync_dir": "data/raw_frames"},
            },
            {
                "id": "scan",
                "stage": "process",
                "command": "scan-frames",
                "depends_on": ["fetch"],
                "args": {"frames_dir": "data/raw_frames"},
            },
            {
                "id": "pad",
                "stage": "process",
                "command": "pad-missing",
                "depends_on": ["scan"],
                "args": {},
            },
            {
                "id": "compose",
                "stage": "visualize",
                "command": "compose-video",
                "depends_on": ["pad"],
                "args": {},
            },
        ]
    }
    updated = _propagate_inferred_args(manifest)
    pad_args = next(a for a in updated["agents"] if a["id"] == "pad")["args"]
    assert pad_args["output_dir"] == "data/raw_frames"
    compose_args = next(a for a in updated["agents"] if a["id"] == "compose")["args"]
    assert compose_args["frames"] == "data/raw_frames"


def test_pad_output_dir_replaced_when_default_placeholder():
    manifest = {
        "agents": [
            {
                "id": "scan",
                "stage": "process",
                "command": "scan-frames",
                "args": {"frames_dir": "data/downloaded"},
            },
            {
                "id": "pad",
                "stage": "process",
                "command": "pad-missing",
                "depends_on": ["scan"],
                "args": {"output_dir": "data/frames_filled"},
            },
            {
                "id": "compose",
                "stage": "visualize",
                "command": "compose-video",
                "depends_on": ["pad"],
                "args": {},
            },
        ]
    }
    updated = _propagate_inferred_args(manifest)
    pad_args = next(a for a in updated["agents"] if a["id"] == "pad")["args"]
    assert pad_args["output_dir"] == "data/downloaded"
    compose_args = next(a for a in updated["agents"] if a["id"] == "compose")["args"]
    assert compose_args["frames"] == "data/downloaded"


def test_proposal_narrate_links_visual_dependency_and_input():
    manifest = {
        "agents": [
            {
                "id": "compose",
                "stage": "visualize",
                "command": "compose-video",
                "args": {"output": "data/movie.mp4"},
            },
            {
                "id": "story",
                "stage": "narrate",
                "behavior": "proposal",
                "args": {},
            },
        ]
    }
    updated = _propagate_inferred_args(manifest)
    story_agent = next(a for a in updated["agents"] if a["id"] == "story")
    assert story_agent["depends_on"] == ["compose"]
    assert story_agent["args"]["input"] == "data/movie.mp4"


def test_llm_plan_mock(monkeypatch):
    class FakeClient:
        def generate(self, system_prompt, user_prompt):
            assert "stage_behavior_hints" in user_prompt
            return json.dumps(
                {
                    "agents": [
                        {
                            "id": "fetch",
                            "stage": "acquire",
                            "command": "ftp",
                            "args": {"path": "ftp://example.com/data"},
                        },
                        {
                            "id": "tell_story",
                            "stage": "narrate",
                            "command": "describe",
                            "depends_on": ["fetch"],
                            "args": {"input": "data/out.mp4"},
                        },
                    ]
                }
            )

    monkeypatch.setattr(planner_cli, "_load_llm_client", lambda: FakeClient())

    class FakeCaps:
        stage_commands = {
            "acquire": {"ftp": {"positionals": [{"name": "path", "required": True}]}},
            "narrate": {"describe": {"positionals": []}},
        }

    fake_caps = {
        "stage_commands": FakeCaps.stage_commands,
        "stage_aliases": {"acquire": "acquire", "narrate": "narrate"},
        "command_aliases": {
            "acquire": {"ftp": "ftp"},
            "narrate": {"describe": "describe"},
        },
        "prompt": {
            "stage_order": _STAGE_SEQUENCE,
            "example_manifest": _EXAMPLE_MANIFEST,
        },
    }
    monkeypatch.setattr(planner_cli, "_load_capabilities", lambda: fake_caps)
    specs = planner_cli.Planner()._llm_plan("please narrate")
    assert specs[0].command == "ftp"
    assert specs[1].behavior == "proposal"
    assert specs[1].metadata["proposal_options"] == ["swarm", "describe"]


# --- guardrails integration via planner ---

_PASS_RAIL = """\
<rail version="0.1">

<output>
    <list name="agents" description="Pipeline agent definitions">
        <object>
            <string name="id" />
            <string name="stage" />
        </object>
    </list>
</output>

<prompt>
    Validate plan agents.
    {{#block hidden=True}}
    {{input}}
    {{/block}}
</prompt>

</rail>
"""

_STRICT_RAIL = """\
<rail version="0.1">

<output>
    <object name="plan">
        <list name="agents">
            <object>
                <string name="id" />
                <string name="stage" />
                <integer name="priority" description="required priority field" />
            </object>
        </list>
    </object>
</output>

<prompt>
    Validate plan agents have a priority field.
    {{#block hidden=True}}
    {{input}}
    {{/block}}
</prompt>

</rail>
"""


@pytest.mark.guardrails
def test_run_guardrails_validates_manifest(tmp_path):
    """_run_guardrails should accept a valid manifest without raising."""
    os.environ.setdefault("OTEL_SDK_DISABLED", "true")
    pytest.importorskip("guardrails")
    schema = tmp_path / "plan.rail"
    schema.write_text(_PASS_RAIL, encoding="utf-8")
    manifest = {
        "agents": [
            {"id": "fetch", "stage": "acquire"},
            {"id": "narrate", "stage": "narrate"},
        ]
    }
    # Should not raise
    _run_guardrails(str(schema), manifest)


@pytest.mark.guardrails
def test_run_guardrails_rejects_invalid_manifest(tmp_path):
    """_run_guardrails should raise when the manifest fails validation."""
    os.environ.setdefault("OTEL_SDK_DISABLED", "true")
    pytest.importorskip("guardrails")
    schema = tmp_path / "strict.rail"
    schema.write_text(_STRICT_RAIL, encoding="utf-8")
    # Manifest lacks the required "priority" integer field and is not
    # wrapped in a "plan" key, so validation_passed will be False.
    manifest = {
        "agents": [
            {"id": "fetch", "stage": "acquire"},
        ]
    }
    with pytest.raises(RuntimeError, match="validation did not pass"):
        _run_guardrails(str(schema), manifest)


@pytest.mark.guardrails
def test_cmd_plan_with_guardrails_flag(tmp_path, capsys):
    """The --guardrails CLI flag should invoke validation without error."""
    os.environ.setdefault("OTEL_SDK_DISABLED", "true")
    pytest.importorskip("guardrails")
    schema = tmp_path / "plan.rail"
    schema.write_text(_PASS_RAIL, encoding="utf-8")
    ns = Namespace(
        intent="mock swarm plan",
        intent_file=None,
        output="-",
        guardrails=str(schema),
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


@pytest.mark.guardrails
def test_cmd_plan_strict_guardrails_rejects(tmp_path, capsys):
    """--guardrails + --strict should return exit code 2 on failure."""
    os.environ.setdefault("OTEL_SDK_DISABLED", "true")
    pytest.importorskip("guardrails")
    schema = tmp_path / "strict.rail"
    schema.write_text(_STRICT_RAIL, encoding="utf-8")
    ns = Namespace(
        intent="mock swarm plan",
        intent_file=None,
        output="-",
        guardrails=str(schema),
        strict=True,
        memory=None,
        no_clarify=True,
        verbose=False,
    )
    rc = planner_cli._cmd_plan(ns)
    assert rc == 2
    err = capsys.readouterr().err
    assert "guardrails validation failed" in err
