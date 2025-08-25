from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Iterable

"""Lightweight serializers for Zyra objects (dataclasses and simple containers).

Avoids subtle pitfalls with getattr default evaluation and handles dataclasses
gracefully without requiring consumers to import `dataclasses` everywhere.
"""


def to_obj(x: Any) -> Any:
    """Convert a value to a JSON-serializable object when possible.

    - Dataclasses → asdict
    - Objects with __dict__ → that dict
    - Mappings are returned as-is
    - Primitives are returned as-is
    """
    try:
        if is_dataclass(x):
            return asdict(x)
    except Exception:
        pass
    d = getattr(x, "__dict__", None)
    if isinstance(d, dict):
        return d
    return x


def to_list(items: Iterable[Any]) -> list[Any]:
    """Convert an iterable of values via to_obj, returning a list."""
    return [to_obj(i) for i in items]
