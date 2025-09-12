# SPDX-License-Identifier: Apache-2.0
def test_resolver_detects_missing_args():
    from zyra.wizard.resolver import MissingArgsError, MissingArgumentResolver

    manifest = {
        "process convert-format": {
            "options": {
                "--file_or_url": {
                    "help": "input path",
                    "required": True,
                    "type": "path",
                },
                "--format": {
                    "help": "output format",
                    "choices": ["netcdf", "geotiff"],
                    "type": "str",
                },
            }
        }
    }
    r = MissingArgumentResolver(manifest)
    cmd = "datavizhub process convert-format --format netcdf"
    try:
        r.resolve(cmd, interactive=False)
    except MissingArgsError as e:
        assert "--file_or_url" in e.missing
    else:  # pragma: no cover - guard
        assert False, "Expected MissingArgsError"


def test_resolver_interactive_prompts_user(monkeypatch):
    from zyra.wizard.resolver import MissingArgumentResolver

    manifest = {
        "process convert-format": {
            "options": {
                "--file_or_url": {
                    "help": "input path",
                    "required": True,
                    "type": "path",
                },
                "--format": {
                    "help": "output format",
                    "choices": ["netcdf", "geotiff"],
                    "type": "str",
                },
            }
        }
    }
    r = MissingArgumentResolver(manifest)
    cmd = "datavizhub process convert-format --format netcdf"
    ans = r.resolve(cmd, interactive=True, ask_fn=lambda q, meta: "samples/demo.grib2")
    assert "--file_or_url" in ans
    assert "samples/demo.grib2" in ans


def test_resolver_prompts_for_positionals_only(monkeypatch):
    from zyra.wizard.resolver import MissingArgumentResolver

    manifest = {
        "acquire ftp": {
            "options": {},
            "positionals": [
                {"name": "path", "help": "ftp path", "required": True, "type": "str"}
            ],
        }
    }
    r = MissingArgumentResolver(manifest)
    cmd = "datavizhub acquire ftp"
    ans = r.resolve(
        cmd, interactive=True, ask_fn=lambda q, meta: "ftp://example.com/path"
    )
    assert ans.strip().endswith("ftp://example.com/path")


def test_resolver_masks_sensitive_in_logs(monkeypatch):
    from zyra.wizard.resolver import MissingArgumentResolver

    captured = []

    manifest = {
        "acquire http": {
            "options": {
                "--api_key": {
                    "help": "secret key",
                    "required": True,
                    "type": "str",
                    "sensitive": True,
                }
            },
            "positionals": [
                {"name": "url", "help": "http url", "required": True, "type": "str"}
            ],
        }
    }
    r = MissingArgumentResolver(manifest)
    cmd = "datavizhub acquire http"

    answers = iter(["s3cr3t", "http://example.com/file"])
    out = r.resolve(
        cmd,
        interactive=True,
        ask_fn=lambda q, meta: next(answers),
        log_fn=lambda e: captured.append(e),
    )
    # Ensure sensitive value is masked in logs
    assert any(ev.get("masked") for ev in captured), captured
    assert all(
        ev.get("user_value") != "s3cr3t" for ev in captured if ev.get("masked")
    ), captured
    assert any(ev.get("positional") for ev in captured)


def test_one_shot_missing_args_fails_without_interactive(monkeypatch, capsys):
    # Force a simple manifest with a required flag
    import zyra.wizard as wiz

    def fake_manifest():
        return {
            "foo bar": {
                "options": {"--x": {"help": "x value", "required": True, "type": "int"}}
            }
        }

    monkeypatch.setattr(wiz, "_load_capabilities_manifest", lambda: fake_manifest())

    # Make MockClient return a command missing --x
    from zyra.wizard import llm_client

    monkeypatch.setattr(
        llm_client.MockClient,
        "generate",
        lambda self, sys, user: """```bash\ndatavizhub foo bar\n```""",
    )

    from zyra.cli import main

    rc = main(["wizard", "--provider", "mock", "--prompt", "anything", "--yes"])
    out = capsys.readouterr().out
    assert rc == 2


def test_one_shot_missing_args_prompts_with_interactive(monkeypatch, capsys):
    import zyra.wizard as wiz

    def fake_manifest():
        return {
            "foo bar": {
                "options": {
                    "--x": {"help": "x value", "required": True, "type": "int"}
                },
                "positionals": [
                    {
                        "name": "path",
                        "help": "input path",
                        "required": True,
                        "type": "path",
                    }
                ],
            }
        }

    monkeypatch.setattr(wiz, "_load_capabilities_manifest", lambda: fake_manifest())

    from zyra.wizard import llm_client

    monkeypatch.setattr(
        llm_client.MockClient,
        "generate",
        lambda self, sys, user: """```bash\ndatavizhub foo bar\n```""",
    )

    # Ensure prompt_toolkit path is disabled so input() is used
    import zyra.wizard as wizmod

    monkeypatch.setattr(wizmod, "PTK_AVAILABLE", False)
    # Provide input for interactive prompts: first --x, then positional path
    answers = iter(["123", "/tmp/in.dat"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    from zyra.cli import main

    # Command will still likely fail at execution (unknown command),
    # but argument resolution should occur and not fail fast.
    rc = main(
        [
            "wizard",
            "--provider",
            "mock",
            "--prompt",
            "anything",
            "--interactive",
            "--yes",
        ]
    )
    out = capsys.readouterr().out
    assert "Command ready" in out
    # It should not fail fast with missing-args; ensure the missing message is absent
    assert "Missing required arguments" not in out
