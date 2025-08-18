from __future__ import annotations

from pathlib import Path

from datavizhub.api.workers import jobs as jb
from datavizhub.api.workers.executor import (
    RunResult,
    _ensure_results_dir,
    _maybe_copy_output,
)


def test_package_output_dir_to_zip(tmp_path: Path) -> None:
    jid = jb.submit_job("visualize", "animate", {})
    frames = tmp_path / f"frames_{jid}"
    frames.mkdir(parents=True, exist_ok=True)
    (frames / "frame_0001.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (frames / "frame_0002.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    jb.start_job(jid, "visualize", "animate", {"output_dir": str(frames)})
    rec = jb.get_job(jid)
    assert rec and rec.get("output_file"), "output_file not set"
    out = Path(rec["output_file"])
    assert out.exists() and out.suffix == ".zip"


def test_binary_stdout_saved_with_extension(tmp_path: Path) -> None:
    jid = jb.submit_job("process", "convert-format", {})
    _ensure_results_dir(jid)
    rr = RunResult(
        stdout="",
        stderr="",
        exit_code=0,
        stdout_bytes=b"\x89PNG\r\n\x1a\n...",
        stderr_bytes=b"",
    )
    path = _maybe_copy_output({}, rr, jid)
    assert path is not None
    p = Path(path)
    assert p.exists() and p.name.endswith(".png")
