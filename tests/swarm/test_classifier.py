# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json

from zyra.swarm.classifier import SemanticClassifier


class FakeClient:
    def __init__(self, payload: dict[str, str]):
        self.payload = payload

    def generate(
        self, system_prompt: str, user_prompt: str
    ) -> str:  # pragma: no cover - trivial
        data = json.loads(user_prompt)
        assert "intent" in data
        return json.dumps({"context_tags": [self.payload]})


def test_classifier_uses_llm(monkeypatch):
    client = FakeClient({"tag": "drought_risk", "confidence": 0.9})
    classifier = SemanticClassifier(client=client)
    tags = classifier.classify("Download drought frames", plan_summary=None)
    assert tags[0]["tag"] == "drought_risk"
    assert tags[0]["confidence"] == 0.9


def test_classifier_fallback_keywords():
    classifier = SemanticClassifier(client=None)
    tags = classifier.classify("Weekly drought risk animation", plan_summary=None)
    assert tags[0]["tag"] in {"drought_risk", "map_viz"}


def test_classifier_empty_text_returns_generic():
    classifier = SemanticClassifier(client=None)
    tags = classifier.classify("", plan_summary=None)
    assert tags == [{"tag": "generic", "confidence": 0.2}]
