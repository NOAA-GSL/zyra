def test_tokenizer_extracts_choices_for_options():
    import zyra.wizard as wiz

    cap = {
        "visualize heatmap": {
            "description": "",
            "options": {
                "--cmap": {"help": "", "choices": ["viridis", "plasma", "magma"]},
                "--output": {"help": "", "path_arg": True},
            },
        }
    }
    toks = wiz._tokenize_manifest(cap)
    # Expect choices mapped for the specific command
    oc = toks["opt_choices"]
    # Ensure top-level token is present, but subcommand isn't treated as a top-level command
    assert ("visualize" in toks["first_tokens"]) and ("heatmap" not in toks["commands"])
    # opt_choices uses keys (first, second)
    choices = set()
    for key, mapping in oc.items():
        if key == ("visualize", "heatmap"):
            choices = mapping.get("--cmap", set())
            break
    assert choices == {"viridis", "plasma", "magma"}
