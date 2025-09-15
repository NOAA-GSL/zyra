# SPDX-License-Identifier: Apache-2.0
"""Lightweight JSON/dict helpers used across modules.

Currently provides a minimal dotted-path accessor that avoids pulling in
heavier JSONPath dependencies.
"""

from __future__ import annotations

from typing import Any


def get_by_path(obj: Any, path: str) -> Any:
    """Return the value at a dotted path within a dict-like object.

    - Supports simple ``a.b.c`` navigation through nested dicts.
    - Returns ``None`` if any segment is missing or the current value is not a
      dict at a required step.
    """
    cur: Any = obj
    for part in (path or "").split(".") if path else []:
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur
