# SPDX-License-Identifier: Apache-2.0
"""Lightweight plugin registry for programmatic and CLI discovery.

This module intentionally keeps registration in-process and in-memory. It is
primarily used by:
- Workflow/Manifest APIs for programmatic extension.
- CLI help/manifest overlays so plugin commands are discoverable.

Execution dispatch for plugins is not wired into the CLI yet; the registry is
for discovery, metadata, and notebook-style inline extensions.
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, overload

_REGISTRY: dict[str, dict[str, PluginSpec]] = {}
_LOCAL_LOADED = False


@dataclass
class PluginSpec:
    """Registered plugin metadata."""

    stage: str
    name: str
    handler: Callable[..., Any] | None = None
    description: str | None = None
    args: list[dict[str, Any]] = field(default_factory=list)
    returns: str | None = None
    extras: list[str] | None = None
    origin: str | None = None


def _normalize_stage(stage: str) -> str:
    norm = stage.strip().lower().replace("-", " ")
    # Collapse repeated whitespace to a single space for consistent keys
    return " ".join(norm.split())


def _load_local_extensions() -> None:
    """Best-effort import of .zyra/extensions/plugins.py for local hooks."""

    global _LOCAL_LOADED
    if _LOCAL_LOADED:
        return
    _LOCAL_LOADED = True
    try:
        extensions_path = Path(".zyra") / "extensions" / "plugins.py"
        if not extensions_path.exists():
            return
        spec = importlib.util.spec_from_file_location(
            "zyra_local_plugins", extensions_path
        )
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            sys.modules["zyra_local_plugins"] = mod
            spec.loader.exec_module(mod)
    except Exception:
        # Non-fatal: ignore local extensions errors to avoid breaking CLI.
        return


def register_command(
    stage: str,
    name: str,
    handler: Callable[..., Any] | None = None,
    *,
    description: str | None = None,
    args: list[dict[str, Any]] | None = None,
    returns: str | None = None,
    extras: list[str] | None = None,
    origin: str | None = None,
) -> Callable[..., Any] | Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Register a plugin command.

    Can be used as a decorator or a direct call. Returns the handler for
    decorator-style usage.
    """

    stage_norm = _normalize_stage(stage)
    cmd_name = name.strip()
    spec = PluginSpec(
        stage=stage_norm,
        name=cmd_name,
        handler=handler,
        description=description,
        args=args or [],
        returns=returns,
        extras=extras,
        origin=origin or "plugin_registry",
    )
    _REGISTRY.setdefault(stage_norm, {})[cmd_name] = spec

    def _decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        spec.handler = func
        _REGISTRY[stage_norm][cmd_name] = spec
        return func

    if handler is not None:
        return handler
    return _decorator


@overload
def list_registered(stage: str) -> list[str]: ...


@overload
def list_registered(stage: None = None) -> dict[str, list[str]]: ...


def list_registered(stage: str | None = None) -> dict[str, list[str]] | list[str]:
    """List registered plugin commands."""

    _load_local_extensions()
    if stage:
        stage_norm = _normalize_stage(stage)
        return sorted(_REGISTRY.get(stage_norm, {}).keys())
    return {stage: sorted(cmds.keys()) for stage, cmds in _REGISTRY.items()}


def manifest_overlay() -> dict[str, dict[str, Any]]:
    """Return a manifest-like overlay for all registered plugins."""

    _load_local_extensions()
    overlay: dict[str, dict[str, Any]] = {}
    for stage, cmds in _REGISTRY.items():
        for name, spec in cmds.items():
            key = f"{stage} {name}"
            overlay[key] = {
                "description": spec.description or "Plugin command",
                "returns": spec.returns,
                "extras": spec.extras,
                "origin": spec.origin or "plugin_registry",
                "impl": None,  # Not wired to CLI dispatch yet
                "args_template": spec.args or [],
            }
    return overlay


def help_epilog() -> str | None:
    """Generate a help epilog snippet listing plugin commands."""

    _load_local_extensions()
    if not _REGISTRY:
        return None
    parts: list[str] = ["Plugin commands:"]
    for stage, cmds in sorted(_REGISTRY.items()):
        names = ", ".join(sorted(cmds.keys()))
        parts.append(f"  {stage}: {names}")
    return "\n".join(parts)


__all__ = ["register_command", "list_registered", "manifest_overlay", "help_epilog"]
