# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import base64
import functools
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

try:  # pragma: no cover - optional dependency check
    import xarray as xr
except ModuleNotFoundError:  # pragma: no cover - optional dependency missing
    pytest.skip("xarray is required for visualization tests", allow_module_level=True)

from zyra.processing.video_processor import VideoProcessor
from zyra.visualization.renderers import available, create


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


def test_globe_renderers_registered() -> None:
    slugs = {renderer.slug for renderer in available()}
    assert "webgl-sphere" in slugs
    assert "cesium-globe" in slugs


def test_webgl_renderer_builds_bundle(tmp_path) -> None:
    renderer = create("webgl-sphere", width=640, height=360)
    bundle = renderer.build(output_dir=tmp_path)

    assert bundle.index_html.exists()
    html = bundle.index_html.read_text(encoding="utf-8")
    assert '<canvas id="zyra-globe">' in html
    assert "data-probe-lat" in html
    assert "window.ZYRA_GLOBE_CONFIG" in html

    asset_paths = {path.name for path in bundle.assets}
    assert asset_paths == {"sphere.js", "config.json"}

    config_path = next(path for path in bundle.assets if path.name == "config.json")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    assert config.get("width") == 640
    assert config.get("height") == 360
    assert config.get("show_controls") is True


def test_cesium_renderer_builds_bundle(tmp_path) -> None:
    renderer = create("cesium-globe", width=800, height=600)
    bundle = renderer.build(output_dir=tmp_path)

    assert bundle.index_html.exists()
    html = bundle.index_html.read_text(encoding="utf-8")
    assert "Zyra Cesium Globe" in html
    assert "Cesium.js" in html

    asset_paths = {path.name for path in bundle.assets}
    assert asset_paths == {"cesium.js", "config.json"}

    config_path = next(path for path in bundle.assets if path.name == "config.json")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    assert config.get("width") == 800
    assert config.get("height") == 600


def test_webgl_renderer_with_texture(tmp_path) -> None:
    texture_path = tmp_path / "dummy.png"
    texture_path.write_bytes(_tiny_png())

    renderer = create("webgl-sphere", texture=str(texture_path))
    bundle = renderer.build(output_dir=tmp_path / "bundle")

    config_path = next(path for path in bundle.assets if path.name == "config.json")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    assert config.get("texture") == "assets/textures/dummy.png"

    staged = tmp_path / "bundle" / "assets" / "textures" / "dummy.png"
    assert staged.exists()


def test_webgl_renderer_with_legend(tmp_path) -> None:
    legend_path = tmp_path / "legend.png"
    legend_path.write_bytes(_tiny_png())

    renderer = create("webgl-sphere", legend=str(legend_path))
    bundle = renderer.build(output_dir=tmp_path / "bundle_legend")

    config = json.loads(
        (bundle.output_dir / "assets" / "config.json").read_text(encoding="utf-8")
    )
    assert config.get("legend") == "assets/legends/legend.png"

    legends_dir = bundle.output_dir / "assets" / "legends"
    assert (legends_dir / "legend.png").exists()


def test_webgl_renderer_with_remote_texture(tmp_path) -> None:
    raw_url = "https:/example.com/remote_texture.jpg"
    expected_url = "https://example.com/remote_texture.jpg"

    renderer = create("webgl-sphere", texture=raw_url)
    bundle = renderer.build(output_dir=tmp_path / "bundle_remote")

    config_path = next(path for path in bundle.assets if path.name == "config.json")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    assert config.get("texture") == expected_url

    textures_dir = bundle.output_dir / "assets" / "textures"
    assert not textures_dir.exists() or not any(textures_dir.iterdir())


def test_webgl_renderer_with_frame_pattern(tmp_path) -> None:
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    data = _tiny_png()
    (frames_dir / "frame_01.png").write_bytes(data)
    (frames_dir / "frame_02.png").write_bytes(data)

    renderer = create(
        "webgl-sphere",
        texture_pattern=str(frames_dir / "*.png"),
        animate="time",
    )
    bundle = renderer.build(output_dir=tmp_path / "bundle_frames")

    config_path = next(path for path in bundle.assets if path.name == "config.json")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    frames = config.get("frames")
    assert isinstance(frames, list)
    assert len(frames) == 2
    assert frames[0]["path"].endswith("frame_01.png")
    assert config.get("texture").endswith("frame_01.png")

    staged = bundle.output_dir / "assets" / "textures"
    assert (staged / "frame_01.png").exists()
    assert (staged / "frame_02.png").exists()


