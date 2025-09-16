# SPDX-License-Identifier: Apache-2.0
import io

import pytest
import yaml


@pytest.mark.cli
def test_narrate_swarm_input_json(tmp_path, capsys):
    from zyra.cli import main

    data = {"title": "Climate Report", "value": 42}
    ip = tmp_path / "climate.json"
    ip.write_text(yaml.safe_dump(data), encoding="utf-8")

    rc = main(
        [
            "narrate",
            "swarm",
            "-P",
            "kids_policy_basic",
            "--provider",
            "mock",
            "--input",
            str(ip),
            "--pack",
            "-",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    y = yaml.safe_load(io.StringIO(out))
    pack = y.get("narrative_pack")
    assert pack["inputs"]["file"] == str(ip)
    assert pack["inputs"]["format"] in ("json", "yaml", "text")
