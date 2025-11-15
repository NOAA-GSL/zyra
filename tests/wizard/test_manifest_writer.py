# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json

from zyra.wizard.manifest import (
    CANONICAL_DOMAINS,
    DOMAIN_ALIAS_MAP,
    save_manifest,
)


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


def test_only_canonical_domains_written(tmp_path):
    out_dir = tmp_path / "canonical_caps"
    save_manifest(str(out_dir))
    domain_files = {
        p.name
        for p in out_dir.glob("*.json")
        if p.name != "zyra_capabilities_index.json"
    }
    expected_files = {f"{dom}.json" for dom in CANONICAL_DOMAINS}
    assert domain_files == expected_files

    index = json.loads((out_dir / "zyra_capabilities_index.json").read_text())
    aliases = index.get("aliases") or {}
    for alias, canonical in DOMAIN_ALIAS_MAP.items():
        assert aliases.get(alias) == canonical
        dom_entry = index.get("domains", {}).get(canonical)
        if isinstance(dom_entry, dict):
            assert alias in dom_entry.get("aliases", [])
