# SPDX-License-Identifier: Apache-2.0
import pytest
import yaml


@pytest.mark.cli
def test_exit_code_1_on_critical_failure(tmp_path, capsys):
    from zyra.cli import main

    # Create a config where summary depends on a missing agent → unmet deps → failed summary
    cfg = tmp_path / "swarm.yaml"
    cfg.write_text(
        yaml.safe_dump(
            {
                "agents": ["summary", "critic"],
                "graph": [{"from": ["missing"], "to": ["summary"]}],
            }
        ),
        encoding="utf-8",
    )
    rc = main(
        [
            "narrate",
            "swarm",
            "--swarm-config",
            str(cfg),
            "--provider",
            "mock",
            "--pack",
            "-",
        ]
    )
    # Pack should be printed but exit code should be 1
    assert rc == 1
    out = capsys.readouterr().out
    assert out.lstrip().startswith("narrative_pack:")
