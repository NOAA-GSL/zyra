import json
from pathlib import Path

import pytest


def _run_cli(args, input_bytes: bytes | None = None):
    import subprocess
    import sys as _sys

    cmd = [_sys.executable, "-m", "datavizhub.cli", *args]
    return subprocess.run(cmd, input=input_bytes, capture_output=True)


@pytest.mark.pipeline
def test_run_process_convert_format_passthrough(tmp_path: Path):
    # Pipeline: processing convert-format - netcdf --stdout; stdin is demo.nc
    cfg = {
        "name": "NC passthrough",
        "stages": [
            {
                "stage": "processing",
                "command": "convert-format",
                "args": {"file_or_url": "-", "format": "netcdf", "stdout": True},
            }
        ],
    }
    import json

    p = tmp_path / "pipe.json"
    p.write_text(json.dumps(cfg), encoding="utf-8")

    demo = Path("tests/testdata/demo.nc").read_bytes()
    res = _run_cli(["run", str(p)], input_bytes=demo)
    assert res.returncode == 0, res.stderr.decode(errors="ignore")
    out = res.stdout
    assert out.startswith(b"CDF") or out.startswith(b"\x89HDF")


@pytest.mark.pipeline
def test_run_dry_run_builds_acquire_and_decimate_args(tmp_path: Path):
    # Use backend-style for acquire (per wiki), and local decimation
    cfg = {
        "name": "Acquire + Decimate Dry Run",
        "stages": [
            {
                "stage": "acquisition",
                "command": "acquire",
                "args": {
                    "backend": "s3",
                    "bucket": "my-bucket",
                    "key": "path/file.bin",
                    "output": "-",
                },
            },
            {
                "stage": "decimation",
                "command": "decimate",
                "args": {
                    "backend": "local",
                    "input": "-",
                    "path": str(tmp_path / "out.bin"),
                },
            },
        ],
    }
    import json

    p = tmp_path / "pipe.json"
    p.write_text(json.dumps(cfg), encoding="utf-8")

    res = _run_cli(["run", str(p), "--dry-run"])
    assert res.returncode == 0, res.stderr.decode(errors="ignore")
    text = res.stdout.decode("utf-8")
    assert (
        "acquire s3" in text
        and "--bucket my-bucket" in text
        and "--key path/file.bin" in text
    )
    assert "decimate local" in text and str(tmp_path / "out.bin") in text


@pytest.mark.pipeline
def test_dry_run_json_emits_objects_with_stage_and_name(tmp_path: Path):
    cfg = {
        "name": "JSON ARGV shape",
        "stages": [
            {
                "id": "fetch-http-1",
                "stage": "acquisition",
                "command": "acquire",
                "args": {"backend": "http", "url": "https://example.com/a.nc"},
            },
            {
                "id": "convert-1",
                "stage": "processing",
                "command": "convert-format",
                "args": {"file_or_url": "-", "format": "netcdf"},
            },
        ],
    }
    import json

    p = tmp_path / "pipe.json"
    p.write_text(json.dumps(cfg), encoding="utf-8")

    res = _run_cli(["run", str(p), "--dry-run", "--print-argv-format=json"])
    assert res.returncode == 0
    items = json.loads(res.stdout.decode("utf-8"))
    assert isinstance(items, list) and len(items) == 2
    assert (
        items[0]["stage"] == 1
        and items[0]["name"] == "acquire"
        and items[0]["id"] == "fetch-http-1"
    )
    assert (
        items[1]["stage"] == 2
        and items[1]["name"] == "process"
        and items[1]["id"] == "convert-1"
    )


@pytest.mark.pipeline
def test_dry_run_json_with_only_preserves_ids_and_reindexes(tmp_path: Path):
    cfg = {
        "name": "JSON only",
        "stages": [
            {
                "id": "fetch1",
                "stage": "acquisition",
                "command": "acquire",
                "args": {"backend": "http", "url": "https://example.com/a.nc"},
            },
            {
                "id": "proc1",
                "stage": "processing",
                "command": "convert-format",
                "args": {"file_or_url": "-", "format": "netcdf"},
            },
            {
                "id": "proc2",
                "stage": "processing",
                "command": "convert-format",
                "args": {"file_or_url": "-", "format": "netcdf"},
            },
        ],
    }
    p = tmp_path / "pipe.json"
    p.write_text(json.dumps(cfg), encoding="utf-8")
    res = _run_cli(
        ["run", str(p), "--dry-run", "--print-argv-format=json", "--only", "process"]
    )
    assert res.returncode == 0
    items = json.loads(res.stdout.decode("utf-8"))
    # Only process stages remain, reindexed starting at 1, ids preserved
    assert len(items) == 2
    assert (
        items[0]["stage"] == 1
        and items[0]["name"] == "process"
        and items[0]["id"] == "proc1"
    )
    assert (
        items[1]["stage"] == 2
        and items[1]["name"] == "process"
        and items[1]["id"] == "proc2"
    )


