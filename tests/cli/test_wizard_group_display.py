def test_group_title_in_option_completion_meta(monkeypatch):
    # Build a small manifest with groups metadata
    cap = {
        "visualize heatmap": {
            "description": "",
            "groups": [
                {"title": "Input Options", "options": ["--input"]},
                {"title": "Output Options", "options": ["--output"]},
            ],
            "options": {
                "--input": {"help": "Path to input", "path_arg": True},
                "--output": {
                    "help": "Path to output",
                    "path_arg": True,
                    "default": "out.png",
                },
            },
        }
    }
    import zyra.wizard as wiz

    comp = wiz._WizardCompleter(cap)

    class Doc:
        text_before_cursor = "visualize heatmap --o"

        @staticmethod
        def get_word_before_cursor(WORD=False):
            return "--o"

    # Collect completions
    got = list(comp.get_completions(Doc, None))  # type: ignore[arg-type]
    # Ensure meta includes the group title and default
    metas = {c.text: str(c.display_meta) for c in got}
    assert "(Output Options)" in (metas.get("--output") or "")
    assert "default: out.png" in (metas.get("--output") or "")