def test_webgl_renderer_with_frame_pattern_and_date_format(tmp_path) -> None:
    frames_dir = tmp_path / "frames_date"
    frames_dir.mkdir()
    data = _tiny_png()
    (frames_dir / "DroughtRisk_Weekly_20250101.png").write_bytes(data)
    (frames_dir / "DroughtRisk_Weekly_20250108.png").write_bytes(data)

    renderer = create(
        "webgl-sphere",
        texture_pattern=str(frames_dir / "DroughtRisk_Weekly_*.png"),
        frame_date_format="%Y%m%d",
        animate="time",
    )
    bundle = renderer.build(output_dir=tmp_path / "bundle_frames_date")

    config_path = next(path for path in bundle.assets if path.name == "config.json")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    frames = config.get("frames")
    assert isinstance(frames, list)
    assert frames[0]["timestamp"].startswith("2025-01-01")


def test_cesium_renderer_with_frame_pattern(tmp_path) -> None:
    frames_dir = tmp_path / "frames_cesium"
    frames_dir.mkdir()
    data = _tiny_png()
    (frames_dir / "DroughtRisk_Weekly_20240201.png").write_bytes(data)
    (frames_dir / "DroughtRisk_Weekly_20240208.png").write_bytes(data)

    renderer = create(
        "cesium-globe",
        texture_pattern=str(frames_dir / "DroughtRisk_Weekly_*.png"),
        date_format="%Y%m%d",
        animate="time",
    )
    bundle = renderer.build(output_dir=tmp_path / "bundle_cesium_frames")

    config_path = next(path for path in bundle.assets if path.name == "config.json")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    frames = config.get("frames")
    assert isinstance(frames, list)
    assert len(frames) == 2
    assert frames[0]["path"].endswith("DroughtRisk_Weekly_20240201.png")
    assert frames[0]["timestamp"].startswith("2024-02-01")


def test_webgl_renderer_with_gradient_and_lut(tmp_path) -> None:
    gradient_path = tmp_path / "gradient.png"
    lut_path = tmp_path / "lut.json"
    gradient_path.write_bytes(_tiny_png())
    lut_path.write_text('{"a":1}', encoding="utf-8")
    probe_path = _write_probe_json(tmp_path)

    renderer = create(
        "webgl-sphere",
        probe_gradient=str(gradient_path),
        probe_lut=str(lut_path),
        probe_data=str(probe_path),
    )
    bundle = renderer.build(output_dir=tmp_path / "bundle_grad")

    config = json.loads(
        (bundle.index_html.parent / "assets" / "config.json").read_text(
            encoding="utf-8"
        )
    )
    assert config.get("probe_gradient") == "assets/gradients/gradient.png"
    assert config.get("probe_lut") == "assets/gradients/lut.json"
    assert config.get("probe_data") == "assets/data/probe.json"

    gradients_dir = bundle.output_dir / "assets" / "gradients"
    assert (gradients_dir / "gradient.png").exists()
    assert (gradients_dir / "lut.json").exists()
    data_dir = bundle.output_dir / "assets" / "data"
    assert (data_dir / "probe.json").exists()


def test_cesium_renderer_with_gradient_and_lut(tmp_path) -> None:
    gradient_path = tmp_path / "gradient.png"
    lut_path = tmp_path / "lut.json"
    gradient_path.write_bytes(_tiny_png())
    lut_path.write_text('{"a":1}', encoding="utf-8")
    probe_path = _write_probe_json(tmp_path)

    renderer = create(
        "cesium-globe",
        probe_gradient=str(gradient_path),
        probe_lut=str(lut_path),
        probe_data=str(probe_path),
    )
    bundle = renderer.build(output_dir=tmp_path / "cesium_bundle")

    config = json.loads(
        (bundle.index_html.parent / "assets" / "config.json").read_text(
            encoding="utf-8"
        )
    )
    assert config.get("probe_gradient") == "assets/gradients/gradient.png"
    assert config.get("probe_lut") == "assets/gradients/lut.json"
    assert config.get("probe_data") == "assets/data/probe.json"

    gradients_dir = bundle.output_dir / "assets" / "gradients"
    assert (gradients_dir / "gradient.png").exists()
    assert (gradients_dir / "lut.json").exists()
    data_dir = bundle.output_dir / "assets" / "data"
    assert (data_dir / "probe.json").exists()


