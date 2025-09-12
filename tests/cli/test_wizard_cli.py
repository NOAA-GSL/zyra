# SPDX-License-Identifier: Apache-2.0
import pytest


def test_wizard_help_works(capsys):
    """Ensure `zyra wizard --help` shows usage and exits cleanly."""
    from zyra.cli import main

    with pytest.raises(SystemExit) as exc:
        main(["wizard", "--help"])  # argparse prints help then exits
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "usage: zyra wizard" in out


def test_wizard_mock_prompt_dry_run_outputs_commands(capsys):
    """Mock provider with --dry-run should print suggested commands and return 0."""
    from zyra.cli import main

    rc = main(
        [
            "wizard",
            "--provider",
            "mock",
            "--prompt",
            "something",
            "--dry-run",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    # The mock client prints a 'zyra ...' suggestion
    assert "zyra" in out


def test_wizard_logs_created(tmp_path, monkeypatch):
    """When --log is passed, a JSONL log file should be created under HOME."""
    from zyra.cli import main

    # Point HOME to a temp dir so we don't write to the real home directory
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))

    rc = main(
        [
            "wizard",
            "--provider",
            "mock",
            "--prompt",
            "example",
            "--dry-run",
            "--log",
        ]
    )
    assert rc == 0

    logs_dir = fake_home / ".datavizhub" / "wizard_logs"
    assert logs_dir.exists()
    files = list(logs_dir.glob("*.jsonl"))
    assert files, "Expected at least one JSONL log file to be created"
    # Optional: ensure file is non-empty
    assert any(f.stat().st_size > 0 for f in files)


def test_wizard_extracts_bash_prompt_lines(capsys, monkeypatch):
    """Commands with "$ datavizhub ..." in fenced code blocks are extracted and printed."""
    from zyra.cli import main
    from zyra.wizard import llm_client

    def fake_generate(system_prompt: str, user_prompt: str) -> str:
        return (
            """
Here you go:
```bash
$ datavizhub process convert-format input.nc --format geotiff --output out.tif
```
"""
        ).strip()

    monkeypatch.setattr(llm_client.MockClient, "generate", staticmethod(fake_generate))

    rc = main(
        [
            "wizard",
            "--provider",
            "mock",
            "--prompt",
            "anything",
            "--dry-run",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    # Ensure the printed command has no leading "$ " and starts with datavizhub
    assert "datavizhub process convert-format" in out
    assert "$ datavizhub" not in out


def test_wizard_extracts_multiple_fenced_blocks(capsys, monkeypatch):
    """All fenced blocks are scanned; commands from each are listed."""
    from zyra.cli import main
    from zyra.wizard import llm_client

    def fake_generate(system_prompt: str, user_prompt: str) -> str:
        return (
            """
```bash
$ datavizhub one
```

Some text

```bash
datavizhub two
```
"""
        ).strip()

    monkeypatch.setattr(llm_client.MockClient, "generate", staticmethod(fake_generate))

    rc = main(
        [
            "wizard",
            "--provider",
            "mock",
            "--prompt",
            "multi",
            "--dry-run",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "datavizhub one" in out
    assert "datavizhub two" in out


def test_wizard_strips_inline_comments(capsys, monkeypatch):
    """Inline comments after commands are removed from suggestions/output."""
    from zyra.cli import main
    from zyra.wizard import llm_client

    def fake_generate(system_prompt: str, user_prompt: str) -> str:
        return (
            """
```bash
datavizhub process convert-format input.nc --format geotiff --output out.tif # explain why
```
"""
        ).strip()

    monkeypatch.setattr(llm_client.MockClient, "generate", staticmethod(fake_generate))

    rc = main(
        [
            "wizard",
            "--provider",
            "mock",
            "--prompt",
            "comments",
            "--dry-run",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "# explain why" not in out
    assert "datavizhub process convert-format" in out


def test_wizard_safety_drops_unsafe_lines(capsys, monkeypatch):
    """Non-datavizhub lines (e.g., rm -rf) are ignored with a notice."""
    from zyra.cli import main
    from zyra.wizard import llm_client

    def fake_generate(system_prompt: str, user_prompt: str) -> str:
        return (
            """
```bash
rm -rf /
datavizhub ok
```
"""
        ).strip()

    monkeypatch.setattr(llm_client.MockClient, "generate", staticmethod(fake_generate))

    rc = main(
        [
            "wizard",
            "--provider",
            "mock",
            "--prompt",
            "safe",
            "--dry-run",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "datavizhub ok" in out


def test_wizard_show_raw_prints_reply(capsys, monkeypatch):
    from zyra.cli import main
    from zyra.wizard import llm_client

    def fake_generate(system_prompt: str, user_prompt: str) -> str:
        return """RAWXYZ
```
datavizhub process convert-format input.nc geotiff --output out.tif
```"""

    monkeypatch.setattr(llm_client.MockClient, "generate", staticmethod(fake_generate))

    rc = main(
        [
            "wizard",
            "--provider",
            "mock",
            "--prompt",
            "convert",
            "--show-raw",
            "--dry-run",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "Raw model output:" in out
    assert "RAWXYZ" in out


def test_wizard_explain_preserves_comments_but_default_strips(capsys, monkeypatch):
    from zyra.cli import main
    from zyra.wizard import llm_client

    reply = (
        """
```bash
datavizhub acquire input.grib2 -o output.nc  # convert GRIB2 to NetCDF
```
"""
    ).strip()

    monkeypatch.setattr(
        llm_client.MockClient, "generate", staticmethod(lambda s, u: reply)
    )

    # With --explain, the comment should appear in output
    rc = main(
        [
            "wizard",
            "--provider",
            "mock",
            "--prompt",
            "anything",
            "--explain",
            "--dry-run",
        ]
    )
    assert rc == 0
    out_explain = capsys.readouterr().out
    assert "# convert GRIB2 to NetCDF" in out_explain

    # Without --explain, the printed suggestion should be stripped of comments
    rc = main(
        [
            "wizard",
            "--provider",
            "mock",
            "--prompt",
            "anything",
            "--dry-run",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "# convert GRIB2 to NetCDF" not in out
    assert "rm -rf /" not in out
