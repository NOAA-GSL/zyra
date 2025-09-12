# SPDX-License-Identifier: Apache-2.0
"""Simulation stage CLI (skeleton).

Exposes lightweight placeholder commands under the ``simulate`` stage so that
the stage hierarchy and API surface can be validated before full features land.

Commands
- ``simulate sample``: emit a simple message; accepts optional ``--seed`` and
  ``--trials`` arguments for future compatibility.
"""

from __future__ import annotations

import argparse


def _cmd_sample(ns: argparse.Namespace) -> int:
    """Placeholder simulate command.

    Emits a simple message and exits with code 0 so pipelines can integrate
    before full functionality is implemented.
    """
    msg = "simulate sample: skeleton in place. Provide --seed and --trials as needed."
    print(msg)
    return 0


def register_cli(subparsers: argparse._SubParsersAction) -> None:
    """Register simulate-stage commands on a subparsers action.

    Parameters
    - subparsers: the result of ``parser.add_subparsers(...)`` to attach
      the ``sample`` command.
    """
    p = subparsers.add_parser("sample", help="Run a placeholder simulation (skeleton)")
    p.add_argument("--seed", type=int, help="Random seed")
    p.add_argument("--trials", type=int, default=1, help="Number of trials")
    p.set_defaults(func=_cmd_sample)