def test_cesium_renderer_with_legend(tmp_path) -> None:
    legend_path = tmp_path / "legend.png"
    legend_path.write_bytes(_tiny_png())

    renderer = create("cesium-globe", legend=str(legend_path))
    bundle = renderer.build(output_dir=tmp_path / "cesium_legend")

    config = json.loads(
        (bundle.index_html.parent / "assets" / "config.json").read_text(
            encoding="utf-8"
        )
    )
    assert config.get("legend") == "assets/legends/legend.png"

    legends_dir = bundle.output_dir / "assets" / "legends"
    assert (legends_dir / "legend.png").exists()


def test_webgl_renderer_with_shared_gradients(tmp_path) -> None:
    gradient_path = tmp_path / "shared.png"
    gradient_path.write_bytes(_tiny_png())

    renderer = create(
        "webgl-sphere",
        shared_gradients={"default": str(gradient_path)},
    )
    bundle = renderer.build(output_dir=tmp_path / "bundle_shared_grad")

    config = json.loads(
        (bundle.index_html.parent / "assets" / "config.json").read_text(
            encoding="utf-8"
        )
    )
    shared = config.get("shared_gradients")
    assert isinstance(shared, dict)
    assert shared["default"].startswith("assets/gradients/shared/")

    gradients_dir = bundle.output_dir / "assets" / "gradients" / "shared"
    assert (gradients_dir / "shared.png").exists()


@pytest.mark.skipif(not _ffmpeg_available(), reason="requires ffmpeg")
def test_webgl_renderer_with_video_source(tmp_path) -> None:
    frames_dir = tmp_path / "drought_frames"
    frames = _create_drought_frames(frames_dir)
    video_path = tmp_path / "drought.mp4"
    vp = VideoProcessor(input_directory=str(frames_dir), output_file=str(video_path))
    assert vp.process_video(fps=1, input_glob="*.png")

    cache_dir = tmp_path / "video_cache"
    renderer = create(
        "webgl-sphere",
        video_source=str(video_path),
        video_start="2024-02-01T00:00:00Z",
        video_fps=1.0,
        frame_cache=str(cache_dir),
    )
    bundle = renderer.build(output_dir=tmp_path / "bundle_video")

    config = json.loads(
        (bundle.index_html.parent / "assets" / "config.json").read_text(
            encoding="utf-8"
        )
    )
    assert config.get("video_start") == "2024-02-01T00:00:00Z"
    assert config.get("video_end") == "2024-02-01T00:00:02Z"
    frames_meta = config.get("frames")
    assert isinstance(frames_meta, list)
    assert len(frames_meta) == len(frames)
    expected_times = [
        (datetime(2024, 2, 1, tzinfo=timezone.utc) + timedelta(seconds=i))
        .isoformat()
        .replace("+00:00", "Z")
        for i in range(len(frames))
    ]
    assert [frame["timestamp"] for frame in frames_meta] == expected_times

    textures_dir = bundle.output_dir / "assets" / "textures"
    extracted = sorted(textures_dir.glob("frame_*.png"))
    assert len(extracted) == len(frames)
    for extracted_frame, original in zip(extracted, sorted(frames), strict=False):
        _assert_images_close(extracted_frame, original)


