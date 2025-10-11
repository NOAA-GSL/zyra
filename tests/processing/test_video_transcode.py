# SPDX-License-Identifier: Apache-2.0
import json
import logging
from argparse import ArgumentParser
from pathlib import Path

import pytest

from zyra.processing import register_cli


def _build_parser():
    parser = ArgumentParser()
    subs = parser.add_subparsers(dest="stage")
    register_cli(subs)
    return parser


class _FakeCompleted:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


@pytest.fixture()
def _patch_ffmpeg(monkeypatch):
    from zyra.processing import video_transcode

    def fake_which(cmd):  # noqa: ARG001
        if cmd in {"ffmpeg", "ffprobe"}:
            return f"/usr/bin/{cmd}"
        return None

    monkeypatch.setattr(video_transcode.shutil, "which", fake_which)
    return video_transcode


def test_video_transcode_single_file(tmp_path, monkeypatch, _patch_ffmpeg):
    module = _patch_ffmpeg
    src = tmp_path / "in.mpg"
    src.write_bytes(b"fake")
    out = tmp_path / "out.mp4"
    metadata_out = tmp_path / "metadata.json"
    commands: list[list[str]] = []

    def fake_run(cmd, capture_output=False, text=False, **kwargs):  # noqa: ARG001
        commands.append(cmd)
        if cmd[0].endswith("ffmpeg"):
            Path(cmd[-1]).write_bytes(b"video")
            return _FakeCompleted(0, "", "")
        if cmd[0].endswith("ffprobe"):
            payload = {
                "streams": [
                    {
                        "codec_type": "video",
                        "codec_name": "h264",
                        "width": 1920,
                        "height": 1080,
                        "r_frame_rate": "30/1",
                    }
                ],
                "format": {"duration": "1.0", "bit_rate": "8000000", "size": "12345"},
            }
            return _FakeCompleted(0, json.dumps(payload), "")
        raise AssertionError(f"Unexpected command: {cmd}")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    parser = _build_parser()
    args = parser.parse_args(
        [
            "video-transcode",
            str(src),
            "--to",
            "mp4",
            "-o",
            str(out),
            "--metadata-out",
            str(metadata_out),
            "--write-metadata",
        ]
    )
    rc = args.func(args)
    assert rc == 0
    assert out.exists()
    assert metadata_out.exists()
    metadata = json.loads(metadata_out.read_text())
    assert metadata[0]["metadata"]["video_codec"] == "h264"
    ffmpeg_cmd = commands[0]
    assert "-c:v" in ffmpeg_cmd and ffmpeg_cmd[ffmpeg_cmd.index("-c:v") + 1] == "h264"
    assert (
        "-pix_fmt" in ffmpeg_cmd
        and ffmpeg_cmd[ffmpeg_cmd.index("-pix_fmt") + 1] == "yuv420p"
    )


def test_video_transcode_sequence_sos_defaults(tmp_path, monkeypatch, _patch_ffmpeg):
    module = _patch_ffmpeg
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    out = tmp_path / "legacy.mp4"
    recorded: list[list[str]] = []

    def fake_run(cmd, capture_output=False, text=False, **kwargs):  # noqa: ARG001
        recorded.append(cmd)
        if cmd[0].endswith("ffmpeg"):
            Path(cmd[-1]).write_bytes(b"legacy")
            return _FakeCompleted(0, "", "")
        if cmd[0].endswith("ffprobe"):
            payload = {
                "streams": [
                    {
                        "codec_type": "video",
                        "codec_name": "libxvid",
                        "width": 2048,
                        "height": 1024,
                        "r_frame_rate": "30/1",
                    }
                ],
                "format": {"duration": "2.0", "bit_rate": "25000000", "size": "45678"},
            }
            return _FakeCompleted(0, json.dumps(payload), "")
        raise AssertionError(f"Unexpected command: {cmd}")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    parser = _build_parser()
    args = parser.parse_args(
        [
            "video-transcode",
            f"{frames_dir}/frame%04d.jpg",
            "--sos-legacy",
            "-o",
            str(out),
            "--write-metadata",
        ]
    )
    rc = args.func(args)
    assert rc == 0
    ffmpeg_cmd = recorded[0]
    assert "libxvid" in ffmpeg_cmd
    assert "-b:v" in ffmpeg_cmd and ffmpeg_cmd[ffmpeg_cmd.index("-b:v") + 1] == "25M"
    framerate_index = ffmpeg_cmd.index("-framerate")
    assert ffmpeg_cmd[framerate_index + 1] == "30.0"
    assert ffmpeg_cmd[framerate_index + 2] == "-i"
    assert out.exists()
    assert ffmpeg_cmd[-1].endswith("legacy.mp4")


