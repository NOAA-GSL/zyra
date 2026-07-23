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

EXTENT_COMMANDS = ["heatmap", "contour", "vector", "animate", "interactive"]


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


def test_resolve_extent_defaults_and_validates():
    assert resolve_extent(SimpleNamespace(extent=None)) == list(DEFAULT_EXTENT)
    assert resolve_extent(SimpleNamespace()) == list(DEFAULT_EXTENT)
    assert resolve_extent(SimpleNamespace(extent=[1, 2, 3, 4])) == [1.0, 2.0, 3.0, 4.0]
    with pytest.raises(SystemExit, match="exactly 4 values"):
        resolve_extent(SimpleNamespace(extent=[1.0, 2.0, 3.0]))


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
