# SPDX-License-Identifier: Apache-2.0
"""Notebook bridge scaffolding.

This module will expose manifest-backed stage namespaces and a session/registry
for notebook-friendly execution. Current implementation is a placeholder to
anchor package structure for subsequent phases.
"""

from __future__ import annotations

from zyra.notebook.registry import Session, create_session

# Align with package version to avoid import errors in stubs/tests.
try:
    from zyra import __version__  # type: ignore
except Exception:  # pragma: no cover - defensive fallback
    __version__ = "0.0.0"

__all__ = ["__version__", "Session", "create_session"]
