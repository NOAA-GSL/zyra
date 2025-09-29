# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import argparse
import json
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import pytest

try:
    from PIL import Image, ImageChops
except ModuleNotFoundError:
    pytest.skip("Pillow is required for pad-missing tests", allow_module_level=True)

from zyra.processing.pad_missing import pad_missing_frames
from zyra.transform import register_cli as register_transform_cli


def _make_frame(path: Path, color: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (64, 64), color)
    img.save(path)


@pytest.fixture()
def frames_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    frames_dir = tmp_path / "frames"
    output_dir = tmp_path / "out"
    frames_dir.mkdir()
    _make_frame(frames_dir / "frame_202401010000.png", "#ff0000")
    _make_frame(frames_dir / "frame_202401010010.png", "#ff0000")
    meta = {
        "frames_dir": str(frames_dir),
        "datetime_format": "%Y%m%d%H%M",
        "missing_timestamps": ["2024-01-01T00:05:00"],
    }
    meta_path = tmp_path / "frames_meta.json"
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    return frames_dir, output_dir, meta_path


def test_pad_missing_blank_mode(frames_fixture: tuple[Path, Path, Path]) -> None:
    _, output_dir, meta_path = frames_fixture
    created = pad_missing_frames(
        str(meta_path),
        output_dir=str(output_dir),
        fill_mode="blank",
    )
    expected = output_dir / "frame_202401010005.png"
    assert expected in created
    with Image.open(expected) as img:
        assert img.size == (64, 64)
        assert img.mode == "RGB"
        assert img.getpixel((0, 0)) == (0, 0, 0)


def test_pad_missing_solid_color(frames_fixture: tuple[Path, Path, Path]) -> None:
    _, output_dir, meta_path = frames_fixture
    shade = "#123456"
    created = pad_missing_frames(
        str(meta_path),
        output_dir=str(output_dir / "solid"),
        fill_mode="solid",
        basemap=shade,
    )
    expected = output_dir / "solid" / "frame_202401010005.png"
    assert expected in created
    with Image.open(expected) as img:
        assert img.getpixel((5, 5)) == Image.new("RGB", (1, 1), shade).getpixel((0, 0))


def test_pad_missing_nearest_with_indicator(
    frames_fixture: tuple[Path, Path, Path],
) -> None:
    frames_dir, output_dir, meta_path = frames_fixture
    # Add an intermediate frame at a different color to ensure donor selection is deterministic
    _make_frame(frames_dir / "frame_202401010015.png", "#0000ff")
    created = pad_missing_frames(
        str(meta_path),
        output_dir=str(output_dir / "nearest"),
        fill_mode="nearest",
        indicator="watermark:MISSING",
    )
    expected = output_dir / "nearest" / "frame_202401010005.png"
    assert expected in created
    with Image.open(expected) as img, Image.open(
        frames_dir / "frame_202401010000.png"
    ) as base:
        diff = ImageChops.difference(img, base)
        assert diff.getbbox() is not None


def test_pad_missing_json_report(
    frames_fixture: tuple[Path, Path, Path], tmp_path: Path
) -> None:
    _, output_dir, meta_path = frames_fixture
    report_path = tmp_path / "report.json"
    pad_missing_frames(
        str(meta_path),
        output_dir=str(output_dir / "report"),
        fill_mode="blank",
        json_report=str(report_path),
    )
    data = json.loads(report_path.read_text(encoding="utf-8"))
    assert data["status"] == "completed"
    assert data["created_count"] == 1
    assert data["created_files"]


def test_pad_missing_json_report_dry_run(
    frames_fixture: tuple[Path, Path, Path], tmp_path: Path
) -> None:
    _, output_dir, meta_path = frames_fixture
    report_path = tmp_path / "report-dry.json"
    pad_missing_frames(
        str(meta_path),
        output_dir=str(output_dir / "dry"),
        fill_mode="blank",
        dry_run=True,
        json_report=str(report_path),
    )
    data = json.loads(report_path.read_text(encoding="utf-8"))
    assert data["status"] == "dry-run"
    assert data["created_count"] == 0
    assert data["planned_count"] == 1
    assert data["planned_files"]


def test_pad_missing_reads_metadata_from_stdin(
    frames_fixture: tuple[Path, Path, Path], tmp_path: Path
) -> None:
    _, output_dir, meta_path = frames_fixture
    report_path = tmp_path / "stdin-report.json"
    out_dir = output_dir / "stdin"

    class _StdInMock:
        def __init__(self, data: bytes) -> None:
            self.buffer = BytesIO(data)

    with patch("sys.stdin", _StdInMock(meta_path.read_bytes())):
        pad_missing_frames(
            "-",
            output_dir=str(out_dir),
            fill_mode="blank",
            json_report=str(report_path),
            read_stdin=True,
        )
    data = json.loads(report_path.read_text(encoding="utf-8"))
    assert data["metadata_path"] == "-"
    assert data["created_count"] == 1


def test_transform_scan_frames_alias(tmp_path: Path) -> None:
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    _make_frame(frames_dir / "frame_202401010000.png", "#00ff00")
    output = tmp_path / "meta.json"

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="cmd", required=True)
    register_transform_cli(subparsers)

    args = parser.parse_args(
        [
            "scan-frames",
            "--frames-dir",
            str(frames_dir),
            "--datetime-format",
            "%Y%m%d%H%M",
            "-o",
            str(output),
        ]
    )
    exit_code = args.func(args)
    assert exit_code == 0
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["frame_count_actual"] == 1
