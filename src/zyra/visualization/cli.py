"""Compatibility wrapper delegating to the root CLI.

This module remains importable for now to avoid breaking existing docs/tests.
It forwards all arguments to ``zyra.cli``.
"""

from __future__ import annotations

import sys

from zyra.cli import main as root_main


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - thin wrapper
    return root_main(argv or sys.argv[1:])


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
