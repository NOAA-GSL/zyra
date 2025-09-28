# SPDX-License-Identifier: Apache-2.0
import pytest
import yaml


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

    rc = main(
        ["narrate", "swarm", "-P", "kid_policy_basic"]
    )  # typo of kids_policy_basic
    assert rc == 2
    err = capsys.readouterr().err
    assert "unknown preset" in err
    assert "did you mean" in err


@pytest.mark.cli
def test_narrate_swarm_pack_stdout_yaml(capsys):
    from zyra.cli import main

    rc = main(["narrate", "swarm", "-P", "kids_policy_basic", "--pack", "-"])
    assert rc == 0
    captured = capsys.readouterr()
    out = captured.out
    assert out.lstrip().startswith("narrative_pack:")
    pack = yaml.safe_load(out).get("narrative_pack")
    assert pack["inputs"]["rubric"].endswith("critic.yaml")
    assert pack["inputs"].get("preset") == "kids_policy_basic"
    outputs = pack.get("outputs", {})
    # From kids_policy_basic audiences
    assert "kids_version" in outputs and "policy_version" in outputs


@pytest.mark.cli
def test_narrate_swarm_rubric_override(tmp_path, capsys):
    from zyra.cli import main

    rubric_path = tmp_path / "custom_rubric.yaml"
    rubric_path.write_text("- Clarity\n- Accuracy\n", encoding="utf-8")

    rc = main(
        [
            "narrate",
            "swarm",
            "-P",
            "kids_policy_basic",
            "--rubric",
            str(rubric_path),
            "--pack",
            "-",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    pack = yaml.safe_load(out).get("narrative_pack")
    assert pack["inputs"]["rubric"] == str(rubric_path)


@pytest.mark.cli
def test_narrate_swarm_missing_rubric_exits_2(capsys):
    from zyra.cli import main

    rc = main(
        [
            "narrate",
            "swarm",
            "-P",
            "kids_policy_basic",
            "--rubric",
            "does-not-exist.yaml",
        ]
    )
    assert rc == 2
    err = capsys.readouterr().err
    assert "rubric file not found" in err
