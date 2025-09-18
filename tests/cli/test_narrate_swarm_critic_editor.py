# SPDX-License-Identifier: Apache-2.0
import io

import pytest
import yaml


@pytest.mark.cli
def test_scientific_preset_includes_critic_and_editor(capsys):
    from zyra.cli import main

    rc = main(
        [
            "narrate",
            "swarm",
            "-P",
            "scientific_rigorous",
            "--provider",
            "mock",
            "--pack",
            "-",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    data = yaml.safe_load(io.StringIO(out))
    pack = data.get("narrative_pack")
    outputs = pack.get("outputs", {})
    assert "critic_notes" in outputs
    assert "edited" in outputs
