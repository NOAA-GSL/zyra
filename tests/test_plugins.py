# SPDX-License-Identifier: Apache-2.0
from zyra import plugins


def test_plugin_registry_lists_registered(monkeypatch):
    monkeypatch.setattr(plugins, "_REGISTRY", {})
    plugins.register_command("acquire", "demo-acquire")
    listed = plugins.list_registered()
    assert "acquire" in listed
    assert "demo-acquire" in listed["acquire"]


def test_help_epilog_includes_plugins(monkeypatch):
    monkeypatch.setattr(plugins, "_REGISTRY", {})
    plugins.register_command("process", "demo-process")
    epilog = plugins.help_epilog()
    assert epilog is not None
    assert "process" in epilog
    assert "demo-process" in epilog


def test_plugin_stage_normalization_spaces(monkeypatch):
    monkeypatch.setattr(plugins, "_REGISTRY", {})
    plugins.register_command("process transform", "demo")
    overlay = plugins.manifest_overlay()
    # Stage normalization keeps space, not hyphen, in manifest keys
    assert "process transform demo" in overlay


def test_plugin_processing_alias_resolves_to_process(monkeypatch):
    monkeypatch.setattr(plugins, "_REGISTRY", {})
    plugins.register_command("processing", "alias-demo")
    overlay = plugins.manifest_overlay()
    # Alias resolves to process
    assert "process alias-demo" in overlay
