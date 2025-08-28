from __future__ import annotations

from zyra.wizard.llm_client import OllamaClient


def test_ollama_error_no_leak_by_default(monkeypatch):
    # Ensure hints are disabled
    # Clear the supported env variants used by env_bool
    monkeypatch.delenv("ZYRA_LLM_ERROR_HINTS", raising=False)
    monkeypatch.delenv("DATAVIZHUB_LLM_ERROR_HINTS", raising=False)
    c = OllamaClient(model="mistral", base_url="http://localhost:11434")
    out = c.generate("sys", "user")
    # Should include generic fallback but no exception details or host URLs
    assert "Ollama error: fallback response used" in out
    assert "localhost" not in out and "http://" not in out
    assert "Ensure the server is started" not in out


def test_ollama_error_hints_enabled(monkeypatch):
    monkeypatch.setenv("ZYRA_LLM_ERROR_HINTS", "1")
    c = OllamaClient(model="mistral", base_url="http://localhost:11434")
    out = c.generate("sys", "user")
    assert "Ollama error: fallback response used" in out
    # Hints should appear when enabled
    assert "Ensure the server is started" in out
