# SPDX-License-Identifier: Apache-2.0
import json
from argparse import ArgumentParser

from zyra.processing import register_cli


def _build_parser():
    p = ArgumentParser()
    subs = p.add_subparsers(dest="stage")
    register_cli(subs)
    return p


def test_audio_metadata_parses_ffprobe_json(tmp_path, monkeypatch):
    def fake_which(cmd):  # noqa: ARG001
        return "/usr/bin/ffprobe"

    class FakeCompleted:
        def __init__(self, returncode=0, stdout="", stderr=""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    sample = {
        "format": {
            "duration": "12.345",
            "format_name": "ogg",
            "size": "12345",
        },
        "streams": [
            {
                "codec_type": "audio",
                "codec_name": "opus",
                "channels": 1,
                "sample_rate": "16000",
                "bit_rate": "24000",
            }
        ],
    }

    def fake_run(cmd, capture_output=False, text=False):  # noqa: ARG001
        return FakeCompleted(0, json.dumps(sample), "")

    import shutil
    import subprocess

    monkeypatch.setattr(shutil, "which", fake_which)
    monkeypatch.setattr(subprocess, "run", fake_run)

    out = tmp_path / "meta.json"
    parser = _build_parser()
    args = parser.parse_args(
        [
            "audio-metadata",
            str(tmp_path / "in.ogg"),
            "-o",
            str(out),
        ]
    )
    rc = args.func(args)
    assert rc == 0
    meta = json.loads(out.read_text(encoding="utf-8"))
    assert meta["codec"] == "opus"
    assert meta["channels"] == 1
    assert meta["sample_rate"] == 16000
    assert meta["bit_rate"] == 24000
    assert meta["duration"] == 12.345
    assert meta["format_name"] == "ogg"
    assert meta["size"] == 12345