def test_video_transcode_sequence_default_name(tmp_path, monkeypatch, _patch_ffmpeg):
    module = _patch_ffmpeg
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    (frames_dir / "tile_%04d.png").write_bytes(b"")
    commands: list[list[str]] = []

    def fake_run(cmd, capture_output=False, text=False, **kwargs):  # noqa: ARG001
        commands.append(cmd)
        if cmd[0].endswith("ffmpeg"):
            Path(cmd[-1]).write_bytes(b"seq")
            return _FakeCompleted(0, "", "")
        if cmd[0].endswith("ffprobe"):
            return _FakeCompleted(1, "", "ffprobe unavailable")
        raise AssertionError(f"Unexpected command: {cmd}")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    parser = _build_parser()
    args = parser.parse_args(
        [
            "video-transcode",
            f"{frames_dir}/tile_%04d.png",
            "--to",
            "mp4",
        ]
    )
    rc = args.func(args)
    assert rc == 0
    ffmpeg_cmd = commands[0]
    output_path = Path(ffmpeg_cmd[-1])
    assert output_path.name == "tile.mp4"
    assert output_path.parent == frames_dir


def test_video_transcode_scale_width_only(tmp_path, monkeypatch, _patch_ffmpeg):
    module = _patch_ffmpeg
    src = tmp_path / "clip.mpg"
    src.write_bytes(b"data")
    out = tmp_path / "clip.mp4"
    commands: list[list[str]] = []

    def fake_run(cmd, capture_output=False, text=False, **kwargs):  # noqa: ARG001
        commands.append(cmd)
        if cmd[0].endswith("ffmpeg"):
            Path(cmd[-1]).write_bytes(b"video")
            return _FakeCompleted(0, "", "")
        if cmd[0].endswith("ffprobe"):
            return _FakeCompleted(1, "", "ffprobe unavailable")
        raise AssertionError(f"Unexpected command: {cmd}")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    parser = _build_parser()
    args = parser.parse_args(
        [
            "video-transcode",
            str(src),
            "--scale",
            "1920x?",
            "-o",
            str(out),
        ]
    )
    rc = args.func(args)
    assert rc == 0
    ffmpeg_cmd = commands[0]
    vf_index = ffmpeg_cmd.index("-vf")
    assert ffmpeg_cmd[vf_index + 1] == "scale=1920:-2"


def test_video_transcode_scale_passthrough(tmp_path, monkeypatch, _patch_ffmpeg):
    module = _patch_ffmpeg
    src = tmp_path / "clip.mpg"
    src.write_bytes(b"data")
    out = tmp_path / "clip.mp4"
    commands: list[list[str]] = []

    def fake_run(cmd, capture_output=False, text=False, **kwargs):  # noqa: ARG001
        commands.append(cmd)
        if cmd[0].endswith("ffmpeg"):
            Path(cmd[-1]).write_bytes(b"video")
            return _FakeCompleted(0, "", "")
        if cmd[0].endswith("ffprobe"):
            return _FakeCompleted(1, "", "ffprobe unavailable")
        raise AssertionError(f"Unexpected command: {cmd}")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    parser = _build_parser()
    args = parser.parse_args(
        [
            "video-transcode",
            str(src),
            "--scale",
            "scale=w=1280:h=-1",
            "-o",
            str(out),
        ]
    )
    rc = args.func(args)
    assert rc == 0
    ffmpeg_cmd = commands[0]
    vf_index = ffmpeg_cmd.index("-vf")
    assert ffmpeg_cmd[vf_index + 1] == "scale=w=1280:h=-1"


