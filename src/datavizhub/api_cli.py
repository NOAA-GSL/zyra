# SPDX-License-Identifier: Apache-2.0
"""Compatibility wrapper for API CLI module execution.

Allows `python -m datavizhub.api_cli ...` after the rename to `zyra`.
"""

from __future__ import annotations

from zyra.api_cli import main as main  # re-export

if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