@pytest.mark.skipif(not _ffmpeg_available(), reason="requires ffmpeg")
def test_webgl_renderer_video_with_period_override(tmp_path) -> None:
    frames_dir = tmp_path / "drought_frames_period"
    frames = _create_drought_frames(frames_dir)
    video_path = tmp_path / "drought_period.mp4"
    vp = VideoProcessor(input_directory=str(frames_dir), output_file=str(video_path))
    assert vp.process_video(fps=1, input_glob="*.png")

    meta_path = tmp_path / "frames_meta.json"
    meta_path.write_text(
        json.dumps(
            {
                "start_datetime": "2024-02-01T00:00:00Z",
                "period_seconds": 604800,
                "frame_count_actual": len(frames),
            }
        ),
        encoding="utf-8",
    )

    renderer = create(
        "webgl-sphere",
        video_source=str(video_path),
        video_fps=1.0,
        frames_meta=str(meta_path),
    )
    bundle = renderer.build(output_dir=tmp_path / "bundle_video_period")

    config = json.loads(
        (bundle.index_html.parent / "assets" / "config.json").read_text(
            encoding="utf-8"
        )
    )
    frames_meta = config.get("frames")
    assert isinstance(frames_meta, list)
    assert len(frames_meta) == len(frames)

    expected_times = [
        (datetime(2024, 2, 1, tzinfo=timezone.utc) + timedelta(days=7 * i))
        .isoformat()
        .replace("+00:00", "Z")
        for i in range(len(frames))
    ]
    assert [frame["timestamp"] for frame in frames_meta] == expected_times
    assert config.get("timeline_period_seconds") == 604800
    assert config.get("timeline_source") == "frames-meta"
    assert frames_meta[1]["metadata"]["elapsed_seconds"] == pytest.approx(604800.0)


@pytest.mark.skipif(not _ffmpeg_available(), reason="requires ffmpeg")
def test_cesium_renderer_with_video_source(tmp_path) -> None:
    frames_dir = tmp_path / "drought_frames_cesium"
    frames = _create_drought_frames(frames_dir)
    video_path = tmp_path / "drought_cesium.mp4"
    vp = VideoProcessor(input_directory=str(frames_dir), output_file=str(video_path))
    assert vp.process_video(fps=1, input_glob="*.png")

    cache_dir = tmp_path / "video_cache_cesium"
    renderer = create(
        "cesium-globe",
        video_source=str(video_path),
        video_start="2024-02-01T00:00:00Z",
        video_fps=1.0,
        frame_cache=str(cache_dir),
    )
    bundle = renderer.build(output_dir=tmp_path / "cesium_video")

    config = json.loads(
        (bundle.index_html.parent / "assets" / "config.json").read_text(
            encoding="utf-8"
        )
    )
    frames_meta = config.get("frames")
    assert isinstance(frames_meta, list)
    assert len(frames_meta) == len(frames)
    textures_dir = bundle.output_dir / "assets" / "textures"
    extracted = sorted(textures_dir.glob("frame_*.png"))
    assert len(extracted) == len(frames)
    for extracted_frame, original in zip(extracted, sorted(frames), strict=False):
        _assert_images_close(extracted_frame, original)


def test_webgl_renderer_with_netcdf_probe(tmp_path) -> None:
    nc_path = tmp_path / "probe.nc"
    _write_tiny_netcdf(nc_path)

    renderer = create(
        "webgl-sphere",
        probe_data=str(nc_path),
        probe_var="temp",
    )
    bundle = renderer.build(output_dir=tmp_path / "bundle_probe_nc")

    config = json.loads(
        (bundle.index_html.parent / "assets" / "config.json").read_text(
            encoding="utf-8"
        )
    )
    assert config.get("probe_data") == "assets/data/probe_probe_points.json"
    assert config.get("probe_units") == "K"
    data_file = bundle.output_dir / "assets" / "data" / "probe_probe_points.json"
    assert data_file.exists()
    payload = json.loads(data_file.read_text(encoding="utf-8"))
    assert payload and payload[0]["value"] == 0.0


def test_cesium_renderer_with_shared_gradients(tmp_path) -> None:
    gradient_path = tmp_path / "shared.png"
    gradient_path.write_bytes(_tiny_png())

    renderer = create(
        "cesium-globe",
        shared_gradients={"primary": str(gradient_path)},
    )
    bundle = renderer.build(output_dir=tmp_path / "cesium_shared_grad")

    config = json.loads(
        (bundle.index_html.parent / "assets" / "config.json").read_text(
            encoding="utf-8"
        )
    )
    shared = config.get("shared_gradients")
    assert isinstance(shared, dict)
    assert shared["primary"].startswith("assets/gradients/shared/")

    gradients_dir = bundle.output_dir / "assets" / "gradients" / "shared"
    assert (gradients_dir / "shared.png").exists()


