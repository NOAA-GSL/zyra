# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
from typing import Any

from zyra.swarm import value_engine


def test_narrate_suggestion_uses_classifier(monkeypatch):
    class Dummy:
        def classify(self, intent, plan_summary):  # pragma: no cover - simple stub
            return [{"tag": "drought_risk", "confidence": 0.9}]

    monkeypatch.setattr(value_engine, "_CLASSIFIER", Dummy())

    manifest = {
        "agents": [
            {"id": "compose", "stage": "visualize"},
        ]
    }
    suggestions = value_engine.suggest(manifest, intent="Download drought frames")
    narrate = next(sug for sug in suggestions if sug["stage"] == "narrate")
    assert "drought" in narrate["intent_text"].lower()


def test_classifier_failure_does_not_break(monkeypatch):
    class Broken:
        def classify(self, intent, plan_summary):
            raise RuntimeError("boom")

    monkeypatch.setattr(value_engine, "_CLASSIFIER", Broken())
    manifest = {"agents": []}
    suggestions = value_engine.suggest(manifest, intent="")
    assert isinstance(suggestions, list)


def test_llm_suggestions_include_summary(monkeypatch):
    captured: dict[str, Any] = {}

    class FakeClient:
        def generate(self, system, user):  # pragma: no cover - simple stub
            captured["system"] = system
            captured["user"] = json.loads(user)
            return json.dumps(
                [
                    {
                        "stage": "process",
                        "description": "Add anomaly detection",
                        "confidence": 0.9,
                    }
                ]
            )

    monkeypatch.setattr(value_engine, "_load_llm_client", lambda: FakeClient())
    monkeypatch.setattr(value_engine, "_capability_hints", lambda: [])
    manifest = {"agents": []}
    out = value_engine._llm_suggestions(  # type: ignore[attr-defined]
        manifest,
        intent="Analyze imagery",
        plan_summary="Download drought maps",
        tags=[{"tag": "drought_risk", "confidence": 0.9}],
    )

    assert captured["user"]["plan_summary"] == "Download drought maps"
    assert captured["user"]["context_tags"][0]["tag"] == "drought_risk"
    assert out[0]["stage"] == "process"


def test_bundle_suggestions_added_for_drought(monkeypatch):
    class Dummy:
        def classify(self, intent, plan_summary):
            return [{"tag": "drought_risk", "confidence": 0.9}]

    monkeypatch.setattr(value_engine, "_CLASSIFIER", Dummy())
    monkeypatch.setattr(value_engine, "_load_llm_client", lambda: None)
    manifest = {"agents": [{"id": "viz", "stage": "visualize"}]}
    suggestions = value_engine.suggest(manifest, intent="Weekly drought risk")
    stages = {s["stage"] for s in suggestions}
    assert "process" in stages  # bundle analysis stage


def test_verify_suggestion_uses_missing_frames(tmp_path, monkeypatch):
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    (frames_dir / "frame_202401010000.png").write_text("a")
    (frames_dir / "frame_202401010100.png").write_text("b")

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
                },
            }
        ]
    }
    monkeypatch.setattr(
        value_engine,
        "_CLASSIFIER",
        type("Dummy", (), {"classify": lambda self, intent, summary: []})(),
    )
    suggestions = value_engine.suggest(manifest, intent="Analyze frames")
    verify = next(s for s in suggestions if s["stage"] == "verify")
    desc = verify["description"].lower()
    assert "missing" in desc and "examples" in desc
    assert "agent_template" in verify
