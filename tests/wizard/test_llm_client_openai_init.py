# SPDX-License-Identifier: Apache-2.0
import pytest


def test_openai_client_requires_api_key(monkeypatch):
    # Force empty API key to simulate missing credentials even if host env has one
    monkeypatch.setenv("OPENAI_API_KEY", "")
    from zyra.wizard.llm_client import OpenAIClient

    with pytest.raises(RuntimeError):
        OpenAIClient(model="gpt-4o-mini")


def test_openai_client_initializes_with_api_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-123")
    from zyra.wizard.llm_client import OpenAIClient

    c = OpenAIClient(model="gpt-4o-mini")
    assert c.model == "gpt-4o-mini"
    # Do not call generate() here (would require network); just verify init succeeds
