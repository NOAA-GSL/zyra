"""Compatibility shim for the former ``datavizhub`` package.

This package has been renamed to ``zyra``. The shim maps imports from
``datavizhub.*`` to ``zyra.*`` and emits a deprecation warning to aid
migration.
"""

from __future__ import annotations

import sys
from importlib import import_module
from importlib.abc import Loader, MetaPathFinder
from importlib.machinery import ModuleSpec, PathFinder
from importlib.metadata import PackageNotFoundError, version
from importlib.util import find_spec
from types import ModuleType
from typing import Any

try:
    __version__ = version("zyra")
except PackageNotFoundError:  # during editable installs without metadata
    __version__ = "0.0.0"

__all__ = ["__version__"]


class _AliasFinder(MetaPathFinder, Loader):
    """Alias ``datavizhub.*`` modules to ``zyra.*`` for deep imports."""

    _FROM_PREFIX = "datavizhub"
    _TO_PREFIX = "zyra"

    def find_spec(self, fullname: str, path, target=None) -> ModuleSpec | None:  # type: ignore[override]
        if fullname == self._FROM_PREFIX or fullname.startswith(
            self._FROM_PREFIX + "."
        ):
            # If a real module exists under datavizhub (e.g., small wrappers), do not alias
            real_existing = PathFinder.find_spec(fullname, path)
            if real_existing is not None:
                return None
            # Otherwise alias to zyra.*
            realname = self._TO_PREFIX + fullname[len(self._FROM_PREFIX) :]
            real_spec = find_spec(realname)
            if real_spec is None:
                return None
            spec = ModuleSpec(fullname, self, origin=f"alias:{realname}")
            spec.submodule_search_locations = real_spec.submodule_search_locations
            return spec
        return None

    # Ensure compatibility with runpy (-m) by delegating code retrieval
    def get_code(self, fullname: str):  # type: ignore[override]
        realname = self._TO_PREFIX + fullname[len(self._FROM_PREFIX) :]
        rspec = find_spec(realname)
        if rspec and rspec.loader and hasattr(rspec.loader, "get_code"):
            return rspec.loader.get_code(realname)  # type: ignore[attr-defined]
        return None

    def create_module(self, spec: ModuleSpec) -> ModuleType | None:  # type: ignore[override]
        return None

    def exec_module(self, module: ModuleType) -> None:  # type: ignore[override]
        realname = self._TO_PREFIX + module.__name__[len(self._FROM_PREFIX) :]
        rspec = find_spec(realname)
        if rspec and rspec.loader and hasattr(rspec.loader, "get_code"):
            code = rspec.loader.get_code(realname)  # type: ignore[attr-defined]
            # Execute the real module's code in the alias module's dict so they share objects
            exec(code, module.__dict__)
            # Ensure both names point to the same module object
            sys.modules[realname] = module
        else:  # Fallback: import and rebind
            real = import_module(realname)
            sys.modules[module.__name__] = real
            if hasattr(real, "__path__"):
                module.__path__ = real.__path__  # type: ignore[attr-defined]


def _install_alias_importer() -> None:
    for finder in sys.meta_path:
        if isinstance(finder, _AliasFinder):
            return
    sys.meta_path.insert(0, _AliasFinder())


_install_alias_importer()


def __getattr__(name: str) -> Any:
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


# Deprecation note intentionally not emitted at import time to avoid noisy stderr
# in subprocess CLI flows and tests. Migration guidance is provided in docs.


def _unify_known_modules() -> None:
    """Ensure some critical modules share identity across both namespaces.

    This avoids isinstance mismatches in tests that compare classes imported
    from ``datavizhub.*`` against instances created via ``zyra.*``.
    """
    try:
        import datavizhub.wizard.llm_client as dllm  # type: ignore

        # Point both names to the same module object
        sys.modules["zyra.wizard.llm_client"] = dllm
        # Also ensure the package object references the same submodule
        import zyra.wizard as zw  # type: ignore

        zw.llm_client = dllm  # type: ignore[attr-defined]
    except Exception:
        # Best effort; safe to ignore in environments that don't touch wizard
        pass


_unify_known_modules()
