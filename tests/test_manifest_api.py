# SPDX-License-Identifier: Apache-2.0
from zyra import plugins
from zyra.manifest import Manifest


def test_manifest_lists_commands():
    manifest = Manifest.load(include_plugins=False)
    commands = manifest.list_commands()
    assert any(cmd.startswith("acquire ") for cmd in commands)


def test_manifest_merges_plugins(monkeypatch):
    monkeypatch.setattr(plugins, "_REGISTRY", {})
    plugins.register_command("process", "demo", description="demo command")
    manifest = Manifest.load(include_plugins=True)
    commands = manifest.list_commands(stage="process")
    assert "process demo" in commands


def test_manifest_describe_specific_command():
    manifest = Manifest.load(include_plugins=False)
    detail = manifest.describe(command="process convert-format")
    assert detail.get("name") == "process convert-format"
    assert detail.get("meta")


def test_manifest_stage_alias_processing():
    manifest = Manifest.load(stage="processing", include_plugins=False)
    commands = manifest.list_commands()
    assert commands  # alias resolved to process
    assert all(cmd.startswith("process ") for cmd in commands)
