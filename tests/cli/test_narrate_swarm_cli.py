# SPDX-License-Identifier: Apache-2.0
import pytest


@pytest.mark.cli
def test_narrate_swarm_preset_list(capsys):
    from zyra.cli import main

    rc = main(["narrate", "swarm", "-P", "help"])
    assert rc == 0
    out = capsys.readouterr().out
    # Should list packaged presets (added by this change)
    assert "kids_policy_basic" in out
    assert "scientific_rigorous" in out


@pytest.mark.cli
def test_narrate_swarm_unknown_preset_exit_2(capsys):
    from zyra.cli import main

    rc = main(["narrate", "swarm", "-P", "kid_policy_basic"])  # typo
    assert rc == 2
    err = capsys.readouterr().err
    assert "unknown preset" in err
    assert "did you mean" in err


@pytest.mark.cli
def test_narrate_swarm_pack_stdout_yaml(capsys):
    from zyra.cli import main

    rc = main(["narrate", "swarm", "-P", "kids_policy_basic", "--pack", "-"])
    assert rc == 0
    out = capsys.readouterr().out
    assert out.lstrip().startswith("narrative_pack:")
    # From kids_policy_basic audiences
    assert "kids_version" in out and "policy_version" in out
