# SPDX-License-Identifier: Apache-2.0
def test_select_provider_openai_falls_back_to_mock(monkeypatch):
    import zyra.wizard as wiz

    monkeypatch.setenv("DATAVIZHUB_LLM_PROVIDER", "openai")
    # Simulate missing credential by unsetting the variable entirely
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    client = wiz._select_provider(provider=None, model=None)
    assert isinstance(client, wiz.llm_client.MockClient)


def test_select_provider_mock(monkeypatch):
    import zyra.wizard as wiz

    client = wiz._select_provider(provider="mock", model=None)
    assert isinstance(client, wiz.llm_client.MockClient)


def test_select_provider_gemini_falls_back_to_mock(monkeypatch):
    import zyra.wizard as wiz

    def _boom(*args, **kwargs):  # pragma: no cover - deliberate failure
        raise RuntimeError("boom")

    monkeypatch.setattr("zyra.wizard.llm_client.GeminiVertexClient", _boom)

    client = wiz._select_provider(provider="gemini", model=None)
    assert isinstance(client, wiz.llm_client.MockClient)


def test_select_provider_vertex_alias(monkeypatch):
    import zyra.wizard as wiz

    class FakeGemini:
        name = "gemini"

        def __init__(self, *args, **kwargs):
            pass

    monkeypatch.setattr("zyra.wizard.llm_client.GeminiVertexClient", FakeGemini)

    client = wiz._select_provider(provider="vertex", model=None)
    assert isinstance(client, FakeGemini)


def test_test_llm_connectivity_gemini(monkeypatch):
    import zyra.wizard as wiz

    class FakeGemini:
        def __init__(self, *args, **kwargs):
            pass

        def test_connection(self):
            return True, "✅ Connected to Gemini"

    monkeypatch.setattr("zyra.wizard.llm_client.GeminiVertexClient", FakeGemini)

    ok, msg = wiz._test_llm_connectivity("gemini", None)
    assert ok and "Gemini" in msg