def test_cesium_renderer_with_netcdf_probe(tmp_path) -> None:
    nc_path = tmp_path / "probe.nc"
    _write_tiny_netcdf(nc_path)

    renderer = create(
        "cesium-globe",
        probe_data=str(nc_path),
        probe_var="temp",
    )
    bundle = renderer.build(output_dir=tmp_path / "cesium_probe_nc")

    config = json.loads(
        (bundle.index_html.parent / "assets" / "config.json").read_text(
            encoding="utf-8"
        )
    )
    assert config.get("probe_data") == "assets/data/probe_probe_points.json"
    assert config.get("probe_units") == "K"
    data_file = bundle.output_dir / "assets" / "data" / "probe_probe_points.json"
    assert data_file.exists()


def test_webgl_renderer_with_time_key_and_format(tmp_path) -> None:
    frames_dir = tmp_path / "frames_json"
    frames_dir.mkdir()
    data = _tiny_png()
    (frames_dir / "frame_a.png").write_bytes(data)
    (frames_dir / "frame_b.png").write_bytes(data)

    manifest_path = frames_dir / "frames_manifest.json"
    manifest = [
        {"path": "frame_a.png", "time": "2024-02-01 06:00"},
        {"path": "frame_b.png", "time": "2024-02-02 06:00", "label": "Second"},
    ]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    renderer = create(
        "webgl-sphere",
        frame_list=str(manifest_path),
        time_key="time",
        time_format="%Y-%m-%d %H:%M",
        animate="time",
    )
    bundle = renderer.build(output_dir=tmp_path / "bundle_time_key")

    config = json.loads(
        (bundle.index_html.parent / "assets" / "config.json").read_text(
            encoding="utf-8"
        )
    )
    frames = config.get("frames")
    assert isinstance(frames, list)
    assert frames[0]["timestamp"].endswith("Z")
    assert frames[0]["display_timestamp"] == "2024-02-01 06:00"
    textures_dir = bundle.output_dir / "assets" / "textures"
    assert (textures_dir / "frame_a.png").exists()
    assert frames[1]["label"] == "Second"


def test_cesium_renderer_with_time_key_and_format(tmp_path) -> None:
    frames_dir = tmp_path / "frames_json_cesium"
    frames_dir.mkdir()
    data = _tiny_png()
    (frames_dir / "frame_a.png").write_bytes(data)
    (frames_dir / "frame_b.png").write_bytes(data)

    manifest_path = frames_dir / "frames_manifest_cesium.json"
    manifest = [
        {"path": "frame_a.png", "time": "2024-02-01 06:00"},
        {"path": "frame_b.png", "time": "2024-02-02 06:00"},
    ]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    renderer = create(
        "cesium-globe",
        frame_list=str(manifest_path),
        time_key="time",
        time_format="%Y-%m-%d %H:%M",
        animate="time",
    )
    bundle = renderer.build(output_dir=tmp_path / "cesium_time_key")

    config = json.loads(
        (bundle.index_html.parent / "assets" / "config.json").read_text(
            encoding="utf-8"
        )
    )
    frames = config.get("frames")
    assert isinstance(frames, list)
    assert frames[0]["timestamp"].endswith("Z")
    assert frames[0]["display_timestamp"] == "2024-02-01 06:00"
    textures_dir = bundle.output_dir / "assets" / "textures"
    assert (textures_dir / "frame_a.png").exists()


def _tiny_png() -> bytes:
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMAASsJTYQAAAAASUVORK5CYII="
    )


def _write_probe_json(tmp_path) -> Path:
    probe_path = tmp_path / "probe.json"
    data = [{"lat": 0.0, "lon": 0.0, "value": 42.5, "units": "K"}]
    probe_path.write_text(json.dumps(data), encoding="utf-8")
    return probe_path


def _write_tiny_netcdf(path: Path) -> None:
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
    ds = da.to_dataset(name="temp")
    ds.to_netcdf(path)
