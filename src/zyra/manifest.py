# SPDX-License-Identifier: Apache-2.0
"""Programmatic access to Zyra capabilities manifests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from zyra.manifest_utils import load_manifest_with_overlays
from zyra.stage_utils import normalize_stage_name


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
        """Load packaged manifest (optionally filtered by stage).

        Args:
            stage: Optional stage name to filter commands. Accepts stage aliases
                (e.g., ``processing`` → ``process``). If provided, only commands
                for the stage are included.
            include_plugins: If True (default), merge registered plugin commands
                from the in-memory registry.

        Returns:
            Manifest instance containing the loaded and filtered command metadata.

        Example:
            - All commands: ``manifest = Manifest.load()``
            - Only process commands: ``manifest = Manifest.load(stage="process")``
            - Without plugins: ``manifest = Manifest.load(include_plugins=False)``
        """

        data = load_manifest_with_overlays(include_plugins=include_plugins)
        if stage:
            stage_norm = normalize_stage_name(stage)
            filtered = {
                k: v
                for k, v in data.items()
                if isinstance(k, str) and k.startswith(f"{stage_norm} ")
            }
            data = filtered
        return cls(data)

    def describe(self, command: str | None = None) -> dict[str, Any]:
        """Describe manifest entries, optionally narrowing to a command.

        Returns:
            Dict with a single key ``commands`` containing a list of ``ManifestEntry``.
            When ``command`` is provided, the list is filtered to matching entries
            (empty when not found).
        """

        entries = self.describe_all()
        if command:
            target = command.strip().lower()
            entries = [e for e in entries if e.name.lower() == target]
        return {"commands": entries}

    def describe_all(self) -> list[ManifestEntry]:
        """Describe all manifest entries."""

        entries: list[ManifestEntry] = []
        for key, meta in self._data.items():
            if not isinstance(key, str):
                continue
            entries.append(ManifestEntry(name=key, meta=meta))
        return entries

    def describe_command(self, command: str) -> ManifestEntry | None:
        """Describe a specific command."""

        target = command.strip().lower()
        for key, meta in self._data.items():
            if not isinstance(key, str):
                continue
            if key.lower() == target:
                return ManifestEntry(name=key, meta=meta)
        return None

    def list_commands(self, stage: str | None = None) -> list[str]:
        """List commands optionally filtered by stage.

        Args:
            stage: Optional stage name to filter commands. Accepts stage aliases
                (e.g., ``processing`` → ``process``). If None, returns all commands.

        Returns:
            Sorted list of command names in ``stage command`` format (e.g., ``process convert-format``).

        Example:
            - All commands: ``commands = manifest.list_commands()``
            - Only process commands: ``commands = manifest.list_commands(stage="process")``
        """

        stage_norm = normalize_stage_name(stage) if stage else None
        commands: list[str] = []
        for key in self._data:
            if not isinstance(key, str):
                continue
            if stage_norm and not key.startswith(f"{stage_norm} "):
                continue
            commands.append(key)
        return sorted(commands)


__all__ = ["Manifest", "ManifestEntry"]
