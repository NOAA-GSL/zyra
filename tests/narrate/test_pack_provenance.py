# SPDX-License-Identifier: Apache-2.0
import io

import pytest
import yaml


@pytest.mark.cli
def test_pack_contains_provenance(capsys):
    from zyra.cli import main

    rc = main(["narrate", "swarm", "-P", "kids_policy_basic", "--pack", "-"])
    assert rc == 0
    out = capsys.readouterr().out
    data = yaml.safe_load(io.StringIO(out))
    assert isinstance(data, dict)
    pack = data.get("narrative_pack")
    assert pack and isinstance(pack, dict)
    prov = pack.get("provenance")
    assert isinstance(prov, list) and len(prov) >= 3
    agents = {p.get("agent") for p in prov}
    # audience_adapter should appear when audiences exist
    assert {"summary", "context", "critic", "audience_adapter"}.issubset(agents)
    # Each entry has started/prompt_ref and non-negative duration
    for p in prov:
        assert "started" in p and p["started"]
        assert "prompt_ref" in p and p["prompt_ref"].startswith(
            "zyra.assets/llm/prompts/narrate/"
        )
        assert int(p.get("duration_ms", 0)) >= 0
