# SPDX-License-Identifier: Apache-2.0
"""Verification/evaluation stage CLI (skeleton).

Adds a minimal ``verify`` stage with placeholder metrics to enable end-to-end
testing of the stage map and API before richer evaluators are implemented.
"""

from __future__ import annotations

import argparse


def _cmd_evaluate(ns: argparse.Namespace) -> int:
    """Placeholder verify/evaluation command."""
    metric = ns.metric or "accuracy"
    print(f"verify evaluate: metric={metric} (skeleton)")
    return 0


def register_cli(subparsers: argparse._SubParsersAction) -> None:
    """Register verify-stage commands on a subparsers action."""
    p = subparsers.add_parser(
        "evaluate", help="Compute placeholder evaluation metrics (skeleton)"
    )
    p.add_argument("--metric", help="Metric name (placeholder)")
    p.set_defaults(func=_cmd_evaluate)
