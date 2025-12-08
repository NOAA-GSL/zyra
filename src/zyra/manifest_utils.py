# SPDX-License-Identifier: Apache-2.0
"""Shared helpers for loading manifests with optional overlays/plugins."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from zyra.wizard.manifest import build_manifest


def _read_overlay(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text) or {}
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError) as exc:
        logging.getLogger(__name__).debug("Failed to read overlay %s: %s", path, exc)
        return {}


def load_manifest_with_overlays(
    *, include_plugins: bool = True, overlay_path: Path | str | None = None
) -> dict[str, Any]:
    """Load packaged manifest and merge plugin + overlay entries.

    Args:
        include_plugins: If True, merge registered plugin commands from the in-memory registry.
        overlay_path: Optional path to a JSON overlay file. If not provided and
            the ``ZYRA_NOTEBOOK_OVERLAY`` environment variable is set, uses that
            path instead.

    Returns:
        Dictionary containing the merged manifest with all command metadata.

    Note:
        Overlay precedence: base manifest → plugins (if enabled) → overlay file (if present).
    """

    data = build_manifest()
    if include_plugins:
        try:
            from zyra import plugins as _plugins

            data.update(_plugins.manifest_overlay())
        except Exception as exc:
            logging.getLogger(__name__).debug("Skipping plugin overlay: %s", exc)

    overlay: Path | None = None
    if overlay_path:
        overlay = Path(overlay_path)
    else:
        env_overlay = os.environ.get("ZYRA_NOTEBOOK_OVERLAY")
        if env_overlay:
            overlay = Path(env_overlay)
    if overlay and overlay.exists():
        data.update(_read_overlay(overlay))
    return data


__all__ = ["load_manifest_with_overlays"]
