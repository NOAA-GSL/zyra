def test_context_includes_enriched_option_details(monkeypatch, capsys):
    import datavizhub.wizard as wiz

    # Override manifest loader to a tiny enriched manifest
    cap = {
        "visualize heatmap": {
            "description": "Render a heatmap",
            "doc": "Docstring here",
            "epilog": "Epilog text",
            "options": {
                "--cmap": {"help": "Colormap", "choices": ["viridis", "plasma"], "default": "viridis"},
                "--input": {"help": "Path", "path_arg": True},
            },
        }
    }
    monkeypatch.setattr(wiz, "_load_capabilities_manifest", lambda: cap)

    seen = {}

    def fake_generate(system_prompt: str, user_prompt: str) -> str:
        seen["user_prompt"] = user_prompt
        return "```bash\ndatavizhub --help\n```"

    from datavizhub.wizard import llm_client

    monkeypatch.setattr(llm_client.MockClient, "generate", staticmethod(fake_generate))

    rc = wiz._handle_prompt(
        "heatmap with cmap",
        provider="mock",
        model=None,
        dry_run=True,
        assume_yes=True,
        max_commands=None,
        logfile=None,
        session=wiz.SessionState(),
    )
    assert rc == 0
    up = seen["user_prompt"]
    # Should contain choices and default info in the context block
    assert "choices: viridis, plasma" in up
    assert "default: viridis" in up

