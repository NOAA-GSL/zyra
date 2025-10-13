# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import base64
import json

from zyra.visualization.renderers import available, create


def test_globe_renderers_registered() -> None:
    slugs = {renderer.slug for renderer in available()}
    assert "webgl-sphere" in slugs
    assert "cesium-globe" in slugs


def test_webgl_renderer_builds_bundle(tmp_path) -> None:
    renderer = create("webgl-sphere", width=640, height=360)
    bundle = renderer.build(output_dir=tmp_path)

    assert bundle.index_html.exists()
    html = bundle.index_html.read_text(encoding="utf-8")
    assert "Zyra WebGL Sphere" in html
    assert "window.ZYRA_GLOBE_CONFIG" in html

    asset_paths = {path.name for path in bundle.assets}
    assert asset_paths == {"sphere.js", "config.json"}

    config_path = next(path for path in bundle.assets if path.name == "config.json")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    assert config.get("width") == 640
    assert config.get("height") == 360


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


def test_webgl_renderer_with_gradient_and_lut(tmp_path) -> None:
    gradient_path = tmp_path / "gradient.png"
    lut_path = tmp_path / "lut.json"
    gradient_path.write_bytes(_tiny_png())
    lut_path.write_text('{"a":1}', encoding="utf-8")

    renderer = create(
        "webgl-sphere",
        probe_gradient=str(gradient_path),
        probe_lut=str(lut_path),
    )
    bundle = renderer.build(output_dir=tmp_path / "bundle_grad")

    config = json.loads(
        (bundle.index_html.parent / "assets" / "config.json").read_text(
            encoding="utf-8"
        )
    )
    assert config.get("probe_gradient") == "assets/gradients/gradient.png"
    assert config.get("probe_lut") == "assets/gradients/lut.json"

    gradients_dir = bundle.output_dir / "assets" / "gradients"
    assert (gradients_dir / "gradient.png").exists()
    assert (gradients_dir / "lut.json").exists()


def test_cesium_renderer_with_gradient_and_lut(tmp_path) -> None:
    gradient_path = tmp_path / "gradient.png"
    lut_path = tmp_path / "lut.json"
    gradient_path.write_bytes(_tiny_png())
    lut_path.write_text('{"a":1}', encoding="utf-8")

    renderer = create(
        "cesium-globe",
        probe_gradient=str(gradient_path),
        probe_lut=str(lut_path),
    )
    bundle = renderer.build(output_dir=tmp_path / "cesium_bundle")

    config = json.loads(
        (bundle.index_html.parent / "assets" / "config.json").read_text(
            encoding="utf-8"
        )
    )
    assert config.get("probe_gradient") == "assets/gradients/gradient.png"
    assert config.get("probe_lut") == "assets/gradients/lut.json"

    gradients_dir = bundle.output_dir / "assets" / "gradients"
    assert (gradients_dir / "gradient.png").exists()
    assert (gradients_dir / "lut.json").exists()


def _tiny_png() -> bytes:
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMAASsJTYQAAAAASUVORK5CYII="
    )
