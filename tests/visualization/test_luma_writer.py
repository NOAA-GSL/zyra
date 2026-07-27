# SPDX-License-Identifier: Apache-2.0
"""Tests for the data-encoded (luma) write path.

The load-bearing one is ``test_round_trip_value_fidelity``: the whole
premise of encoding data rather than a picture is that the value comes
back, so it is asserted directly against the one-8-bit-step budget.

The rest guard the properties that make that possible — an exactly
sized output (the figure pipeline silently resamples, which is why
this path exists at all), nodata landing on 0, and a hard error rather
than an autoscale when the range is missing.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from zyra.visualization.luma_writer import (
    SIDECAR_STOPS,
    build_color_scale,
    normalize_to_luma,
    resize_nearest,
    write_luma_png,
)

pytest.importorskip("PIL")
from PIL import Image  # noqa: E402


def test_normalize_maps_the_range_onto_the_code_range():
    data = np.array([[0.0, 50.0], [100.0, 25.0]])
    codes = normalize_to_luma(data, vmin=0, vmax=100)
    assert codes.dtype == np.uint8
    assert codes[0, 0] == 0
    assert codes[1, 0] == 255
    assert codes[0, 1] == 128  # round(0.5 * 255) == 128


def test_nodata_becomes_zero():
    # 0 is both vmin and the code the palette's transparent range
    # covers, so "nothing measured" and "the bottom of the scale"
    # deliberately coincide.
    data = np.array([[np.nan, 10.0], [np.inf, -np.inf]])
    codes = normalize_to_luma(data, vmin=0, vmax=100)
    assert codes[0, 0] == 0
    assert codes[1, 0] == 255  # +inf clamps to vmax
    assert codes[1, 1] == 0  # -inf clamps to vmin


def test_masked_arrays_are_treated_as_nodata():
    data = np.ma.masked_array([[1.0, 2.0]], mask=[[True, False]])
    codes = normalize_to_luma(data, vmin=0, vmax=2)
    assert codes[0, 0] == 0


def test_values_outside_the_range_clamp_rather_than_wrap():
    data = np.array([[-500.0, 500.0]])
    codes = normalize_to_luma(data, vmin=0, vmax=100)
    assert codes[0, 0] == 0
    assert codes[0, 1] == 255


@pytest.mark.parametrize(
    "vmin,vmax",
    [(None, 100), (0, None), (5, 5), (np.nan, 1)],
)
def test_missing_or_degenerate_range_is_an_error_not_an_autoscale(vmin, vmax):
    # A per-frame autoscale would make luma mean something different
    # in every frame of the same dataset.
    with pytest.raises(ValueError):
        normalize_to_luma(np.array([[1.0, 2.0]]), vmin=vmin, vmax=vmax)


def test_non_2d_input_is_rejected():
    with pytest.raises(ValueError, match="2-D"):
        normalize_to_luma(np.zeros((2, 2, 3)), vmin=0, vmax=1)


def test_round_trip_value_fidelity():
    """Write luma, read it back, assert MAE within one 8-bit step.

    This is the measurement the whole approach rests on.
    """
    rng = np.random.default_rng(1234)
    vmin, vmax = -12.5, 87.5
    source = rng.uniform(vmin, vmax, size=(64, 128))

    codes = normalize_to_luma(source, vmin=vmin, vmax=vmax)
    recovered = vmin + (codes.astype("float64") / 255.0) * (vmax - vmin)

    step = (vmax - vmin) / 255.0
    mae = float(np.mean(np.abs(recovered - source)))
    assert mae <= step, f"MAE {mae} exceeds one 8-bit step {step}"
    assert float(np.max(np.abs(recovered - source))) <= step


def test_output_dimensions_match_the_source_grid_exactly(tmp_path):
    # The reason this path exists: asking the cartopy figure pipeline
    # for exactly the source grid (1799x1059) returns 1799x899.
    data = np.zeros((1059, 1799))
    out = write_luma_png(data, str(tmp_path / "f.png"), vmin=0, vmax=1)
    with Image.open(out) as im:
        assert im.size == (1799, 1059)
        assert im.mode == "L"


def test_explicit_size_resizes_by_nearest_neighbour(tmp_path):
    data = np.zeros((4, 4))
    out = write_luma_png(
        data, str(tmp_path / "f.png"), vmin=0, vmax=1, width=8, height=8
    )
    with Image.open(out) as im:
        assert im.size == (8, 8)


def test_resize_nearest_never_invents_a_value():
    # A hard edge must stay hard. Any interpolating resampler puts a
    # mid-range value on the boundary that nothing measured.
    codes = np.array([[0, 255], [0, 255]], dtype=np.uint8)
    out = resize_nearest(codes, 8, 8)
    assert set(np.unique(out).tolist()) == {0, 255}


def test_resize_is_a_no_op_at_the_source_size():
    codes = np.zeros((3, 5), dtype=np.uint8)
    assert resize_nearest(codes, 5, 3) is codes
    assert resize_nearest(codes, None, None) is codes


@pytest.mark.parametrize(
    ("width", "height"),
    [(0, 0), (0, 3), (5, 0), (-4, 3), (5, -4)],
)
def test_resize_rejects_a_non_positive_size(width, height):
    # 0 is a size, not an absent one. Resolving it to the source
    # dimension would accept an invalid request and silently do
    # something other than what was asked.
    codes = np.zeros((3, 5), dtype=np.uint8)
    with pytest.raises(ValueError, match="must be positive"):
        resize_nearest(codes, width, height)


def test_written_pixels_are_the_codes(tmp_path):
    data = np.array([[0.0, 100.0], [50.0, 25.0]])
    out = write_luma_png(data, str(tmp_path / "f.png"), vmin=0, vmax=100)
    with Image.open(out) as im:
        px = np.asarray(im)
    assert px[0, 0] == 0
    assert px[0, 1] == 255
    assert px[1, 0] == 128


class TestColorScaleSidecar:
    def test_defaults_to_a_greyscale_ramp_without_a_palette(self):
        scale = build_color_scale(None, vmin=0, vmax=10, units="K")
        assert len(scale["stops"]) == SIDECAR_STOPS
        assert scale["stops"][0]["rgba"] == [0, 0, 0, 255]
        assert scale["stops"][-1]["rgba"] == [255, 255, 255, 255]
        assert scale["vmin"] == 0 and scale["vmax"] == 10
        assert scale["units"] == "K"

    def test_stops_are_ordered_and_span_the_unit_interval(self):
        stops = build_color_scale(None, vmin=0, vmax=1)["stops"]
        ts = [s["t"] for s in stops]
        assert ts[0] == 0.0 and ts[-1] == 1.0
        assert ts == sorted(ts)

    def test_continuous_palette_carries_its_transparency_ramp(self):
        spec = {
            "type": "continuous",
            "base": "YlOrBr",
            "transparent_range": 12,
            "blend_range": 8,
        }
        scale = build_color_scale(spec, vmin=0, vmax=50)
        # The published smoke pipeline's value, as a fraction of 256.
        assert scale["transparentRange"] == pytest.approx(12 / 256, abs=1e-6)
        # …and the stops themselves start fully transparent.
        assert scale["stops"][0]["rgba"][3] == 0

    def test_classified_palette_bands_land_on_their_bounds(self):
        spec = {
            "type": "classified",
            "entries": [
                {"Color": [0, 0, 255, 255], "Upper Bound": 0.0},
                {"Color": [255, 0, 0, 255], "Upper Bound": 50.0},
                {"Color": [0, 255, 0, 255], "Upper Bound": 100.0},
            ],
        }
        scale = build_color_scale(spec, vmin=0, vmax=100)
        # t=0.25 -> value 25, inside the first band (0..50) -> blue.
        low = scale["stops"][SIDECAR_STOPS // 4]["rgba"]
        # t=0.75 -> value 75, inside the second band (50..100) -> red.
        high = scale["stops"][(SIDECAR_STOPS * 3) // 4]["rgba"]
        assert low[2] > low[0]
        assert high[0] > high[2]
        assert "transparentRange" not in scale

    def test_units_are_omitted_rather_than_emitted_empty(self):
        assert "units" not in build_color_scale(None, vmin=0, vmax=1)
        assert "units" not in build_color_scale(None, vmin=0, vmax=1, units="")

    def test_degenerate_range_is_an_error(self):
        with pytest.raises(ValueError):
            build_color_scale(None, vmin=3, vmax=3)

    def test_sidecar_is_json_serialisable(self):
        # It is written to a file and later stored in a D1 TEXT column.
        scale = build_color_scale(
            {"type": "continuous", "base": "viridis", "transparent_range": 2},
            vmin=-1,
            vmax=1,
            units="m s-1",
        )
        round_tripped = json.loads(json.dumps(scale))
        assert round_tripped["stops"][0]["rgba"] == scale["stops"][0]["rgba"]


class TestDataEncodedCli:
    """Parity across the four surfaces the plan names.

    A flag that reaches the parser but not the handler (or the API
    model) is silently dropped rather than rejected, so each is
    asserted rather than assumed.
    """

    @staticmethod
    def _ns(**over):
        import argparse

        from zyra.visualization.cli import main as _  # noqa: F401  (registers)
        from zyra.visualization.cli_register import register_cli

        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="cmd")
        register_cli(sub)
        argv = ["heatmap"]
        for key, value in over.items():
            flag = "--" + key.replace("_", "-")
            if value is True:
                argv.append(flag)
            elif value is not None:
                argv.extend([flag, str(value)])
        return parser.parse_args(argv)

    def test_parser_exposes_the_flags(self):
        ns = self._ns(
            input="a.tif",
            output="o.png",
            data_encoded=True,
            color_scale_file="s.json",
            vmin=0,
            vmax=10,
        )
        assert ns.data_encoded is True
        assert ns.color_scale_file == "s.json"
        assert ns.vmin == 0.0 and ns.vmax == 10.0

    def test_defaults_leave_the_picture_path_untouched(self):
        # Backwards compatibility: an ordinary heatmap invocation must
        # not acquire data-encoded behaviour.
        ns = self._ns(input="a.tif", output="o.png")
        assert getattr(ns, "data_encoded", False) is False
        assert getattr(ns, "color_scale_file", None) is None

    def test_handler_writes_frames_and_sidecar(self, tmp_path):
        from zyra.visualization.cli_heatmap import handle_heatmap

        src = tmp_path / "in.npy"
        np.save(src, np.array([[0.0, 100.0], [50.0, 25.0]]))
        out = tmp_path / "out.png"
        sidecar = tmp_path / "scale.json"
        ns = self._ns(
            input=str(src),
            output=str(out),
            data_encoded=True,
            vmin=0,
            vmax=100,
            color_scale_file=str(sidecar),
            units="K",
        )

        assert handle_heatmap(ns) == 0
        with Image.open(out) as im:
            assert im.mode == "L"
            # The source grid, NOT the figure path's 1024x512 default
            # canvas — applying that here would resample every frame.
            assert im.size == (2, 2)
            assert np.asarray(im)[0, 1] == 255
        scale = json.loads(sidecar.read_text())
        assert scale["vmin"] == 0 and scale["vmax"] == 100
        assert scale["units"] == "K"
        assert len(scale["stops"]) == SIDECAR_STOPS

    def test_handler_accepts_a_classified_palette_with_a_range(self, tmp_path):
        # resolve_cmap_args rejects --vmin/--vmax alongside a classified
        # palette, which is right for a picture and wrong here: a
        # data-encoded frame requires them. When that ran ahead of the
        # data-encoded branch, classified + --data-encoded exited 2 and
        # the classified arm of _sample_palette was unreachable.
        pytest.importorskip("matplotlib")
        from zyra.visualization.cli_heatmap import handle_heatmap

        src = tmp_path / "in.npy"
        np.save(src, np.array([[0.0, 100.0], [50.0, 25.0]]))
        palette = tmp_path / "p.json"
        palette.write_text(
            json.dumps(
                {
                    "type": "classified",
                    "entries": [
                        {"Color": [0, 0, 255, 255], "Upper Bound": 0.0},
                        {"Color": [255, 0, 0, 255], "Upper Bound": 50.0},
                        {"Color": [0, 255, 0, 255], "Upper Bound": 100.0},
                    ],
                }
            )
        )
        sidecar = tmp_path / "scale.json"
        ns = self._ns(
            input=str(src),
            output=str(tmp_path / "out.png"),
            data_encoded=True,
            vmin=0,
            vmax=100,
            cmap_file=str(palette),
            color_scale_file=str(sidecar),
        )

        assert handle_heatmap(ns) == 0
        scale = json.loads(sidecar.read_text())
        # The bands came from the palette, not the greyscale fallback
        # (which would put equal values on all three channels).
        assert scale["stops"][SIDECAR_STOPS // 4]["rgba"][:3] == [0, 0, 255]
        assert scale["stops"][3 * SIDECAR_STOPS // 4]["rgba"][:3] == [255, 0, 0]

    def test_handler_exits_2_without_a_range(self, tmp_path):
        from zyra.visualization.cli_heatmap import handle_heatmap

        src = tmp_path / "in.npy"
        np.save(src, np.zeros((2, 2)))
        ns = self._ns(input=str(src), output=str(tmp_path / "o.png"), data_encoded=True)
        # The ValueError -> exit-2 contract, not a traceback and not an
        # autoscale.
        assert handle_heatmap(ns) == 2

    def test_api_model_round_trips_the_new_fields_and_the_range(self):
        from zyra.api.schemas.domain_args import VisualizeHeatmapArgs

        args = VisualizeHeatmapArgs(
            input="a.tif",
            output="o.png",
            data_encoded=True,
            color_scale_file="s.json",
            vmin=0,
            vmax=10,
        )
        assert args.data_encoded is True
        assert args.color_scale_file == "s.json"
        # vmin/vmax used to be dropped silently by extra="ignore".
        assert args.vmin == 0 and args.vmax == 10

    def test_api_model_rejects_data_encoded_without_a_range(self):
        import pydantic

        from zyra.api.schemas.domain_args import VisualizeHeatmapArgs

        with pytest.raises(pydantic.ValidationError):
            VisualizeHeatmapArgs(input="a.tif", output="o.png", data_encoded=True)
