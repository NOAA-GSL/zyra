# SPDX-License-Identifier: Apache-2.0
import argparse
import os
import shutil
import tempfile

import pytest


def _namespace(frames: str, output: str, **overrides) -> argparse.Namespace:
    ns = argparse.Namespace(
        frames=frames,
        output=output,
        glob=None,
        fps=None,
        basemap=None,
        preset=None,
        size=None,
        verbose=False,
        quiet=False,
        trace=False,
    )
    for key, value in overrides.items():
        setattr(ns, key, value)
    return ns


@pytest.fixture()
def captured_processor(monkeypatch):
    """Swap VideoProcessor for a spy that records kwargs and skips ffmpeg."""
    captured = {}

    class _SpyProcessor:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def validate(self):
            return False  # short-circuit before any ffmpeg work

    import zyra.processing.video_processor as vp_mod

    monkeypatch.setattr(vp_mod, "VideoProcessor", _SpyProcessor)
    return captured


def _make_frames_dir(td: str) -> str:
    frames = os.path.join(td, "frames")
    os.makedirs(frames, exist_ok=True)
    # Content is irrelevant pre-validate; only discovery by extension matters.
    with open(os.path.join(frames, "frame_0000.png"), "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n")
    return frames


def test_preset_sos_resolves_defaults(captured_processor):
    from zyra.visualization.cli_compose_video import handle_compose_video

    with tempfile.TemporaryDirectory() as td:
        frames = _make_frames_dir(td)
        ns = _namespace(frames, os.path.join(td, "out.mp4"), preset="sos")
        assert handle_compose_video(ns) == 0
    assert captured_processor["fps"] == 30
    assert captured_processor["size"] == (4096, 2048)
    assert captured_processor["faststart"] is True


def test_explicit_flags_override_preset(captured_processor):
    from zyra.visualization.cli_compose_video import handle_compose_video

    with tempfile.TemporaryDirectory() as td:
        frames = _make_frames_dir(td)
        ns = _namespace(
            frames, os.path.join(td, "out.mp4"), preset="sos", fps=24, size="2048x1024"
        )
        assert handle_compose_video(ns) == 0
    assert captured_processor["fps"] == 24
    assert captured_processor["size"] == (2048, 1024)
    assert captured_processor["faststart"] is True


def test_no_preset_keeps_legacy_defaults(captured_processor):
    from zyra.visualization.cli_compose_video import handle_compose_video

    with tempfile.TemporaryDirectory() as td:
        frames = _make_frames_dir(td)
        ns = _namespace(frames, os.path.join(td, "out.mp4"))
        assert handle_compose_video(ns) == 0
    assert captured_processor["fps"] == 30
    assert captured_processor["size"] is None
    assert captured_processor["faststart"] is False


def test_bad_size_rejected():
    from zyra.visualization.cli_compose_video import handle_compose_video

    with tempfile.TemporaryDirectory() as td:
        frames = _make_frames_dir(td)
        for bad in ("4096", "0x2048", "ax b"):
            ns = _namespace(frames, os.path.join(td, "out.mp4"), size=bad)
            with pytest.raises(SystemExit):
                handle_compose_video(ns)


@pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe not installed",
)
def test_preset_sos_output_matches_spec():
    """End-to-end: compose tiny frames with --preset sos, ffprobe the result."""
    import subprocess
    import sys

    try:
        import matplotlib.pyplot as plt
    except Exception as e:
        pytest.skip(f"Visualization deps missing: {e}")

    with tempfile.TemporaryDirectory() as td:
        frames = os.path.join(td, "frames")
        os.makedirs(frames, exist_ok=True)
        for i in range(2):
            fig = plt.figure(figsize=(1, 1), dpi=50)
            plt.text(0.5, 0.5, f"{i}", ha="center", va="center")
            fig.savefig(os.path.join(frames, f"frame_{i:04d}.png"))
            plt.close(fig)
        out = os.path.join(td, "out.mp4")
        cmd = [
            sys.executable,
            "-m",
            "zyra.cli",
            "visualize",
            "compose-video",
            "--frames",
            frames,
            "-o",
            out,
            "--preset",
            "sos",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        assert proc.returncode == 0, proc.stderr
        assert os.path.exists(out)
        probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=codec_name,width,height,pix_fmt,r_frame_rate",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                out,
            ],
            capture_output=True,
            text=True,
        )
        assert probe.returncode == 0, probe.stderr
        lines = probe.stdout.splitlines()
        assert len(lines) == 5, probe.stdout
        codec, width, height, pix_fmt, rate = lines
        assert codec == "h264"
        assert (width, height) == ("4096", "2048")
        assert pix_fmt == "yuv420p"
        assert rate in ("30/1", "30000/1000")


def test_cli_compose_video_smoke():
    try:
        # No hard dependency on ffmpeg; we just ensure graceful behavior
        import matplotlib.pyplot as plt
    except Exception as e:
        import pytest

        pytest.skip(f"Visualization deps missing: {e}")

    import subprocess
    import sys

    with tempfile.TemporaryDirectory() as td:
        frames = os.path.join(td, "frames")
        os.makedirs(frames, exist_ok=True)
        # Create two tiny frames
        for i in range(2):
            fig = plt.figure(figsize=(1, 1), dpi=50)
            plt.text(0.5, 0.5, f"{i}", ha="center", va="center")
            fig.savefig(os.path.join(frames, f"frame_{i:04d}.png"))
            plt.close(fig)
        out = os.path.join(td, "out.mp4")
        cmd = [
            sys.executable,
            "-m",
            "zyra.cli",
            "visualize",
            "compose-video",
            "--frames",
            frames,
            "-o",
            out,
            "--fps",
            "12",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        # Should return 0 regardless of ffmpeg availability (graceful skip)
        assert proc.returncode == 0, proc.stderr
        # If ffmpeg is present, an MP4 may be created; if not, that's fine
        # We just care that the command doesn't error out.
