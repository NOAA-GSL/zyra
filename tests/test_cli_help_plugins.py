# SPDX-License-Identifier: Apache-2.0
import pytest

import zyra.plugins as plugins


def test_cli_help_includes_registered_plugins(monkeypatch, capsys):
    # Isolate registry for the test
    monkeypatch.setattr(plugins, "_REGISTRY", {})
    plugins.register_command("process", "demo-help")
    import zyra.cli as cli

    with pytest.raises(SystemExit):
        cli.main(["--help"])
    output = capsys.readouterr().out
    assert "Plugin commands:" in output
    assert "process: demo-help" in output