def test_video_transcode_sos_mpg_warns_and_sets_mpeg2(
    tmp_path, monkeypatch, _patch_ffmpeg, caplog
):
    module = _patch_ffmpeg
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    out = tmp_path / "legacy.mpg"
    recorded: list[list[str]] = []

    def fake_run(cmd, capture_output=False, text=False, **kwargs):  # noqa: ARG001
        recorded.append(cmd)
        if cmd[0].endswith("ffmpeg"):
            Path(cmd[-1]).write_bytes(b"legacy")
            return _FakeCompleted(0, "", "")
        if cmd[0].endswith("ffprobe"):
            return _FakeCompleted(1, "", "ffprobe unavailable")
        raise AssertionError(f"Unexpected command: {cmd}")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    parser = _build_parser()
    caplog.set_level(logging.WARNING)
    args = parser.parse_args(
        [
            "video-transcode",
            f"{frames_dir}/frame%04d.jpg",
            "--sos-legacy",
            "--to",
            "mpg",
            "-o",
            str(out),
        ]
    )
    rc = args.func(args)
    assert rc == 0
    ffmpeg_cmd = recorded[0]
    assert (
        "-c:v" in ffmpeg_cmd
        and ffmpeg_cmd[ffmpeg_cmd.index("-c:v") + 1] == "mpeg2video"
    )
    assert "SOS legacy preset normally emits .mp4 files." in caplog.text


def test_video_transcode_missing_ffmpeg(tmp_path, monkeypatch):
    from zyra.processing import video_transcode

    def missing_which(cmd):  # noqa: ARG001
        return None

    monkeypatch.setattr(video_transcode.shutil, "which", missing_which)
    (tmp_path / "input.mp4").write_bytes(b"data")

    parser = _build_parser()
    args = parser.parse_args(
        [
            "video-transcode",
            str(tmp_path / "input.mp4"),
            "-o",
            str(tmp_path / "out.mp4"),
        ]
    )
    rc = args.func(args)
    assert rc == 2


def test_video_transcode_batch_directory(tmp_path, monkeypatch, _patch_ffmpeg):
    module = _patch_ffmpeg
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "a.mpg").write_bytes(b"a")
    (src_dir / "b.mpg").write_bytes(b"b")
    out_dir = tmp_path / "converted"
    calls: list[list[str]] = []

    def fake_run(cmd, capture_output=False, text=False, **kwargs):  # noqa: ARG001
        calls.append(cmd)
        if cmd[0].endswith("ffmpeg"):
            Path(cmd[-1]).write_bytes(b"out")
            return _FakeCompleted(0, "", "")
        if cmd[0].endswith("ffprobe"):
            payload = {
                "streams": [
                    {
                        "codec_type": "video",
                        "codec_name": "h264",
                        "width": 1280,
                        "height": 720,
                        "r_frame_rate": "24/1",
                    }
                ],
                "format": {"duration": "1.0", "bit_rate": "4000000", "size": "111"},
            }
            return _FakeCompleted(0, json.dumps(payload), "")
        raise AssertionError(f"Unexpected command: {cmd}")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    parser = _build_parser()
    args = parser.parse_args(
        [
            "video-transcode",
            str(src_dir),
            "--to",
            "mp4",
            "--output",
            str(out_dir),
            "--write-metadata",
        ]
    )
    rc = args.func(args)
    assert rc == 0
    assert (out_dir / "a.mp4").exists()
    assert (out_dir / "b.mp4").exists()
    assert len([cmd for cmd in calls if cmd[0].endswith("ffmpeg")]) == 2