@pytest.mark.pipeline
def test_dry_run_json_start_end_preserves_ids_and_reindexes(tmp_path: Path):
    cfg = {
        "name": "JSON start-end",
        "stages": [
            {
                "id": "s1",
                "stage": "acquisition",
                "command": "acquire",
                "args": {"backend": "http", "url": "https://example.com/a.nc"},
            },
            {
                "id": "s2",
                "stage": "processing",
                "command": "convert-format",
                "args": {"file_or_url": "-", "format": "netcdf"},
            },
            {
                "id": "s3",
                "stage": "decimation",
                "command": "local",
                "args": {"input": "-", "path": "out.nc"},
            },
        ],
    }
    p = tmp_path / "pipe2.json"
    p.write_text(json.dumps(cfg), encoding="utf-8")
    res = _run_cli(
        [
            "run",
            str(p),
            "--dry-run",
            "--print-argv-format=json",
            "--start",
            "2",
            "--end",
            "3",
        ]
    )
    assert res.returncode == 0
    items = json.loads(res.stdout.decode("utf-8"))
    assert len(items) == 2
    # Reindexed stages start at 1; ids correspond to original stages 2 and 3
    assert items[0]["stage"] == 1 and items[0]["id"] == "s2"
    assert items[1]["stage"] == 2 and items[1]["id"] == "s3"
    # argv arrays present and start with 'datavizhub'
    assert isinstance(items[0]["argv"], list) and items[0]["argv"][0] == "datavizhub"


@pytest.mark.pipeline
def test_run_process_then_decimate_local(tmp_path: Path):
    # Convert NetCDF stdin (pass-through) then write to a file via decimate local
    cfg = {
        "name": "NC to file",
        "stages": [
            {
                "stage": "processing",
                "command": "convert-format",
                "args": {"file_or_url": "-", "format": "netcdf", "stdout": True},
            },
            {
                "stage": "decimation",
                "command": "local",
                "args": {"input": "-", "path": str(tmp_path / "out.nc")},
            },
        ],
    }
    import json

    p = tmp_path / "pipe.json"
    p.write_text(json.dumps(cfg), encoding="utf-8")

    demo = Path("tests/testdata/demo.nc").read_bytes()
    res = _run_cli(["run", str(p)], input_bytes=demo)
    assert res.returncode == 0, res.stderr.decode(errors="ignore")
    out_file = tmp_path / "out.nc"
    assert out_file.exists()
    data = out_file.read_bytes()
    assert data.startswith(b"CDF") or data.startswith(b"\x89HDF")


@pytest.mark.pipeline
def test_stage_name_overrides_apply_correctly(tmp_path: Path):
    # Use stage-name overrides to change arguments on targeted stages
    cfg = {
        "name": "Stage-name overrides",
        "stages": [
            {
                "stage": "processing",
                "command": "convert-format",
                "args": {"file_or_url": "-", "format": "netcdf", "stdout": True},
            },
            {
                "stage": "decimation",
                "command": "local",
                "args": {"input": "-", "path": str(tmp_path / "ORIG.nc")},
            },
        ],
    }
    import json

    p = tmp_path / "pipe.json"
    p.write_text(json.dumps(cfg), encoding="utf-8")

    demo = Path("tests/testdata/demo.nc").read_bytes()
    # Override the path on the decimation stage via stage-name syntax
    res = _run_cli(
        ["run", str(p), "--set", f"decimation.path={tmp_path/'NEW.nc'}"],
        input_bytes=demo,
    )
    assert res.returncode == 0, res.stderr.decode(errors="ignore")
    assert (tmp_path / "NEW.nc").exists()
    assert not (tmp_path / "ORIG.nc").exists()


@pytest.mark.pipeline
def test_run_start_end_subset(tmp_path: Path):
    # Stages: [1] process convert, [2] process convert, [3] decimate local
    # Run only stage 2 via --start/--end and assert stdout NetCDF header
    cfg = {
        "name": "subset",
        "stages": [
            {
                "stage": "processing",
                "command": "convert-format",
                "args": {"file_or_url": "-", "format": "netcdf", "stdout": True},
            },
            {
                "stage": "processing",
                "command": "convert-format",
                "args": {"file_or_url": "-", "format": "netcdf", "stdout": True},
            },
            {
                "stage": "decimation",
                "command": "local",
                "args": {"input": "-", "path": str(tmp_path / "out.nc")},
            },
        ],
    }
    import json

    p = tmp_path / "pipe.json"
    p.write_text(json.dumps(cfg), encoding="utf-8")

    demo = Path("tests/testdata/demo.nc").read_bytes()
    res = _run_cli(["run", str(p), "--start", "2", "--end", "2"], input_bytes=demo)
    assert res.returncode == 0
    assert res.stdout.startswith(b"CDF") or res.stdout.startswith(b"\x89HDF")


@pytest.mark.pipeline
def test_run_only_stage_name(tmp_path: Path):
    # Only run process stage and emit stdout NetCDF
    cfg = {
        "name": "only-process",
        "stages": [
            {
                "stage": "processing",
                "command": "convert-format",
                "args": {"file_or_url": "-", "format": "netcdf", "stdout": True},
            },
            {
                "stage": "decimation",
                "command": "local",
                "args": {"input": "-", "path": str(tmp_path / "out.nc")},
            },
        ],
    }
    import json

    p = tmp_path / "pipe.json"
    p.write_text(json.dumps(cfg), encoding="utf-8")

    demo = Path("tests/testdata/demo.nc").read_bytes()
    res = _run_cli(["run", str(p), "--only", "process"], input_bytes=demo)
    assert res.returncode == 0
    assert res.stdout.startswith(b"CDF") or res.stdout.startswith(b"\x89HDF")
