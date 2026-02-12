# SPDX-License-Identifier: Apache-2.0
"""Verification/evaluation stage CLI (skeleton).

Adds a minimal ``verify`` stage with placeholder metrics to enable end-to-end
testing of the stage map and API before richer evaluators are implemented.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _cmd_evaluate(ns: argparse.Namespace) -> int:
    """Evaluate simple verification metrics."""
    metric = (ns.metric or "accuracy").lower()
    if metric == "completeness" and ns.input:
        return _evaluate_completeness(ns.input)
    print(f"verify evaluate: metric={metric} (no-op)")
    return 0


def register_cli(subparsers: argparse._SubParsersAction) -> None:
    """Register verify-stage commands on a subparsers action."""
    p = subparsers.add_parser(
        "evaluate",
        help="Compute basic verification metrics (e.g., completeness)",
    )
    p.add_argument("--metric", help="Metric name", default="completeness")
    p.add_argument(
        "--input",
        help="Path to metadata JSON (e.g., transform scan-frames output)",
    )
    p.set_defaults(func=_cmd_evaluate)


def _evaluate_completeness(meta_path: str) -> int:
    try:
        data = json.loads(Path(meta_path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"verify evaluate: completeness FAILED - metadata not found: {meta_path}")
        return 2
    except json.JSONDecodeError:
        print("verify evaluate: completeness FAILED - metadata file is not valid JSON")
        return 2

    missing = data.get("missing_count")
    missing_list = _string_list(data.get("missing_timestamps"))
    if missing is None and missing_list:
        missing = len(missing_list)
    analysis = data.get("analysis") or {}
    duplicates = _string_list(analysis.get("duplicate_timestamps"))

    issues: list[str] = []
    if missing:
        msg = f"{missing} missing frame(s)"
        if missing_list:
            msg += f" (examples: {', '.join(missing_list[:3])})"
        issues.append(msg)
    if duplicates:
        msg = f"{len(duplicates)} duplicate timestamp(s)"
        msg += f" (examples: {', '.join(duplicates[:3])})"
        issues.append(msg)

    if issues:
        print("verify evaluate: completeness FAILED - " + "; ".join(issues))
        return 1

    print("verify evaluate: completeness PASSED - all frames present")
    return 0


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str)]
