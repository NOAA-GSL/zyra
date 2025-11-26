# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import sys
import types

from zyra.wizard.llm_client import GeminiVertexClient, OllamaClient


def _install_fake_google(monkeypatch, project: str | None = "adc-project"):
    """Install lightweight google.auth stubs to avoid real dependency."""
    dummy_google = types.ModuleType("google")
    dummy_auth = types.ModuleType("google.auth")
    dummy_transport = types.ModuleType("google.auth.transport")
    dummy_requests = types.ModuleType("google.auth.transport.requests")

    class DummyCred:
        def __init__(self):
            self.valid = True
            self.token = "dummy-token"

        def refresh(self, request):
            self.token = "dummy-token"

    def default(scopes=None):
        return DummyCred(), project

    class DummyRequest:
        def __init__(self, *args, **kwargs):
            pass

    dummy_auth.default = default
    dummy_requests.Request = DummyRequest
    dummy_transport.requests = dummy_requests
    dummy_auth.transport = dummy_transport
    dummy_google.auth = dummy_auth

    monkeypatch.setitem(sys.modules, "google", dummy_google)
    monkeypatch.setitem(sys.modules, "google.auth", dummy_auth)
    monkeypatch.setitem(sys.modules, "google.auth.transport", dummy_transport)
    monkeypatch.setitem(sys.modules, "google.auth.transport.requests", dummy_requests)


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


def test_gemini_api_key_error_fallback(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "dummy-key")

    class DummySession:
        def post(self, *args, **kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr(GeminiVertexClient, "_get_session", lambda self: DummySession())
    c = GeminiVertexClient(model="gemini-1.5-flash")
    out = c.generate("sys", "user")
    assert "Gemini error: fallback response used" in out


def test_gemini_api_key_test_connection(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "dummy-key")

    class DummyResp:
        def raise_for_status(self):
            return None

        def json(self):
            return {}

    class DummySession:
        def get(self, *args, **kwargs):
            return DummyResp()

        def post(self, *args, **kwargs):
            return DummyResp()

    monkeypatch.setattr(GeminiVertexClient, "_get_session", lambda self: DummySession())
    c = GeminiVertexClient(model="gemini-1.5-flash")
    ok, msg = c.test_connection()
    assert ok
    assert "Gemini" in msg


def test_gemini_vertex_uses_adc_defaults(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    _install_fake_google(monkeypatch, project="adc-proj")
    c = GeminiVertexClient(model=None, base_url="https://vertex.example")
    assert c.project == "adc-proj"
    assert c.location == "us-central1"
    headers = c._auth_headers()
    assert headers["Authorization"] == "Bearer dummy-token"


def test_gemini_vertex_requires_project(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    _install_fake_google(monkeypatch, project=None)
    try:
        GeminiVertexClient(model=None)
    except RuntimeError as exc:
        assert "VERTEX_PROJECT" in str(exc)
    else:  # pragma: no cover - ensure we fail if no exception
        raise AssertionError("expected RuntimeError for missing project")
