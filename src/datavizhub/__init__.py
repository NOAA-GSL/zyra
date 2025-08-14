"""DataVizHub package root.

This module avoids eager-importing optional subpackages (acquisition,
processing, visualization, etc.) to ensure stage-specific installs work
with minimal dependencies. Subpackages can be imported directly, e.g.::

    import datavizhub.visualization

Lazy attribute access below provides a convenience to access
``datavizhub.<submodule>`` as attributes without importing them at
package import time.
"""

from __future__ import annotations

from importlib import import_module
from importlib.metadata import PackageNotFoundError, version
from typing import Any

try:  # best-effort version resolution
    __version__ = version("datavizhub")
except PackageNotFoundError:  # during editable installs without metadata
    __version__ = "0.0.0"

__all__ = [
    "__version__",
]


def __getattr__(name: str) -> Any:
    """Lazily expose top-level subpackages on attribute access.

    This preserves ``datavizhub.visualization``-style access without importing
    optional subpackages unless actually used.
    """
    if name in {"acquisition", "assets", "processing", "utils", "visualization"}:
        return import_module(f"datavizhub.{name}")
    raise AttributeError(name)
