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
