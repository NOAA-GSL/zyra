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


@pytest.mark.parametrize("bad", ["sub/x.tif", "../x.tif", "a\\b.tif", "", ".", ".."])
def test_names_must_be_filenames_not_paths(bad):
    # A separator either points at a directory that does not exist —
    # a traceback rather than a clean error — or climbs out of
    # --output-dir, which matters most over the API where the list
    # arrives in a request body.
    with pytest.raises(ValueError, match="takes filenames, not paths"):
        resolve_batch_output_names(["a.grib2"], [bad], derive=str)


def test_derived_names_are_not_subject_to_the_filename_check():
    # Only supplied names are checked; a derive that returns a path is
    # the caller's own business and no user typed it.
    assert resolve_batch_output_names(["a"], None, derive=lambda s: f"d/{s}") == ["d/a"]


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


# ---- mixed-mode and overwrite guards --------------------------------------


@pytest.mark.parametrize(
    ("argv", "single"),
    [
        (["process", "convert-format"], ["a.grib2", "geotiff"]),
        (["process", "reproject"], ["--input", "a.tif", "--output", "b.tif"]),
        (["visualize", "heatmap"], ["--input", "a.tif", "--output", "b.png"]),
        (["visualize", "contour"], ["--input", "a.tif", "--output", "b.png"]),
    ],
    ids=["convert-format", "reproject", "heatmap", "contour"],
)
def test_output_names_without_inputs_is_rejected(argv, single):
    # The flag is positional against --inputs, so in single-input mode
    # it would rename nothing. Accepting it silently is the failure
    # this guards: the caller believes a rename happened.
    proc = subprocess.run(
        [sys.executable, "-m", "zyra.cli", *argv, *single, "--output-names", "x.png"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "--output-names applies to --inputs" in proc.stderr
    assert "Traceback" not in proc.stderr


def test_convert_format_refuses_to_overwrite_an_input(tmp_path):
    # NetCDF passthrough writes the bytes straight back out. Naming one
    # input's output after a *different* input destroys that file
    # before it is ever read.
    a = tmp_path / "a.nc"
    b = tmp_path / "b.nc"
    a.write_bytes(b"CDF\x01" + b"\0" * 64)
    b.write_bytes(b"CDF\x01" + b"\1" * 64)
    before = b.read_bytes()

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "zyra.cli",
            "process",
            "convert-format",
            "netcdf",
            "--inputs",
            str(a),
            str(b),
            "--output-dir",
            str(tmp_path),
            "--output-names",
            "b.nc",
            "c.nc",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "would overwrite input" in proc.stderr
    assert b.read_bytes() == before, "input was clobbered before the guard fired"


# ---- API parity -----------------------------------------------------------


def test_schemas_reject_what_the_cli_rejects():
    import pytest as _pytest
    from pydantic import ValidationError

    from zyra.api.schemas.domain_args import (
        ProcessConvertFormatArgs,
        ProcessReprojectArgs,
        VisualizeContourArgs,
        VisualizeHeatmapArgs,
    )

    # `single` is a valid single-input form for each model, so the
    # last case isolates output_names as the only thing wrong — some
    # of these models also validate the input form, and that check
    # runs first.
    cases = [
        (ProcessConvertFormatArgs, {"format": "geotiff"}, {"file_or_url": "a.grib2"}),
        (ProcessReprojectArgs, {}, {"input": "a.tif", "output": "b.tif"}),
        (VisualizeHeatmapArgs, {}, {"input": "a.tif", "output": "b.png"}),
        (VisualizeContourArgs, {}, {"input": "a.tif", "output": "b.png"}),
    ]
    for model, extra, single in cases:
        # Wrong count.
        with _pytest.raises(ValidationError, match="one entry per --inputs"):
            model(inputs=["a", "b"], output_dir="o", output_names=["only.tif"], **extra)
        # Duplicate destination.
        with _pytest.raises(ValidationError, match="repeats"):
            model(
                inputs=["a", "b"],
                output_dir="o",
                output_names=["s.tif", "s.tif"],
                **extra,
            )
        # A path where a filename belongs.
        with _pytest.raises(ValidationError, match="filenames, not paths"):
            model(inputs=["a"], output_dir="o", output_names=["sub/x.tif"], **extra)
        # Names with no batch to attach to, on an otherwise-valid
        # single-input request.
        with _pytest.raises(ValidationError, match="output_names requires inputs"):
            model(output_names=["x.tif"], **single, **extra)


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


def test_shared_rules_report_identically_on_both_surfaces():
    """The parity claim in `_validate_batch_output_names`, checked.

    The three shared rules must produce the *same* message from the API
    and the CLI — that is what "cannot drift" means. The missing-inputs
    case deliberately differs, because a JSON body has no `--inputs`
    flag to name; the docstring says so, and this pins both halves so
    the claim stays true.
    """
    import re

    from pydantic import ValidationError

    from zyra.api.schemas.domain_args import VisualizeHeatmapArgs

    def api_message(**kwargs) -> str:
        try:
            VisualizeHeatmapArgs(**kwargs)
        except ValidationError as exc:
            # Pydantic wraps it: a count line, then "Value error, <msg>
            # [type=...]". DOTALL so the leading line is consumed too.
            return re.sub(r".*Value error, ", "", str(exc), flags=re.DOTALL).split(
                " [type"
            )[0]
        raise AssertionError("expected a validation error")

    def cli_message(argv) -> str:
        proc = subprocess.run(
            [sys.executable, "-m", "zyra.cli", "visualize", "heatmap", *argv],
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 2, proc.stderr
        # The logger prefix varies with configuration ("ERROR: " here,
        # "ERROR:root:" under the default root logger).
        return re.sub(r"^ERROR(:root)?:\s*", "", proc.stderr.strip())

    shared = [
        (
            {"inputs": ["a", "b"], "output_dir": "o", "output_names": ["one.png"]},
            ["--inputs", "a", "b", "--output-dir", "o", "--output-names", "one.png"],
        ),
        (
            {
                "inputs": ["a", "b"],
                "output_dir": "o",
                "output_names": ["s.png", "s.png"],
            },
            [
                "--inputs",
                "a",
                "b",
                "--output-dir",
                "o",
                "--output-names",
                "s.png",
                "s.png",
            ],
        ),
        (
            {"inputs": ["a"], "output_dir": "o", "output_names": ["sub/x.png"]},
            ["--inputs", "a", "--output-dir", "o", "--output-names", "sub/x.png"],
        ),
    ]
    for kwargs, argv in shared:
        assert api_message(**kwargs) == cli_message(argv)

    # The documented exception: same rule, surface-appropriate wording.
    api_only = api_message(input="a.tif", output="b.png", output_names=["x.png"])
    cli_only = cli_message(
        ["--input", "a.tif", "--output", "b.png", "--output-names", "x.png"]
    )
    assert api_only != cli_only
    assert "inputs" in api_only and "--inputs" not in api_only
    assert "--inputs" in cli_only
