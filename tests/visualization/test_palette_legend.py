# SPDX-License-Identifier: Apache-2.0
"""Palette files (--cmap-file) and standalone legends (--legend-file).

Classified palettes (NWS-style boundary tables) and continuous
transparency-ramp specs were Python-API-only; globe display targets
(TerraViz/SOS) need the legend as a separate screen-space image rather
than baked into the frame, where it would wrap onto the globe.
"""

from __future__ import annotations

import json
import os

import pytest

from zyra.visualization.cli_utils import load_palette_spec

CLASSIFIED = {
    "type": "classified",
    "entries": [
        {"Color": [4, 233, 231, 255], "Upper Bound": 10},
        {"Color": [1, 159, 244, 255], "Upper Bound": 20},
        {"Color": [3, 0, 244, 255], "Upper Bound": 30},
        {"Color": [253, 149, 2, 255], "Upper Bound": 40},
    ],
}
CONTINUOUS = {
    "type": "continuous",
    "base": "YlOrBr",
    "transparent_range": 2,
    "blend_range": 8,
    "overall_alpha": 0.9,
}


def _write(tmp_path, spec, name="palette.json"):
    p = tmp_path / name
    p.write_text(json.dumps(spec))
    return str(p)


def test_load_classified_ok(tmp_path):
    spec = load_palette_spec(_write(tmp_path, CLASSIFIED))
    assert spec["type"] == "classified"
    assert len(spec["entries"]) == 4


def test_load_continuous_ok(tmp_path):
    spec = load_palette_spec(_write(tmp_path, CONTINUOUS))
    assert spec["base"] == "YlOrBr"


@pytest.mark.parametrize(
    "mutation,match",
    [
        ({"type": "chromatic"}, "must be 'classified' or 'continuous'"),
        ({"type": "classified", "entries": []}, "non-empty 'entries'"),
        (
            {"type": "classified", "entries": [{"Upper Bound": 5}]},
            "'Color' key",
        ),
        (
            {"type": "classified", "entries": [{"Color": [1, 2], "Upper Bound": 5}]},
            r"\[R,G,B\]",
        ),
        (
            {
                "type": "classified",
                "entries": [{"Color": [0, 0, 300], "Upper Bound": 5}],
            },
            "0-255",
        ),
        (
            {
                "type": "classified",
                "entries": [
                    {"Color": [1, 1, 1], "Upper Bound": 10},
                    {"Color": [2, 2, 2], "Upper Bound": 10},
                ],
            },
            "strictly increasing",
        ),
        ({"type": "continuous"}, "'base' colormap name"),
        (
            {"type": "continuous", "base": "viridis", "transparent_range": -1},
            "non-negative integer",
        ),
        (
            {"type": "continuous", "base": "viridis", "overall_alpha": 1.5},
            "between 0 and 1",
        ),
    ],
)
def test_load_palette_rejects_bad_specs(tmp_path, mutation, match):
    with pytest.raises(ValueError, match=match):
        load_palette_spec(_write(tmp_path, mutation))


def test_load_palette_bad_json(tmp_path):
    p = tmp_path / "broken.json"
    p.write_text("{not json")
    with pytest.raises(ValueError, match="not valid JSON"):
        load_palette_spec(str(p))


def test_load_palette_missing_file(tmp_path):
    with pytest.raises(ValueError, match="Cannot read palette file"):
        load_palette_spec(str(tmp_path / "absent.json"))


def test_cli_parser_accepts_palette_and_legend_flags():
    import argparse

    import zyra.visualization as vpkg

    parser = argparse.ArgumentParser()
    vpkg.register_cli(parser.add_subparsers(dest="cmd"))
    ns = parser.parse_args(
        [
            "heatmap",
            "--input",
            "x.npy",
            "--output",
            "o.png",
            "--cmap-file",
            "p.json",
            "--legend-file",
            "l.png",
            "--legend-orientation",
            "vertical",
        ]
    )
    assert ns.cmap_file == "p.json"
    assert ns.legend_file == "l.png"
    assert ns.legend_orientation == "vertical"
    ns = parser.parse_args(["contour", "--input", "x.npy", "--output", "o.png"])
    assert ns.cmap_file is None
    assert ns.legend_orientation == "horizontal"