def test_video_transcode_batch_glob_preserves_structure(
    tmp_path, monkeypatch, _patch_ffmpeg
):
    module = _patch_ffmpeg
    src_root = tmp_path / "sq"
    nested = src_root / "nested"
    nested.mkdir(parents=True)
    (nested / "clip.mpg").write_bytes(b"clip")
    out_dir = tmp_path / "converted"
    commands: list[list[str]] = []

    def fake_run(cmd, capture_output=False, text=False, **kwargs):  # noqa: ARG001
        commands.append(cmd)
        if cmd[0].endswith("ffmpeg"):
            Path(cmd[-1]).write_bytes(b"out")
            return _FakeCompleted(0, "", "")
        if cmd[0].endswith("ffprobe"):
            return _FakeCompleted(1, "", "ffprobe unavailable")
        raise AssertionError(f"Unexpected command: {cmd}")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    pattern = str(src_root / "*" / "*.mpg")
    parser = _build_parser()
    args = parser.parse_args(
        [
            "video-transcode",
            pattern,
            "--output",
            str(out_dir),
        ]
    )
    rc = args.func(args)
    assert rc == 0
    assert (out_dir / "nested" / "clip.mp4").exists()
    ffmpeg_cmd = commands[0]
    assert ffmpeg_cmd[-1].endswith("nested/clip.mp4")


def test_video_transcode_extra_args_split(tmp_path, monkeypatch, _patch_ffmpeg):
    module = _patch_ffmpeg
    src = tmp_path / "input.mpg"
    src.write_bytes(b"data")
    out = tmp_path / "out.mp4"
    commands: list[list[str]] = []

    def fake_run(cmd, capture_output=False, text=False, **kwargs):  # noqa: ARG001
        commands.append(cmd)
        if cmd[0].endswith("ffmpeg"):
            Path(cmd[-1]).write_bytes(b"video")
            return _FakeCompleted(0, "", "")
        if cmd[0].endswith("ffprobe"):
            return _FakeCompleted(1, "", "ffprobe unavailable")
        raise AssertionError(f"Unexpected command: {cmd}")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    parser = _build_parser()
    args = parser.parse_args(
        [
            "video-transcode",
            str(src),
            "-o",
            str(out),
            "--extra-args",
            "-movflags +faststart",
            "--extra-args",
            "-max_muxing_queue_size 2048",
        ]
    )
    rc = args.func(args)
    assert rc == 0
    ffmpeg_cmd = commands[0]
    assert "-movflags" in ffmpeg_cmd
    assert "+faststart" in ffmpeg_cmd
    assert "-max_muxing_queue_size" in ffmpeg_cmd
    assert "2048" in ffmpeg_cmd


def test_video_transcode_percent_filename_not_sequence(
    tmp_path, monkeypatch, _patch_ffmpeg
):
    module = _patch_ffmpeg
    src = tmp_path / "clip%done.mp4"
    src.write_bytes(b"data")
    out = tmp_path / "converted" / "clip.mp4"
    commands: list[list[str]] = []

    def fake_run(cmd, capture_output=False, text=False, **kwargs):  # noqa: ARG001
        commands.append(cmd)
        if cmd[0].endswith("ffmpeg"):
            Path(cmd[-1]).parent.mkdir(parents=True, exist_ok=True)
            Path(cmd[-1]).write_bytes(b"video")
            return _FakeCompleted(0, "", "")
        if cmd[0].endswith("ffprobe"):
            return _FakeCompleted(1, "", "ffprobe unavailable")
        raise AssertionError(f"Unexpected command: {cmd}")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    parser = _build_parser()
    args = parser.parse_args(
        [
            "video-transcode",
            str(src),
            "--to",
            "mp4",
            "-o",
            str(out),
        ]
    )
    rc = args.func(args)
    assert rc == 0
    assert out.exists()
    ffmpeg_cmd = commands[0]
    assert "-framerate" not in ffmpeg_cmd
    assert ffmpeg_cmd[ffmpeg_cmd.index("-i") + 1] == str(src)
