# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
from pathlib import Path

from zyra.core.capabilities_loader import (
    INDEX_FILENAME,
    compute_capabilities_hash,
    load_capabilities,
    load_domains,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_load_from_directory_with_alias(tmp_path):
    caps_dir = tmp_path / "caps"
    data_acq = {"acquire http": {"description": "Fetch"}}
    data_viz = {"visualize heatmap": {"description": "Heatmap"}}
    _write_json(caps_dir / "acquire.json", data_acq)
    _write_json(caps_dir / "visualize.json", data_viz)
    index = {
        "version": "1.0",
        "generated_at": "2025-01-01T00:00:00Z",
        "generator": "test",
        "domains": {
            "acquire": "acquire.json",
            "visualize": {"file": "visualize.json", "aliases": ["render"]},
        },
        "aliases": {"import": "acquire"},
    }
    _write_json(caps_dir / INDEX_FILENAME, index)

    all_domains = load_domains(caps_dir)
    assert set(all_domains) == {"acquire", "visualize"}
    assert load_capabilities(caps_dir)["visualize heatmap"]["description"] == "Heatmap"

    render_domain = load_domains(caps_dir, domain="render")
    assert "visualize" in render_domain and len(render_domain) == 1

    import_caps = load_capabilities(caps_dir, domain="import")
    assert list(import_caps) == ["acquire http"]


def test_load_from_single_file(tmp_path):
    manifest = {
        "acquire http": {"description": "Fetch"},
        "visualize heatmap": {"description": "Heatmap"},
    }
    legacy_path = tmp_path / "zyra_capabilities.json"
    _write_json(legacy_path, manifest)

    combined = load_capabilities(legacy_path)
    assert combined == manifest

    domains = load_domains(legacy_path, domain="visualize")
    assert "visualize" in domains
    assert list(domains["visualize"]) == ["visualize heatmap"]


def test_compute_capabilities_hash_is_deterministic():
    caps_a = {"b": {"description": "two"}, "a": {"description": "one"}}
    caps_b = {"a": {"description": "one"}, "b": {"description": "two"}}
    assert compute_capabilities_hash(caps_a) == compute_capabilities_hash(caps_b)
