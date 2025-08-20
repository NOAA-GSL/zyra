def test_fallback_timeseries_for_csv_prompts():
    import datavizhub.wizard as wiz

    cmds = wiz._fallback_commands_for_prompt("Plot time series from CSV columns")
    assert isinstance(cmds, list) and cmds, "Expected at least one fallback command"
    assert any(c.startswith("datavizhub ") for c in cmds)
    assert any("visualize timeseries" in c for c in cmds)


def test_fallback_heatmap_for_generic_prompts():
    import datavizhub.wizard as wiz

    cmds = wiz._fallback_commands_for_prompt("Make a nice map")
    assert isinstance(cmds, list) and cmds, "Expected at least one fallback command"
    assert any(c.startswith("datavizhub ") for c in cmds)
    assert any("visualize heatmap" in c for c in cmds)
