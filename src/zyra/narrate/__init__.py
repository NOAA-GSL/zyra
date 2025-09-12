# SPDX-License-Identifier: Apache-2.0
"""Narration/reporting stage CLI (skeleton).

Adds a minimal ``narrate`` stage for AI-driven summaries/captions so that
the overall CLI/API surface is stable before detailed features land.
"""

from __future__ import annotations

import argparse


def _cmd_describe(ns: argparse.Namespace) -> int:
    """Placeholder narrate/report command."""
    topic = ns.topic or "run"
    print(f"narrate describe: topic={topic} (skeleton)")
    return 0


def register_cli(subparsers: argparse._SubParsersAction) -> None:
    """Register narrate-stage commands on a subparsers action."""
    p = subparsers.add_parser(
        "describe", help="Produce a placeholder narrative/report (skeleton)"
    )
    p.add_argument("--topic", help="Topic to narrate (placeholder)")
    p.set_defaults(func=_cmd_describe)
