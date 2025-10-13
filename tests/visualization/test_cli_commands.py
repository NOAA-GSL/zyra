# SPDX-License-Identifier: Apache-2.0
import base64
import json
import subprocess
import sys

import pytest


@pytest.mark.cli
@pytest.mark.parametrize(
    "cmd",
    [
        ["visualize", "heatmap", "--help"],
        ["visualize", "contour", "--help"],
        ["visualize", "timeseries", "--help"],
        ["visualize", "vector", "--help"],
        ["visualize", "animate", "--help"],
        ["visualize", "compose-video", "--help"],
        ["visualize", "interactive", "--help"],
        ["visualize", "globe", "--help"],
    ],
)
def test_visualize_subcommand_help_exits_zero(cmd):
    proc = subprocess.run([sys.executable, "-m", "zyra.cli", *cmd], capture_output=True)
    assert proc.returncode == 0, proc.stderr.decode(errors="ignore")


def test_visualize_globe_emits_bundle(tmp_path):
    output_dir = tmp_path / "bundle"
    texture_path = tmp_path / "dummy.png"
    texture_path.write_bytes(_tiny_png())
    gradient_path = tmp_path / "gradient.png"
    gradient_path.write_bytes(_tiny_png())
    lut_path = tmp_path / "lut.json"
    lut_path.write_text('{"a":1}', encoding="utf-8")
    data_path = _write_probe_json(tmp_path)
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "zyra.cli",
            "visualize",
            "globe",
            "--target",
            "webgl-sphere",
            "--output",
            str(output_dir),
            "--texture",
            str(texture_path),
            "--probe-gradient",
            str(gradient_path),
            "--probe-lut",
            str(lut_path),
            "--probe-data",
            str(data_path),
        ],
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stderr.decode(errors="ignore")
    assert (output_dir / "index.html").exists()
    assert (output_dir / "assets" / "sphere.js").exists()
    config = json.loads(
        (output_dir / "assets" / "config.json").read_text(encoding="utf-8")
    )
    assert config.get("texture") == "assets/textures/dummy.png"
    assert config.get("probe_gradient") == "assets/gradients/gradient.png"
    assert config.get("probe_lut") == "assets/gradients/lut.json"
    assert config.get("probe_data") == "assets/data/probe.json"


def test_visualize_globe_cesium(tmp_path):
    output_dir = tmp_path / "cesium"
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "zyra.cli",
            "visualize",
            "globe",
            "--target",
            "cesium-globe",
            "--output",
            str(output_dir),
        ],
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stderr.decode(errors="ignore")
    assert (output_dir / "index.html").exists()
    assert (output_dir / "assets" / "cesium.js").exists()


def test_visualize_globe_cesium_with_gradient(tmp_path):
    output_dir = tmp_path / "cesium_grad"
    gradient_path = tmp_path / "gradient.png"
    lut_path = tmp_path / "lut.json"
    gradient_path.write_bytes(_tiny_png())
    lut_path.write_text('{"a":1}', encoding="utf-8")
    data_path = _write_probe_json(tmp_path)

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "zyra.cli",
            "visualize",
            "globe",
            "--target",
            "cesium-globe",
            "--output",
            str(output_dir),
            "--probe-gradient",
            str(gradient_path),
            "--probe-lut",
            str(lut_path),
            "--probe-data",
            str(data_path),
        ],
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stderr.decode(errors="ignore")
    config = json.loads(
        (output_dir / "assets" / "config.json").read_text(encoding="utf-8")
    )
    assert config.get("probe_gradient") == "assets/gradients/gradient.png"
    assert config.get("probe_lut") == "assets/gradients/lut.json"
    assert config.get("probe_data") == "assets/data/probe.json"


def test_visualize_globe_with_frame_pattern(tmp_path):
    output_dir = tmp_path / "bundle_frames"
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    data = _tiny_png()
    (frames_dir / "frame_01.png").write_bytes(data)
    (frames_dir / "frame_02.png").write_bytes(data)

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "zyra.cli",
            "visualize",
            "globe",
            "--target",
            "webgl-sphere",
            "--output",
            str(output_dir),
            "--texture-pattern",
            str(frames_dir / "*.png"),
            "--animate",
            "time",
        ],
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stderr.decode(errors="ignore")
    config = json.loads(
        (output_dir / "assets" / "config.json").read_text(encoding="utf-8")
    )
    frames = config.get("frames")
    assert isinstance(frames, list)
    assert len(frames) == 2


def _tiny_png() -> bytes:
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMAASsJTYQAAAAASUVORK5CYII="
    )


def _write_probe_json(tmp_path):
    probe_path = tmp_path / "probe.json"
    data = [{"lat": 0.0, "lon": 0.0, "value": 42.5, "units": "K"}]
    probe_path.write_text(json.dumps(data), encoding="utf-8")
    return probe_path
