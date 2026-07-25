# SPDX-License-Identifier: Apache-2.0
"""``--output-names`` for batch stages (issue: frames had no valid time).

Batch commands name outputs after their input, which keeps a chain of
batch stages aligned without restating filenames — but it also means an
output's identity is whatever the source happened to be called. For
NOAA GRIB2 products that name is cycle-relative
(``gefs.chem.t12z.a2d_0p25.f000``): cycle hour and forecast hour, no
date, so two different cycles produce identical filenames.

That blocks ``process scan-frames``, which derives start/end times purely
by parsing timestamps out of frame filenames. The end-to-end test at the
bottom is the reason this flag exists.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys

import pytest

from zyra.utils.cli_helpers import resolve_batch_output_names


def _parse(registrar, argv):
    parser = argparse.ArgumentParser()
    registrar(parser.add_subparsers(dest="cmd"))
    return parser.parse_args(argv)


# ---- the resolver ---------------------------------------------------------


def test_derives_names_when_not_supplied():
    out = resolve_batch_output_names(
        ["a/x.grib2", "b/y.grib2"], None, derive=lambda s: s.split("/")[-1] + ".tif"
    )
    assert out == ["x.grib2.tif", "y.grib2.tif"]


def test_explicit_names_win_positionally():
    out = resolve_batch_output_names(
        ["a/x.grib2", "b/y.grib2"], ["first.tif", "second.tif"], derive=lambda s: "NOPE"
    )
    assert out == ["first.tif", "second.tif"]


def test_length_mismatch_names_both_counts():
    with pytest.raises(ValueError, match=r"1 names for 2 inputs"):
        resolve_batch_output_names(["a", "b"], ["only.tif"], derive=str)


def test_duplicate_explicit_names_rejected():
    # Two entries resolving to one destination silently loses a frame.
    with pytest.raises(ValueError, match=r"--output-names repeats 'same\.tif'"):
        resolve_batch_output_names(["a", "b"], ["same.tif", "same.tif"], derive=str)


def test_colliding_derived_names_keep_their_own_wording():
    # A derived collision is the caller's *inputs* sharing a basename, not
    # a name typed twice; the message that ships today says so and stays.
    with pytest.raises(ValueError, match="share a filename"):
        resolve_batch_output_names(
            ["d1/f.tif", "d2/f.tif"], None, derive=lambda s: s.split("/")[-1]
        )


def test_empty_batch_is_not_an_error_here():
    # Emptiness is the caller's contract to enforce; the resolver just
    # agrees that zero names match zero inputs.
    assert resolve_batch_output_names([], [], derive=str) == []


# ---- parser surface -------------------------------------------------------


@pytest.mark.parametrize(
    ("domain", "argv"),
    [
        ("process", ["convert-format", "geotiff", "--inputs", "a", "b"]),
        ("process", ["reproject", "--inputs", "a", "b"]),
        ("visualize", ["heatmap", "--inputs", "a", "b"]),
        ("visualize", ["contour", "--inputs", "a", "b"]),
    ],
    ids=["convert-format", "reproject", "heatmap", "contour"],
)
def test_output_names_parses_on_every_batch_command(domain, argv):
    if domain == "process":
        from zyra.processing import register_cli
    else:
        from zyra.visualization.cli_register import register_cli

    ns = _parse(
        register_cli, [*argv, "--output-dir", "out", "--output-names", "x", "y"]
    )
    assert ns.output_names == ["x", "y"]
    # Repeated-flag expansion (the Domain API style) accumulates too.
    ns = _parse(
        register_cli,
        [*argv, "--output-dir", "out", "--output-names", "x", "--output-names", "y"],
    )
    assert ns.output_names == ["x", "y"]
    # Unset stays None rather than [].
    ns = _parse(register_cli, [*argv, "--output-dir", "out"])
    assert ns.output_names is None


def test_schemas_accept_output_names():
    from zyra.api.schemas.domain_args import (
        ProcessConvertFormatArgs,
        ProcessReprojectArgs,
        VisualizeContourArgs,
        VisualizeHeatmapArgs,
    )

    assert ProcessConvertFormatArgs(
        format="geotiff", inputs=["a"], output_dir="o", output_names=["n.tif"]
    ).output_names == ["n.tif"]
    assert ProcessReprojectArgs(
        inputs=["a"], output_dir="o", output_names=["n.tif"]
    ).output_names == ["n.tif"]
    assert VisualizeHeatmapArgs(
        inputs=["a"], output_dir="o", output_names=["n.png"]
    ).output_names == ["n.png"]
    assert VisualizeContourArgs(
        inputs=["a"], output_dir="o", output_names=["n.png"]
    ).output_names == ["n.png"]


# ---- end to end -----------------------------------------------------------


def test_valid_time_names_make_scan_frames_report_real_dates(tmp_path):
    """The reason this flag exists.

    Cycle-relative names give ``scan-frames`` nothing to parse, so
    ``start_datetime``/``end_datetime`` come back null. Naming the same
    frames by valid time makes them real.
    """
    pytest.importorskip("PIL")
    from PIL import Image

    frames = tmp_path / "frames"
    frames.mkdir()

    cycle_relative = [
        "gefs.chem.t12z.a2d_0p25.f000.png",
        "gefs.chem.t12z.a2d_0p25.f006.png",
    ]
    valid_time = ["20260724T120000.png", "20260724T180000.png"]

    def _scan(directory, extra=()):
        out = tmp_path / f"meta-{directory.name}.json"
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "zyra.cli",
                "process",
                "scan-frames",
                "--frames-dir",
                str(directory),
                "--output",
                str(out),
                *extra,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 0, proc.stderr
        return json.loads(out.read_text())

    # Baseline: cycle-relative names carry no date.
    before = tmp_path / "before"
    before.mkdir()
    for name in cycle_relative:
        Image.new("RGB", (2, 2)).save(before / name)
    meta = _scan(before)
    assert meta["start_datetime"] is None
    assert meta["end_datetime"] is None

    # Same frames, named by valid time.
    for name in valid_time:
        Image.new("RGB", (2, 2)).save(frames / name)
    meta = _scan(
        frames, ["--datetime-format", "%Y%m%dT%H%M%S", "--period-seconds", "21600"]
    )
    assert meta["start_datetime"].startswith("2026-07-24T12:00:00")
    assert meta["end_datetime"].startswith("2026-07-24T18:00:00")
    assert meta["period_seconds"] == 21600


def test_cli_length_mismatch_exits_2(tmp_path):
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "zyra.cli",
            "visualize",
            "heatmap",
            "--inputs",
            "a.tif",
            "b.tif",
            "--output-dir",
            str(tmp_path / "out"),
            "--output-names",
            "only-one.png",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 2, proc.stderr
    assert "one entry per --inputs" in proc.stderr
    assert "Traceback" not in proc.stderr