def test_cli_cmap_and_cmap_file_mutually_exclusive():
    import argparse

    import zyra.visualization as vpkg

    parser = argparse.ArgumentParser()
    vpkg.register_cli(parser.add_subparsers(dest="cmd"))
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(
            [
                "heatmap",
                "--input",
                "x.npy",
                "--output",
                "o.png",
                "--cmap",
                "turbo",
                "--cmap-file",
                "p.json",
            ]
        )
    assert exc_info.value.code == 2


def test_classified_palette_rejects_vmin_vmax(tmp_path):
    from types import SimpleNamespace

    from zyra.visualization.cli_utils import resolve_cmap_args

    ns = SimpleNamespace(
        cmap_file=_write(tmp_path, CLASSIFIED), cmap=None, vmin=0.0, vmax=60.0
    )
    with pytest.raises(ValueError, match="not valid with a classified palette"):
        resolve_cmap_args(ns)


def test_cmap_norm_from_palette_classified(tmp_path):
    pytest.importorskip("matplotlib")
    from zyra.visualization.cli_utils import cmap_norm_from_palette

    spec = load_palette_spec(_write(tmp_path, CLASSIFIED))
    cmap, norm = cmap_norm_from_palette(spec)
    assert norm is not None and hasattr(norm, "boundaries")
    # Band color survives the round trip (0-255 -> 0-1).
    assert cmap.colors[0] == pytest.approx([4 / 255, 233 / 255, 231 / 255, 1.0])


def test_cmap_norm_from_palette_continuous_ramp(tmp_path):
    pytest.importorskip("matplotlib")
    import numpy as np

    from zyra.visualization.cli_utils import cmap_norm_from_palette

    spec = load_palette_spec(_write(tmp_path, CONTINUOUS))
    cmap, norm = cmap_norm_from_palette(spec)
    assert norm is None
    rgba = cmap(np.linspace(0, 1, 256))
    # Low end transparent, high end capped by overall_alpha.
    assert rgba[0, 3] == 0.0
    assert rgba[-1, 3] == pytest.approx(0.9, abs=0.01)


def test_write_legend_horizontal_and_vertical(tmp_path):
    pytest.importorskip("matplotlib")
    import numpy as np
    from PIL import Image

    from zyra.visualization.cli_utils import write_legend

    for orientation in ("horizontal", "vertical"):
        out = str(tmp_path / f"legend_{orientation}.png")
        write_legend(
            out,
            cmap="turbo",
            vmin=0,
            vmax=60,
            label="Composite reflectivity (dBZ)",
            orientation=orientation,
        )
        img = np.asarray(Image.open(out).convert("RGBA"))
        h, w = img.shape[:2]
        assert (w > h) == (orientation == "horizontal")
        # Transparent background around the bar (corner pixel).
        assert img[0, 0, 3] == 0
        # The bar itself carries opaque color somewhere.
        assert img[:, :, 3].max() == 255


def test_write_legend_classified_bands(tmp_path):
    pytest.importorskip("matplotlib")
    from PIL import Image

    from zyra.visualization.cli_utils import cmap_norm_from_palette, write_legend

    spec = load_palette_spec(_write(tmp_path, CLASSIFIED))
    cmap, norm = cmap_norm_from_palette(spec)
    out = str(tmp_path / "legend_classified.png")
    write_legend(out, cmap=cmap, norm=norm, label="dBZ")
    assert Image.open(out).size[0] > 0


def test_cli_malformed_palette_exits_2(tmp_path):
    import subprocess
    import sys

    import numpy as np

    npy = tmp_path / "d.npy"
    np.save(npy, np.zeros((4, 8), dtype="float32"))
    bad = tmp_path / "bad.json"
    bad.write_text('{"type": "classified", "entries": []}')
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "zyra.cli",
            "visualize",
            "heatmap",
            "--input",
            str(npy),
            "--output",
            str(tmp_path / "o.png"),
            "--cmap-file",
            str(bad),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 2
    assert "non-empty 'entries'" in proc.stderr
    assert "Traceback" not in proc.stderr


