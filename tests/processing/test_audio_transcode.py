# SPDX-License-Identifier: Apache-2.0
from argparse import ArgumentParser
from pathlib import Path

from zyra.processing import register_cli


def _build_parser():
    p = ArgumentParser()
    subs = p.add_subparsers(dest="stage")
    register_cli(subs)
    return p


def test_audio_transcode_invokes_ffmpeg(tmp_path, monkeypatch):
    # Arrange fake ffmpeg and subprocess
    out = tmp_path / "out.wav"

    def fake_which(cmd):  # noqa: ARG001
        return "/usr/bin/ffmpeg"

    class FakeCompleted:
        def __init__(self, returncode=0, stderr=""):
            self.returncode = returncode
            self.stderr = stderr

    def fake_run(cmd, capture_output=False, text=False):  # noqa: ARG001
        # write output file as ffmpeg would
        Path(cmd[-1]).write_bytes(b"RIFF....WAVE")
        return FakeCompleted(0, "")

    import shutil
    import subprocess

    monkeypatch.setattr(shutil, "which", fake_which)
    monkeypatch.setattr(subprocess, "run", fake_run)

    parser = _build_parser()
    args = parser.parse_args(
        [
            "audio-transcode",
            str(tmp_path / "in.ogg"),
            "-o",
            str(out),
            "--to",
            "wav",
            "--sample-rate",
            "8000",
            "--mono",
        ]
    )
    rc = args.func(args)
    assert rc == 0
    assert out.exists()
