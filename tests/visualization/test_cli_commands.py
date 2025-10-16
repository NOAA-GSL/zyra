# SPDX-License-Identifier: Apache-2.0
import base64
import functools
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
import xarray as xr
from PIL import Image

from zyra.processing.video_processor import VideoProcessor


@functools.lru_cache
def _ffmpeg_available() -> bool:
    try:
        vp = VideoProcessor(input_directory=".", output_file="_/tmp/out.mp4")
        return vp.check_ffmpeg_installed()
    except Exception:
        return False


def _write_color_png(path: Path, color: tuple[int, int, int]) -> None:
    img = Image.new("RGB", (64, 32), color)
    img.save(path, format="PNG")


def _assert_images_close(path_a: Path, path_b: Path, *, tolerance: int = 2) -> None:
    with Image.open(path_a) as img_a, Image.open(path_b) as img_b:
        a_rgb = img_a.convert("RGB")
        b_rgb = img_b.convert("RGB")
        assert a_rgb.size == b_rgb.size
        arr_a = np.asarray(a_rgb, dtype=np.int16)
        arr_b = np.asarray(b_rgb, dtype=np.int16)
        diff = np.abs(arr_a - arr_b)
        assert diff.max() <= tolerance


def _create_drought_frames(frames_dir: Path) -> list[Path]:
    frames_dir.mkdir(parents=True, exist_ok=True)
    colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
    dates = ["20240201", "20240202", "20240203"]
    frames: list[Path] = []
    for color, date in zip(colors, dates, strict=True):
        out = frames_dir / f"DroughtRisk_Weekly_{date}.png"
        _write_color_png(out, color)
        frames.append(out)
    return frames


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
    legend_path = tmp_path / "legend.png"
    legend_path.write_bytes(_tiny_png())
    shared_gradient_path = tmp_path / "shared_grad.png"
    shared_gradient_path.write_bytes(_tiny_png())
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
            "--legend",
            str(legend_path),
            "--shared-gradient",
            f"default={shared_gradient_path}",
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
    assert config.get("legend") == "assets/legends/legend.png"
    shared_map = config.get("shared_gradients")
    assert shared_map and shared_map.get("default") == (
        "assets/gradients/shared/shared_grad.png"
    )
    shared_dest = output_dir / "assets" / "gradients" / "shared" / "shared_grad.png"
    assert shared_dest.exists()


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


def test_visualize_globe_with_json_manifest(tmp_path):
    frames_dir = tmp_path / "frames_json"
    frames_dir.mkdir()
    data = _tiny_png()
    (frames_dir / "frame_a.png").write_bytes(data)
    (frames_dir / "frame_b.png").write_bytes(data)

    manifest_path = frames_dir / "manifest.json"
    manifest = [
        {"path": "frame_a.png", "time": "2024-02-01 12:00"},
        {"path": "frame_b.png", "time": "2024-02-02 12:00"},
    ]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    output_dir = tmp_path / "bundle_manifest"
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
            "--frame-list",
            str(manifest_path),
            "--time-key",
            "time",
            "--time-format",
            "%Y-%m-%d %H:%M",
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
    assert frames[0]["display_timestamp"] == "2024-02-01 12:00"
    assert (output_dir / "assets" / "textures" / "frame_a.png").exists()


def test_visualize_globe_with_probe_dataset(tmp_path):
    nc_path = tmp_path / "probe.nc"
    _write_tiny_netcdf(nc_path)

    output_dir = tmp_path / "bundle_probe_dataset"
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
            "--probe-data",
            str(nc_path),
            "--probe-var",
            "temp",
        ],
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stderr.decode(errors="ignore")
    config = json.loads(
        (output_dir / "assets" / "config.json").read_text(encoding="utf-8")
    )
    assert config.get("probe_data") == "assets/data/probe_probe_points.json"
    assert config.get("probe_units") == "K"
    data_file = output_dir / "assets" / "data" / "probe_probe_points.json"
    assert data_file.exists()


@pytest.mark.skipif(not _ffmpeg_available(), reason="requires ffmpeg")
def test_visualize_globe_with_video_source(tmp_path):
    frames_dir = tmp_path / "video_frames"
    frames = _create_drought_frames(frames_dir)
    video_path = tmp_path / "drought_globe.mp4"
    vp = VideoProcessor(input_directory=str(frames_dir), output_file=str(video_path))
    assert vp.process_video(fps=1, input_glob="*.png")

    output_dir = tmp_path / "bundle_video_cli"
    cache_dir = tmp_path / "frame_cache"
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
            "--video-source",
            str(video_path),
            "--video-start",
            "2024-02-01T00:00:00Z",
            "--video-fps",
            "1",
            "--frame-cache",
            str(cache_dir),
        ],
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stderr.decode(errors="ignore")

    config = json.loads(
        (output_dir / "assets" / "config.json").read_text(encoding="utf-8")
    )
    frames_meta = config.get("frames")
    assert isinstance(frames_meta, list)
    assert len(frames_meta) == len(frames)
    textures_dir = output_dir / "assets" / "textures"
    extracted = sorted(textures_dir.glob("frame_*.png"))
    assert len(extracted) == len(frames)
    for extracted_frame, original in zip(extracted, sorted(frames), strict=False):
        _assert_images_close(extracted_frame, original)


def _tiny_png() -> bytes:
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMAASsJTYQAAAAASUVORK5CYII="
    )


def _write_probe_json(tmp_path):
    probe_path = tmp_path / "probe.json"
    data = [{"lat": 0.0, "lon": 0.0, "value": 42.5, "units": "K"}]
    probe_path.write_text(json.dumps(data), encoding="utf-8")
    return probe_path


def _write_tiny_netcdf(path):
    lat = np.array([-10.0, 0.0, 10.0])
    lon = np.array([0.0, 30.0, 60.0])
    data = np.arange(lat.size * lon.size, dtype=float).reshape(lat.size, lon.size)
    da = xr.DataArray(
        data,
        coords={"lat": lat, "lon": lon},
        dims=("lat", "lon"),
        name="temp",
        attrs={"units": "K"},
    )
    da.to_dataset(name="temp").to_netcdf(path)
