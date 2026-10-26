#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Regenerate the packaged ``zyra run`` JSON Schema.

Writes ``src/zyra/assets/schemas/zyra-pipeline.schema.json`` from the committed
capabilities manifest. Run with ``--check`` in CI to fail when the artifact is
stale.

Usage::

    poetry run python scripts/generate_pipeline_schema.py
    poetry run python scripts/generate_pipeline_schema.py --check
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = REPO_ROOT / "src" / "zyra" / "assets" / "schemas"

# Prefer the working tree over any installed copy of Zyra.
sys.path.insert(0, str(REPO_ROOT / "src"))

from zyra.pipeline_schema import SCHEMA_FILENAME, render_schema  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT,
        help=f"Destination directory (default: {DEFAULT_OUT})",
    )
    ap.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if the artifact on disk is out of date; write nothing.",
    )
    ns = ap.parse_args(argv)

    target = ns.out_dir / SCHEMA_FILENAME
    rendered = render_schema()

    if ns.check:
        if not target.exists():
            print(f"Missing schema artifact: {target}", file=sys.stderr)
            return 1
        if target.read_text(encoding="utf-8") != rendered:
            print(
                f"{target} is out of date.\n"
                "Run: poetry run python scripts/generate_pipeline_schema.py",
                file=sys.stderr,
            )
            return 1
        print(f"{target} is up to date.")
        return 0

    ns.out_dir.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.read_text(encoding="utf-8") == rendered:
        print(f"{target} unchanged.")
        return 0
    target.write_text(rendered, encoding="utf-8")
    print(f"Wrote {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
