from __future__ import annotations

import os
from pathlib import Path
import pytest

from datavizhub.visualization.cli_animate import _build_ffmpeg_grid_args


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x00")


def test_build_ffmpeg_grid_args_grid_two_inputs(tmp_path: Path) -> None:
    v1 = tmp_path / "a.mp4"
    v2 = tmp_path / "b.mp4"
    out = tmp_path / "out.mp4"
    _touch(v1)
    _touch(v2)
    args = _build_ffmpeg_grid_args(
        videos=[str(v1), str(v2)],
        fps=24,
        output=str(out),
        grid_mode="grid",
        cols=2,
    )
    # Starts with ffmpeg and includes two input args
    assert args[0] == "ffmpeg"
    assert args.count("-i") == 2
    # Contains xstack layout for 2 inputs in one row
    fc_idx = args.index("-filter_complex")
    flt = args[fc_idx + 1]
    assert flt.startswith("xstack=inputs=2:layout=")
    assert "0_0|w0*1_0" in flt
    # Ends with output path
    assert args[-1].endswith("out.mp4")


def test_build_ffmpeg_grid_args_hstack(tmp_path: Path) -> None:
    v1 = tmp_path / "a.mp4"
    v2 = tmp_path / "b.mp4"
    out = tmp_path / "out.mp4"
    _touch(v1)
    _touch(v2)
    args = _build_ffmpeg_grid_args(
        videos=[str(v1), str(v2)],
        fps=30,
        output=str(out),
        grid_mode="hstack",
        cols=2,
    )
    fc_idx = args.index("-filter_complex")
    assert args[fc_idx + 1] == "hstack=inputs=2"


def test_build_ffmpeg_grid_args_validations(tmp_path: Path) -> None:
    v1 = tmp_path / "a.mp4"
    _touch(v1)
    out = tmp_path / "out.mp4"
    # Empty videos
    with pytest.raises(ValueError):
        _build_ffmpeg_grid_args(videos=[], fps=24, output=str(out), grid_mode="grid", cols=2)
    # Bad fps
    with pytest.raises(ValueError):
        _build_ffmpeg_grid_args(videos=[str(v1)], fps=0, output=str(out), grid_mode="grid", cols=1)
    # Output starting with '-'
    with pytest.raises(ValueError):
        _build_ffmpeg_grid_args(videos=[str(v1)], fps=24, output="-bad.mp4", grid_mode="grid", cols=1)
    # Missing input file
    with pytest.raises(ValueError):
        _build_ffmpeg_grid_args(videos=[str(tmp_path / "missing.mp4")], fps=24, output=str(out), grid_mode="grid", cols=1)

