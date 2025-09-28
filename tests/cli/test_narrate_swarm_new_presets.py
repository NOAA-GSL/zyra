# SPDX-License-Identifier: Apache-2.0
import pytest


@pytest.mark.cli
def test_new_presets_listed(capsys):
    from zyra.cli import main

    rc = main(["narrate", "swarm", "-P", "help"])
    assert rc == 0
    out = capsys.readouterr().out
    for name in [
        "kids_story",
        "policy_brief",
        "multi_audience_report",
        "accessibility_default",
        "scientific_lite",
        "kids_policy_dual",
    ]:
        assert name in out


@pytest.mark.cli
def test_run_multi_audience_report_stdout_yaml(capsys):
    from zyra.cli import main

    rc = main(
        [
            "narrate",
            "swarm",
            "-P",
            "multi_audience_report",
            "--provider",
            "mock",
            "--pack",
            "-",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert out.lstrip().startswith("narrative_pack:")
    # Expect multiple audience variants present
    assert (
        "kids_version" in out
        and "policy_version" in out
        and "scientific_version" in out
    )


@pytest.mark.cli
def test_run_policy_brief_stdout_yaml(capsys):
    from zyra.cli import main

    rc = main(
        [
            "narrate",
            "swarm",
            "-P",
            "policy_brief",
            "--provider",
            "mock",
            "--pack",
            "-",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert out.lstrip().startswith("narrative_pack:")
    # Expect policy variant and edited output present
    assert "policy_version" in out and "edited" in out
