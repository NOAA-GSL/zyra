def test_select_provider_openai_falls_back_to_mock(monkeypatch):
    import datavizhub.wizard as wiz

    monkeypatch.setenv("DATAVIZHUB_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "")  # force missing key

    client = wiz._select_provider(provider=None, model=None)
    assert isinstance(client, wiz.llm_client.MockClient)


def test_select_provider_mock(monkeypatch):
    import datavizhub.wizard as wiz

    client = wiz._select_provider(provider="mock", model=None)
    assert isinstance(client, wiz.llm_client.MockClient)
