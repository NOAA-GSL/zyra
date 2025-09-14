# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from zyra.pipeline_runner import _stage_group_alias
from zyra.wizard.manifest import build_manifest


def test_stage_alias_normalization():
    assert _stage_group_alias("import") == "acquire"
    assert _stage_group_alias("ingest") == "acquire"
    assert _stage_group_alias("render") == "visualize"
    assert _stage_group_alias("disseminate") == "decimate"
    assert _stage_group_alias("export") == "decimate"
    assert _stage_group_alias("decimation") == "decimate"


def test_manifest_includes_alias_groups_and_skeletons():
    m = build_manifest()
    # egress aliases
    assert any(k.startswith("disseminate ") for k in m)
    assert any(k.startswith("export ") for k in m)
    # visualize alias
    assert any(k.startswith("render ") for k in m)
    # acquire alias
    assert any(k.startswith("import ") for k in m)
    # skeleton groups are present with at least one command
    assert any(k.startswith("simulate ") for k in m)
    assert any(k.startswith("decide ") for k in m)
    assert any(k.startswith("optimize ") for k in m)  # alias of decide
    assert any(k.startswith("narrate ") for k in m)
    assert any(k.startswith("verify ") for k in m)
