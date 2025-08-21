"""Compatibility wrapper for module execution.

Allows `python -m datavizhub.cli ...` to resolve after the rename to `zyra`.
"""
from __future__ import annotations

from zyra.cli import main as main  # re-export

if __name__ == "__main__":  # pragma: no cover - exercised in CLI tests
    raise SystemExit(main())
