# SPDX-License-Identifier: Apache-2.0
"""Shared helpers for loading manifests with optional overlays/plugins."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from zyra.plugins import manifest_overlay
from zyra.wizard.manifest import build_manifest


def _read_overlay(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def load_manifest_with_overlays(
    *, include_plugins: bool = True, overlay_path: Path | str | None = None
) -> dict[str, Any]:
    """Load packaged manifest and merge plugin + overlay entries."""

    data = build_manifest()
    if include_plugins:
        data.update(manifest_overlay())

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
