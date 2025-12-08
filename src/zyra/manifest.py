# SPDX-License-Identifier: Apache-2.0
"""Programmatic access to Zyra capabilities manifests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from zyra.manifest_utils import load_manifest_with_overlays
from zyra.wizard.manifest import DOMAIN_ALIAS_MAP


def _normalize_stage(stage: str) -> str:
    stage_norm = stage.strip().lower()
    try:
        from zyra.pipeline_runner import _stage_group_alias

        return _stage_group_alias(stage_norm)
    except (ImportError, AttributeError):
        return DOMAIN_ALIAS_MAP.get(stage_norm, stage_norm)
    except Exception as exc:  # pragma: no cover - defensive
        try:
            import logging as _log

            _log.getLogger(__name__).debug(
                "manifest stage normalization fallback: %s", exc
            )
        except Exception:
            # Avoid raising during manifest load path
            pass
        return DOMAIN_ALIAS_MAP.get(stage_norm, stage_norm)


@dataclass
class ManifestEntry:
    """Single manifest entry."""

    name: str
    meta: dict[str, Any]


class Manifest:
    """Load and inspect Zyra CLI capabilities."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    @classmethod
    def load(
        cls, stage: str | None = None, *, include_plugins: bool = True
    ) -> Manifest:
        """Load packaged manifest (optionally filtered by stage)."""

        data = load_manifest_with_overlays(include_plugins=include_plugins)
        if stage:
            stage_norm = _normalize_stage(stage)
            filtered = {
                k: v
                for k, v in data.items()
                if isinstance(k, str) and k.startswith(f"{stage_norm} ")
            }
            data = filtered
        return cls(data)

    def describe(self, command: str | None = None) -> dict[str, Any]:
        """Describe manifest entries, optionally narrowing to a command."""

        if command:
            target = command.strip().lower()
            for key, meta in self._data.items():
                if not isinstance(key, str):
                    continue
                if key.lower() == target:
                    return {"name": key, "meta": meta}
            return {}
        entries: list[ManifestEntry] = []
        for key, meta in self._data.items():
            if not isinstance(key, str):
                continue
            entries.append(ManifestEntry(name=key, meta=meta))
        return {"commands": entries}

    def list_commands(self, stage: str | None = None) -> list[str]:
        """List commands optionally filtered by stage."""

        stage_norm = _normalize_stage(stage) if stage else None
        commands: list[str] = []
        for key in self._data:
            if not isinstance(key, str):
                continue
            if stage_norm and not key.startswith(f"{stage_norm} "):
                continue
            commands.append(key)
        return sorted(commands)


__all__ = ["Manifest", "ManifestEntry"]
