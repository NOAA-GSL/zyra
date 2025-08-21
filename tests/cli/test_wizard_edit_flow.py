"""Tests for Wizard edit flow and manifest tokenization."""


def test_wizard_edit_flow_sanitizes_and_runs(monkeypatch, capsys):
    import zyra.wizard as wiz
    from zyra.cli import main
    from zyra.wizard import llm_client

    # Force no prompt_toolkit and no external editor
    monkeypatch.setattr(wiz, "PTK_AVAILABLE", False, raising=False)
    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.delenv("EDITOR", raising=False)

    # Mock LLM to suggest a simple command
    monkeypatch.setattr(
        llm_client.MockClient,
        "generate",
        staticmethod(lambda s, u: "```bash\ndatavizhub --help\n```"),
    )

    # Simulate user editing: provide an unsafe line and a commented command
    inputs = iter(
        [
            "rm -rf /",  # unsafe - should be dropped
            "datavizhub visualize heatmap --input in.nc --output out.png # note",  # safe
            "",  # end of edit
        ]
    )
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))

    executed = []

    def fake_run_one(cmd: str) -> int:
        executed.append(cmd)
        return 0

    monkeypatch.setattr(wiz, "_run_one", fake_run_one)

    # Ensure we pick edit mode
    monkeypatch.setenv("DATAVIZHUB_WIZARD_EDITOR_MODE", "always")

    rc = main(["wizard", "--provider", "mock", "--prompt", "x"])
    assert rc == 0

    # Only the sanitized datavizhub line should run (no inline comment)
    assert executed == ["datavizhub visualize heatmap --input in.nc --output out.png"]


def test_tokenize_manifest_basic():
    import zyra.wizard as wiz

    cap = wiz._load_capabilities_manifest()
    assert cap is not None
    toks = wiz._tokenize_manifest(cap)
    # Expect some broad tokens
    assert "acquire" in toks["first_tokens"]
    assert isinstance(toks["options"], set)
    # Common option presence
    assert any(
        (o in ("--output", "-o")) or o.startswith("--output") for o in toks["options"]
    )
