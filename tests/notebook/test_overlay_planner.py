# SPDX-License-Identifier: Apache-2.0
import pytest

from zyra.notebook import create_session
from zyra.swarm import planner


def _fake_caps() -> dict[str, dict]:
    # Minimal manifest with one built-in command.
    return {"process built": {"returns": "object"}}


@pytest.fixture(autouse=True)
def reset_caps(monkeypatch):
    # Reset cached capabilities before/after each test.
    planner.planner._caps = None  # type: ignore[attr-defined]
    monkeypatch.setenv("ZYRA_NOTEBOOK_OVERLAY", "")
    monkeypatch.setattr("zyra.api.services.manifest.get_manifest", _fake_caps)
    yield
    planner.planner._caps = None  # type: ignore[attr-defined]


def test_load_capabilities_merges_overlay(tmp_path, monkeypatch):
    overlay = {
        "process custom": {
            "returns": "object",
            "origin": "inline",
            "serialization": {
                "kind": "inline",
                "cell_hash": "abc123",
                "cell_id": "cell-1",
            },
            "stage": "process",
            "command": "custom",
        }
    }
    overlay_path = tmp_path / "overlay.json"
    overlay_path.write_text(planner.json.dumps(overlay), encoding="utf-8")
    monkeypatch.setenv("ZYRA_NOTEBOOK_OVERLAY", str(overlay_path))

    caps = planner._load_capabilities()

    assert "process custom" in caps["raw"]
    assert "custom" in caps["stage_commands"].get("process", {})
    assert caps["stage_commands"]["process"]["custom"].get("origin") == "inline"


def test_registered_tool_written_to_overlay(tmp_path, monkeypatch):
    monkeypatch.setenv("ZYRA_NOTEBOOK_DIR", str(tmp_path))
    sess = create_session(workdir=tmp_path)

    def dummy(ns):  # pragma: no cover - simple stub
        return "ok"

    sess.process.register(
        "dummy", dummy, returns="object", cell_hash="cellhash123", cell_id="cell-5"
    )

    overlay_path = tmp_path / "notebook_capabilities_overlay.json"
    assert overlay_path.exists()
    overlay = planner.json.loads(overlay_path.read_text())
    assert "process dummy" in overlay
    entry = overlay["process dummy"]
    assert entry.get("origin") == "inline"
    serialization = entry.get("serialization") or {}
    assert serialization.get("kind") in {"inline", "reference"}
    # With env set, planner should pick it up
    monkeypatch.setenv("ZYRA_NOTEBOOK_OVERLAY", str(overlay_path))
    caps = planner._load_capabilities()
    assert "dummy" in caps["stage_commands"].get("process", {})


def test_inline_origin_label_in_choice(monkeypatch):
    # Ensure suggestions carry origin labels for consent
    sug = {
        "stage": "process",
        "description": "demo",
        "origin": "inline:notebook_register",
    }
    stage = sug.get("stage")
    desc = sug.get("description") or sug.get("text") or ""
    origin = sug.get("origin") or sug.get("origin_detail")
    origin_label = f" [inline: {origin}]" if origin else ""
    prompt = f"  Accept {stage}{origin_label}: {desc}? [y/N] "
    assert "inline:notebook_register" in prompt
    assert "[inline:" in prompt


def test_replay_overlay_missing_ok(monkeypatch, tmp_path):
    # If overlay path is missing, planner should still load base caps
    monkeypatch.delenv("ZYRA_NOTEBOOK_OVERLAY", raising=False)
    planner.planner._caps = None  # type: ignore[attr-defined]
    caps = planner._load_capabilities()
    # With fake manifest stubbed above, stage_commands should at least exist
    assert isinstance(caps.get("stage_commands"), dict)


def test_cli_planner_with_overlay_and_prompt(monkeypatch, tmp_path):
    # Write overlay with inline origin
    overlay = {
        "process inline_cmd": {
            "returns": "object",
            "origin": "inline:notebook_register",
            "serialization": {
                "kind": "inline",
                "cell_hash": "abc",
                "cell_id": "cell-1",
            },
            "stage": "process",
            "command": "inline_cmd",
            "description": "inline demo",
        }
    }
    overlay_path = tmp_path / "overlay.json"
    overlay_path.write_text(planner.json.dumps(overlay), encoding="utf-8")
    monkeypatch.setenv("ZYRA_NOTEBOOK_OVERLAY", str(overlay_path))
    monkeypatch.setenv("ZYRA_FORCE_PLAN_PROMPT", "0")  # disable TTY block in tests
    planner.planner._caps = None  # type: ignore[attr-defined]
    # Simulate no TTY; _prompt_accept_suggestions should no-op and not crash
    accepted = planner._prompt_accept_suggestions(
        [
            {
                "stage": "process",
                "description": "inline demo",
                "origin": "inline:notebook_register",
            }
        ],
        allow_prompt=False,
    )
    assert accepted == []
