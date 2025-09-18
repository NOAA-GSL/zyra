# SPDX-License-Identifier: Apache-2.0
import io

import pytest
import yaml


@pytest.mark.cli
def test_critic_structured_output_yaml_mapping(capsys):
    from zyra.cli import main

    rc = main(
        [
            "narrate",
            "swarm",
            "-P",
            "scientific_rigorous",
            "--provider",
            "mock",
            "--critic-structured",
            "--pack",
            "-",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    data = yaml.safe_load(io.StringIO(out))
    pack = data.get("narrative_pack")
    assert isinstance(pack, dict)
    cn = pack.get("outputs", {}).get("critic_notes")
    assert isinstance(cn, dict) and "notes" in cn and isinstance(cn["notes"], str)
