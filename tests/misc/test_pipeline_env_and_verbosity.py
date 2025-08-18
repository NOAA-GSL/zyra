import json
import subprocess
import sys
from pathlib import Path

import pytest


def _run_cli(args, input_bytes: bytes | None = None):
    cmd = [sys.executable, "-m", "datavizhub.cli", *args]
    return subprocess.run(cmd, input=input_bytes, capture_output=True)


@pytest.mark.pipeline
def test_env_interpolation_expands_and_strict_errors(tmp_path: Path, monkeypatch):
    cfg = {
        "name": "env-expand",
        "stages": [
            {
                "stage": "processing",
                "command": "convert-format",
                "args": {"file_or_url": "-", "format": "netcdf", "stdout": True},
            },
            {
                "stage": "decimation",
                "command": "local",
                "args": {"input": "-", "path": "${TMPDIR}/out.nc"},
            },
        ],
    }
    p = tmp_path / "pipe.json"
    p.write_text(json.dumps(cfg), encoding="utf-8")

    # Set TMPDIR and run; with --dry-run JSON, check expanded path
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    res = _run_cli(["run", str(p), "--dry-run", "--print-argv-format=json"])
    assert res.returncode == 0
    items = json.loads(res.stdout.decode("utf-8"))
    # Second stage argv should contain expanded TMPDIR
    assert str(tmp_path) in " ".join(items[1]["argv"]) or str(tmp_path) in json.dumps(
        items[1]
    )

    # Default expansion: when VAR is missing, use provided default
    cfg_def = {
        "name": "env-default",
        "stages": [
            {
                "stage": "decimation",
                "command": "local",
                "args": {"input": "-", "path": "${NO_SUCH_VAR:-fallback.bin}"},
            },
        ],
    }
    pdef = tmp_path / "pipe_def.json"
    pdef.write_text(json.dumps(cfg_def), encoding="utf-8")
    res_def = _run_cli(["run", str(pdef), "--dry-run", "--print-argv-format=json"])
    assert res_def.returncode == 0
    items_def = json.loads(res_def.stdout.decode("utf-8"))
    assert "fallback.bin" in " ".join(
        items_def[0]["argv"]
    ) or "fallback.bin" in json.dumps(items_def[0])

    # Strict mode should fail when a var is missing without default
    cfg2 = {
        "name": "env-strict",
        "stages": [
            {
                "stage": "decimation",
                "command": "local",
                "args": {"input": "-", "path": "${NOT_SET}/file.bin"},
            },
        ],
    }
    p2 = tmp_path / "pipe2.json"
    p2.write_text(json.dumps(cfg2), encoding="utf-8")
    res2 = _run_cli(["run", str(p2), "--dry-run", "--strict-env"])
    assert res2.returncode != 0
    assert b"Environment variable not set" in res2.stderr or res2.stdout


@pytest.mark.pipeline
def test_runner_verbosity_flags_print_headings(tmp_path: Path):
    cfg = {
        "name": "verbosity",
        "stages": [
            {
                "stage": "processing",
                "command": "convert-format",
                "args": {"file_or_url": "-", "format": "netcdf"},
            },
        ],
    }
    p = tmp_path / "pipe.json"
    p.write_text(json.dumps(cfg), encoding="utf-8")

    # Verbose: expect Stage heading lines in text dry-run
    res_v = _run_cli(["run", str(p), "--dry-run", "-v"])
    assert res_v.returncode == 0
    assert b"Stage 1 [process]" in res_v.stdout

    # Quiet: no stage headings
    res_q = _run_cli(["run", str(p), "--dry-run", "--quiet"])
    assert res_q.returncode == 0
    assert b"Stage 1 [process]" not in res_q.stdout
