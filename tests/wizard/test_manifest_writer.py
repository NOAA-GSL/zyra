# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json

from zyra.wizard.manifest import save_manifest


def test_save_manifest_directory_and_legacy(tmp_path):
    out_dir = tmp_path / "caps"
    legacy_path = tmp_path / "legacy.json"

    save_manifest(str(out_dir), include_legacy=True, legacy_path=str(legacy_path))

    index = out_dir / "zyra_capabilities_index.json"
    assert index.exists()
    assert legacy_path.exists()

    # Ensure at least one domain file was created under the directory
    domain_files = list(p for p in out_dir.glob("*.json") if p.name != index.name)
    assert domain_files, "Expected per-domain manifest files to be generated"


def test_save_manifest_legacy_file(tmp_path):
    legacy_path = tmp_path / "caps.json"
    save_manifest(str(legacy_path))
    assert legacy_path.exists()
    assert legacy_path.is_file()


def test_generated_at_stable_across_runs(tmp_path):
    out_dir = tmp_path / "stable_caps"
    save_manifest(str(out_dir))
    index_path = out_dir / "zyra_capabilities_index.json"
    first = json.loads(index_path.read_text())
    save_manifest(str(out_dir))
    second = json.loads(index_path.read_text())
    assert first.get("generated_at") == second.get("generated_at")
