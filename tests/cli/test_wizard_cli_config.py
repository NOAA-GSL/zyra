# SPDX-License-Identifier: Apache-2.0
import yaml


def _write_yaml(path, data):
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _monkeypatch_generators(monkeypatch):
    from zyra.wizard import llm_client

    def gen_openai(system_prompt: str, user_prompt: str) -> str:
        return """
```bash
$ datavizhub from-openai
```
""".strip()

    def gen_mock(system_prompt: str, user_prompt: str) -> str:
        return """
```bash
$ datavizhub from-mock
```
""".strip()

    monkeypatch.setattr(llm_client.OpenAIClient, "generate", staticmethod(gen_openai))
    monkeypatch.setattr(llm_client.MockClient, "generate", staticmethod(gen_mock))


def test_config_file_sets_default_provider(tmp_path, monkeypatch, capsys):
    from zyra.cli import main

    # Point HOME to temp and write config with provider: mock
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    cfg = home / ".datavizhub_wizard.yaml"
    _write_yaml(cfg, {"provider": "mock"})

    _monkeypatch_generators(monkeypatch)

    rc = main(["wizard", "--prompt", "hello", "--dry-run"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "from-mock" in out
    assert "from-openai" not in out


def test_env_overrides_config(tmp_path, monkeypatch, capsys):
    from zyra.cli import main

    # Config says openai, env overrides to mock
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    _write_yaml(home / ".datavizhub_wizard.yaml", {"provider": "openai"})
    monkeypatch.setenv("DATAVIZHUB_LLM_PROVIDER", "mock")

    _monkeypatch_generators(monkeypatch)

    rc = main(["wizard", "--prompt", "hello", "--dry-run"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "from-mock" in out
    assert "from-openai" not in out


def test_cli_overrides_env(monkeypatch, capsys):
    from zyra.cli import main

    monkeypatch.setenv("DATAVIZHUB_LLM_PROVIDER", "openai")
    _monkeypatch_generators(monkeypatch)

    rc = main(["wizard", "--provider", "mock", "--prompt", "hello", "--dry-run"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "from-mock" in out
    assert "from-openai" not in out
