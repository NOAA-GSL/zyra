# SPDX-License-Identifier: Apache-2.0
"""Tests for --extent flag parsing across visualization commands.

The Domain API's argv builder expands list args as repeated flags
(``--extent w --extent e ...``), which the previous ``nargs=4``
declarations could not parse — extent-cropped renders via the API
never worked. The flags now use ``action="extend"`` so both spellings
accumulate, with length validation in ``resolve_extent``.
"""

import argparse
from types import SimpleNamespace

import pytest

from zyra.visualization.cli_register import register_cli
from zyra.visualization.cli_utils import DEFAULT_EXTENT, resolve_extent

EXTENT_COMMANDS = ["heatmap", "contour", "vector", "animate", "interactive", "sos"]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="visualize")
    register_cli(parser.add_subparsers(dest="cmd"))
    return parser


def _required_stub(cmd: str) -> list[str]:
    # Minimal required args per command so parse_args succeeds.
    stubs = {
        "heatmap": ["--input", "x.nc"],
        "contour": ["--input", "x.nc", "--output", "o.png"],
        "vector": ["--input", "x.nc"],
        "animate": [],
        "interactive": ["--input", "x.nc", "--output", "o.html"],
        "sos": ["--input", "x.nc", "--output", "o.png"],
    }
    return stubs[cmd]


@pytest.mark.parametrize("cmd", EXTENT_COMMANDS)
def test_single_flag_spelling_parses(cmd):
    ns = _parser().parse_args(
        [cmd, *_required_stub(cmd), "--extent", "-120", "-60", "20", "55"]
    )
    assert ns.extent == [-120.0, -60.0, 20.0, 55.0]


@pytest.mark.parametrize("cmd", EXTENT_COMMANDS)
def test_repeated_flag_spelling_accumulates(cmd):
    # The Domain API expansion: one flag occurrence per value.
    argv = [cmd, *_required_stub(cmd)]
    for v in ("-120", "-60", "20", "55"):
        argv += ["--extent", v]
    ns = _parser().parse_args(argv)
    assert ns.extent == [-120.0, -60.0, 20.0, 55.0]


@pytest.mark.parametrize("cmd", EXTENT_COMMANDS)
def test_default_is_none_not_mutated(cmd):
    # extend appends to list defaults; default must therefore be None
    # (resolve_extent supplies the full globe).
    ns = _parser().parse_args([cmd, *_required_stub(cmd)])
    assert ns.extent is None


def test_resolve_extent_defaults_and_validates(caplog):
    assert resolve_extent(SimpleNamespace(extent=None)) == list(DEFAULT_EXTENT)
    assert resolve_extent(SimpleNamespace()) == list(DEFAULT_EXTENT)
    assert resolve_extent(SimpleNamespace(extent=[1, 2, 3, 4])) == [1.0, 2.0, 3.0, 4.0]
    # The exit code must be numeric so the failure stays a clean exit-status
    # signal rather than a message string routed through the executor.
    with caplog.at_level("ERROR"), pytest.raises(SystemExit) as excinfo:
        resolve_extent(SimpleNamespace(extent=[1.0, 2.0, 3.0]))
    assert excinfo.value.code == 2
    assert "exactly 4 values" in caplog.text


def test_api_argv_round_trips_extent():
    # End-to-end for the API path: args dict -> executor argv -> parser.
    from zyra.api.workers.executor import _args_dict_to_argv

    argv = _args_dict_to_argv(
        "visualize",
        "heatmap",
        {"input": "x.nc", "output": "o.png", "extent": [-120, -60, 20, 55]},
    )
    assert argv[:2] == ["visualize", "heatmap"]
    ns = _parser().parse_args(argv[1:])
    assert ns.extent == [-120.0, -60.0, 20.0, 55.0]


class TestExtentValueValidation:
    """`--extent` value checks (#287).

    `--extent` is [west, east, south, north]; `process reproject
    --dst-bounds` is [west, south, east, north]. A regional pipeline
    writes both, adjacent, and passing one in the other's order renders
    a valid picture of the wrong part of the world with no error.

    The swap is not detectable in general — both orderings can describe
    a well-formed box — so these check the part that is: the two values
    in the latitude slots have to be latitudes.
    """

    @pytest.mark.parametrize(
        ("extent", "why"),
        [
            ([-135.0, -60.0, 21.0, 53.0], "a regional box"),
            ([-180.0, 180.0, -90.0, 90.0], "the global default"),
            # west > east is how a dateline-crossing extent is written,
            # so longitudes are deliberately not order-checked.
            ([170.0, -170.0, -10.0, 10.0], "crossing the dateline"),
        ],
    )
    def test_valid_extents_are_accepted(self, extent, why):
        assert resolve_extent(SimpleNamespace(extent=list(extent))) == list(extent), why

    @pytest.mark.parametrize(
        ("extent", "why"),
        [
            ([-135.0, 21.0, -160.0, 53.0], "a longitude in the south slot"),
            ([0.0, 10.0, -95.0, 95.0], "latitudes beyond the poles"),
            ([-135.0, -60.0, 53.0, 21.0], "south above north — an empty box"),
        ],
    )
    def test_invalid_extents_exit_2(self, extent, why):
        with pytest.raises(SystemExit) as exc:
            resolve_extent(SimpleNamespace(extent=list(extent)))
        assert exc.value.code == 2, why

    def test_latitude_error_names_the_other_flag_s_ordering(self, caplog):
        with caplog.at_level("ERROR"), pytest.raises(SystemExit):
            resolve_extent(SimpleNamespace(extent=[-135.0, 21.0, -160.0, 53.0]))
        assert "--dst-bounds" in caplog.text
        assert "west south east north" in caplog.text

    def test_the_undetectable_swap_is_documented_as_accepted(self):
        """The case that actually bit: both readings are valid boxes.

        `-135 21 -60 53` is a well-formed extent whichever convention
        you read it in, so no validation can reject it. Pinned so the
        limitation is explicit rather than an assumed-covered gap — the
        mitigation for this one is the help text, not a check.
        """
        assert resolve_extent(SimpleNamespace(extent=[-135.0, 21.0, -60.0, 53.0])) == [
            -135.0,
            21.0,
            -60.0,
            53.0,
        ]
