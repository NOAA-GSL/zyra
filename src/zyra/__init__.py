"""Zyra package root.

This is the primary package namespace moving forward.
"""
from __future__ import annotations

from importlib import import_module
from importlib.metadata import PackageNotFoundError, version
from typing import Any

# Expose package version under the new name when available.
try:
    __version__ = version("zyra")
except PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = ["__version__"]


def __getattr__(name: str) -> Any:
    """Lazily expose top-level subpackages on attribute access."""
    if name in {
        "assets",
        "processing",
        "utils",
        "visualization",
        "api",
        "connectors",
        "wizard",
        "transform",
    }:
        return import_module(f"zyra.{name}")
    raise AttributeError(name)
