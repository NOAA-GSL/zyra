# SPDX-License-Identifier: Apache-2.0
"""Decision/optimization stage CLI (skeleton).

Provides a minimal ``decide`` stage with an ``optimize`` command so that
workflows and API integration can be validated prior to full implementations.
"""

from __future__ import annotations

import argparse


def _cmd_optimize(ns: argparse.Namespace) -> int:
    """Placeholder decision/optimization command."""
    strategy = ns.strategy or "greedy"
    print(f"decide optimize: strategy={strategy} (skeleton)")
    return 0


def register_cli(subparsers: argparse._SubParsersAction) -> None:
    """Register decide-stage commands on a subparsers action."""
    p = subparsers.add_parser(
        "optimize", help="Run a placeholder optimization (skeleton)"
    )
    p.add_argument(
        "--strategy",
        choices=["greedy", "random", "grid"],
        help="Optimization strategy (placeholder)",
    )
    p.set_defaults(func=_cmd_optimize)
