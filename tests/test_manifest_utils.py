# SPDX-License-Identifier: Apache-2.0
import json

from zyra import plugins
from zyra.manifest_utils import load_manifest_with_overlays


def test_manifest_includes_plugins(monkeypatch):
    monkeypatch.setattr(plugins, "_REGISTRY", {})
    plugins.register_command("process", "demo-plugin", description="demo")
    data = load_manifest_with_overlays(include_plugins=True)
    assert "process demo-plugin" in data


def test_manifest_includes_overlay_file(tmp_path, monkeypatch):
    overlay = tmp_path / "overlay.json"
    overlay.write_text(json.dumps({"process overlay-cmd": {"returns": "path"}}))
    data = load_manifest_with_overlays(include_plugins=False, overlay_path=overlay)
    assert "process overlay-cmd" in data
