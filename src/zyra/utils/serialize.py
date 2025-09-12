# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Iterable

"""Lightweight serializers and text helpers used across Zyra.

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
    except (TypeError, ValueError):
        pass
    d = getattr(x, "__dict__", None)
    if isinstance(d, dict):
        return d
    return x


def to_list(items: Iterable[Any]) -> list[Any]:
    """Convert an iterable of values via to_obj, returning a list."""
    return [to_obj(i) for i in items]


def truncate_text(text: str, max_len: int = 240) -> str:
    """Return ``text`` truncated to ``max_len`` characters with an ellipsis.

    Uses the single-character Unicode ellipsis when truncating. If ``text``
    is shorter than or equal to ``max_len``, it is returned unchanged.
    """
    try:
        s = str(text)
    except (TypeError, ValueError):
        s = ""
    if max_len is None or max_len <= 0:
        return s
    if len(s) > max_len:
        # Reserve 1 character for the ellipsis
        return s[: max(0, max_len - 1)] + "…"
    return s


def compact_dataset(x: Any, max_desc_len: int = 240) -> dict[str, Any]:
    """Return a compact mapping for a dataset-like object.

    Extracts the common fields (id, name, description, source, format, uri)
    from either a dataclass/object via attribute access or a mapping via
    ``get``. The description is truncated to ``max_desc_len`` using
    :func:`truncate_text`.
    """
    if isinstance(x, dict):
        get = x.get  # type: ignore[assignment]
    else:

        def _get(k: str, default: Any | None = None) -> Any:
            return getattr(x, k, default)

        get = _get

    desc_raw = get("description") or ""
    desc = truncate_text(str(desc_raw), max_desc_len)
    return {
        "id": get("id"),
        "name": get("name"),
        "description": desc,
        "source": get("source"),
        "format": get("format"),
        "uri": get("uri"),
    }
