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
        ({"type": "classified", "entries": []}, "at least 2 entries"),
        (
            {"type": "classified", "entries": [{"Color": [1, 1, 1], "Upper Bound": 5}]},
            "at least 2 entries",
        ),
        (
            {
                "type": "continuous",
                "base": "viridis",
                "transparent_range": 200,
                "blend_range": 100,
            },
            "must not exceed",
        ),
        (
            {
                "type": "classified",
                "entries": [
                    {"Upper Bound": 5},
                    {"Color": [1, 1, 1], "Upper Bound": 9},
                ],
            },
            "'Color' key",
        ),
        (
            {
                "type": "classified",
                "entries": [
                    {"Color": [1, 2], "Upper Bound": 5},
                    {"Color": [1, 1, 1], "Upper Bound": 9},
                ],
            },
            r"\[R,G,B\]",
        ),
        (
            {
                "type": "classified",
                "entries": [
                    {"Color": [0, 0, 300], "Upper Bound": 5},
                    {"Color": [1, 1, 1], "Upper Bound": 9},
                ],
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


def test_load_palette_coerces_string_bounds(tmp_path):
    spec = load_palette_spec(
        _write(
            tmp_path,
            {
                "type": "classified",
                "entries": [
                    {"Color": [1, 1, 1], "Upper Bound": "10"},
                    {"Color": [2, 2, 2], "Upper Bound": "20.5"},
                ],
            },
        )
    )
    # Numeric strings are stored back as floats so BoundaryNorm never
    # sees strings.
    assert [e["Upper Bound"] for e in spec["entries"]] == [10.0, 20.5]


def test_write_legend_requires_scale(tmp_path):
    from zyra.visualization.cli_utils import write_legend

    with pytest.raises(ValueError, match="requires --vmin and --vmax"):
        write_legend(str(tmp_path / "l.png"), cmap="turbo")
    with pytest.raises(ValueError, match="requires --vmin and --vmax"):
        write_legend(str(tmp_path / "l.png"), cmap="turbo", vmin=0)


def test_resolve_levels_distinguishes_default_from_explicit():
    from types import SimpleNamespace

    from zyra.visualization.cli_contour import _resolve_levels

    sentinel_norm = object()
    # Omitted: palette bounds when classified, historical default otherwise.
    assert _resolve_levels(SimpleNamespace(levels=None), sentinel_norm) is None
    assert _resolve_levels(SimpleNamespace(levels=None), None) == 10
    # Explicit values always win, including an explicit 10.
    assert _resolve_levels(SimpleNamespace(levels="10"), sentinel_norm) == 10
    assert _resolve_levels(SimpleNamespace(levels="12"), None) == 12


def test_api_schema_cmap_exclusive_and_orientation():
    from zyra.api.schemas.domain_args import (
        VisualizeContourArgs,
        VisualizeHeatmapArgs,
    )

    with pytest.raises(ValueError, match="mutually exclusive"):
        VisualizeHeatmapArgs(cmap="turbo", cmap_file="p.json")
    with pytest.raises(ValueError, match="mutually exclusive"):
        VisualizeContourArgs(output="o.png", cmap="turbo", cmap_file="p.json")
    with pytest.raises(ValueError, match="horizontal.*vertical"):
        VisualizeHeatmapArgs(legend_orientation="diagonal")
    # Valid combinations survive.
    VisualizeHeatmapArgs(cmap_file="p.json", legend_orientation="vertical")


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
    assert "at least 2 entries" in proc.stderr
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


@pytest.mark.skipif(
    _skip_cartopy_heavy,
    reason="Cartopy-heavy tests require cartopy and opt-in (DATAVIZHUB_RUN_CARTOPY_TESTS=1)",
)
def test_unfilled_contour_honors_palette(tmp_path):
    # Line contours must follow the palette cmap/norm (previously only
    # --filled did; unfilled silently fell back to the default cmap).
    import matplotlib

    matplotlib.use("Agg")
    import numpy as np

    from zyra.visualization.cli_utils import cmap_norm_from_palette
    from zyra.visualization.contour_manager import ContourManager

    spec = load_palette_spec(_write(tmp_path, CLASSIFIED))
    cmap, norm = cmap_norm_from_palette(spec)
    data = np.linspace(0, 45, 800, dtype="float32").reshape(20, 40)
    mgr = ContourManager(extent=[-180, 180, -90, 90], filled=False)
    fig = mgr.render(data, cmap=cmap, norm=norm, features=[])
    contour_sets = [
        c for ax in fig.axes for c in ax.collections if hasattr(c, "get_cmap")
    ]
    assert contour_sets, "no contour collections found"
    assert contour_sets[0].get_cmap().name == "custom_colormap"
    assert contour_sets[0].norm is norm


# ---- URL palettes (--cmap-file) ------------------------------------------
# A palette hosted next to the portal that renders the visualization had
# to be staged locally first, which costs a whole pipeline stage under a
# fixed stage budget. Every other zyra input is already URL-aware.


def test_load_palette_from_http_url(monkeypatch):
    from zyra.connectors.backends import http as http_backend

    monkeypatch.setattr(
        http_backend, "fetch_bytes", lambda url, **kw: json.dumps(CONTINUOUS).encode()
    )
    spec = load_palette_spec("https://example.org/palettes/smoke.json")
    assert spec["type"] == "continuous"
    assert spec["base"] == "YlOrBr"


def test_load_palette_from_s3_url(monkeypatch):
    from zyra.connectors.backends import s3 as s3_backend

    monkeypatch.setattr(
        s3_backend, "fetch_bytes", lambda url, **kw: json.dumps(CLASSIFIED).encode()
    )
    spec = load_palette_spec("s3://bucket/palettes/refl.json")
    assert len(spec["entries"]) == 4


def test_url_palette_renders_identically_to_local_file(tmp_path):
    # End-to-end over real HTTP (loopback), not a monkeypatched backend:
    # the colormap built from a URL palette must match the one built from
    # the same bytes on disk.
    pytest.importorskip("matplotlib")
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    from zyra.visualization.cli_utils import cmap_norm_from_palette

    body = json.dumps(CLASSIFIED).encode()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler API
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):  # keep pytest output clean
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/palette.json"
        from_url = load_palette_spec(url)
    finally:
        server.shutdown()
        server.server_close()

    from_file = load_palette_spec(_write(tmp_path, CLASSIFIED))
    assert from_url == from_file

    import numpy as np

    cmap_u, norm_u = cmap_norm_from_palette(from_url)
    cmap_f, norm_f = cmap_norm_from_palette(from_file)
    assert np.array_equal(cmap_u(range(cmap_u.N)), cmap_f(range(cmap_f.N)))
    assert list(norm_u.boundaries) == list(norm_f.boundaries)


def test_load_palette_url_fetch_failure_names_the_url():
    # Port 1 refuses immediately — no DNS, no network dependency.
    url = "http://127.0.0.1:1/palette.json"
    with pytest.raises(ValueError, match="Cannot read palette file") as excinfo:
        load_palette_spec(url)
    assert url in str(excinfo.value)


def test_load_palette_url_bad_json_matches_local_message(monkeypatch):
    from zyra.connectors.backends import http as http_backend

    monkeypatch.setattr(http_backend, "fetch_bytes", lambda url, **kw: b"{not json")
    with pytest.raises(ValueError, match="not valid JSON"):
        load_palette_spec("https://example.org/p.json")


def test_load_palette_url_non_utf8(monkeypatch):
    # A URL that serves an image (or any binary) must not surface as a
    # UnicodeDecodeError traceback.
    from zyra.connectors.backends import http as http_backend

    monkeypatch.setattr(http_backend, "fetch_bytes", lambda url, **kw: b"\xff\xfe\x00")
    with pytest.raises(ValueError, match="not UTF-8"):
        load_palette_spec("https://example.org/p.png")


def test_cli_unreachable_palette_url_exits_2(tmp_path):
    import subprocess
    import sys

    url = "http://127.0.0.1:1/palette.json"
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "zyra.cli",
            "visualize",
            "heatmap",
            "--input",
            str(tmp_path / "any.npy"),
            "--output",
            str(tmp_path / "o.png"),
            "--cmap-file",
            url,
        ],
        capture_output=True,
        text=True,
        check=False,
        # Never let an ambient proxy turn a refused connection into a
        # slow upstream error.
        env={**os.environ, "no_proxy": "*", "NO_PROXY": "*"},
    )
    assert proc.returncode == 2
    assert url in proc.stderr
    assert "Traceback" not in proc.stderr