# Cartopy-heavy render tests: opt-in via DATAVIZHUB_RUN_CARTOPY_TESTS=1
# (repo convention). Heavy imports stay inside the test bodies so
# collection succeeds in environments without matplotlib/cartopy.
_has_cartopy = False
try:  # pragma: no cover - import guard
    import cartopy  # noqa: F401

    _has_cartopy = True
except Exception:
    pass

_skip_cartopy_heavy = (not _has_cartopy) or os.environ.get(
    "DATAVIZHUB_RUN_CARTOPY_TESTS"
) != "1"


@pytest.mark.skipif(
    _skip_cartopy_heavy,
    reason="Cartopy-heavy tests require cartopy and opt-in (DATAVIZHUB_RUN_CARTOPY_TESTS=1)",
)
def test_heatmap_classified_render_uses_band_colors(tmp_path):
    import matplotlib

    matplotlib.use("Agg")
    import numpy as np
    from PIL import Image

    from zyra.visualization.cli_utils import cmap_norm_from_palette
    from zyra.visualization.heatmap_manager import HeatmapManager

    spec = load_palette_spec(_write(tmp_path, CLASSIFIED))
    cmap, norm = cmap_norm_from_palette(spec)

    # ColormapManager semantic (matches the packaged SOS palettes): the
    # N bounds delimit N-1 bins, so [10,20) maps to entry index 0 and
    # [20,30) to entry index 1. Left third sits below the first bound —
    # under-range renders transparent (no-echo must not flood the frame
    # with the lowest band color).
    data = np.full((20, 60), 2.0, dtype="float32")
    data[:, 20:40] = 15.0
    data[:, 40:] = 25.0

    mgr = HeatmapManager(extent=[-180, 180, -90, 90])
    mgr.render(data, cmap=cmap, norm=norm, features=[])
    out = str(tmp_path / "o.png")
    mgr.save(out)

    img = np.asarray(Image.open(out).convert("RGB")).astype(int)
    h, w = img.shape[:2]
    under = img[h // 2, w // 6]
    band0 = img[h // 2, w // 2]
    band1 = img[h // 2, (5 * w) // 6]
    assert tuple(band0) == (4, 233, 231), f"[10,20) bin color mismatch: {band0}"
    assert tuple(band1) == (1, 159, 244), f"[20,30) bin color mismatch: {band1}"
    # Under-range is transparent: shows the neutral background, not a band.
    assert max(under) - min(under) < 30, f"under-range not background-like: {under}"


@pytest.mark.skipif(
    _skip_cartopy_heavy,
    reason="Cartopy-heavy tests require cartopy and opt-in (DATAVIZHUB_RUN_CARTOPY_TESTS=1)",
)
def test_cli_legend_file_written_frame_unchanged(tmp_path):
    import subprocess
    import sys

    import numpy as np

    npy = tmp_path / "d.npy"
    np.save(npy, np.random.rand(20, 40).astype("float32") * 60)
    frame_plain = tmp_path / "plain.png"
    frame_legend = tmp_path / "with_legend.png"
    legend = tmp_path / "legend.png"

    base = [
        sys.executable,
        "-m",
        "zyra.cli",
        "visualize",
        "heatmap",
        "--input",
        str(npy),
        "--cmap",
        "turbo",
        "--vmin",
        "0",
        "--vmax",
        "60",
    ]
    env = dict(os.environ, DATAVIZHUB_RUN_CARTOPY_TESTS="1")
    r1 = subprocess.run(
        [*base, "--output", str(frame_plain)],
        capture_output=True,
        env=env,
        check=False,
    )
    r2 = subprocess.run(
        [*base, "--output", str(frame_legend), "--legend-file", str(legend)],
        capture_output=True,
        env=env,
        check=False,
    )
    assert r1.returncode == 0 and r2.returncode == 0
    assert legend.exists() and legend.stat().st_size > 0
    # The legend flag must not change the frame bytes.
    assert frame_plain.read_bytes() == frame_legend.read_bytes()
