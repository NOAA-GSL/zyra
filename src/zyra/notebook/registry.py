# SPDX-License-Identifier: Apache-2.0
"""Notebook runtime scaffolding for manifest-backed stage functions.

This module provides:
- A Session that loads the capabilities manifest and exposes stage namespaces.
- Lightweight wrapper generation using manifest hints (impl/returns/output_arg/stdin_arg).
- Registry support for inline tool registration (to be implemented in subsequent phases).

Phase 3 scope: define the interfaces and basic manifest loading.
"""

from __future__ import annotations

import contextlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from zyra.swarm import open_provenance_store
from zyra.wizard.manifest import build_manifest

DEFAULT_WORKDIR_ENV = "ZYRA_NOTEBOOK_DIR"
DEFAULT_WORKDIR_FALLBACKS = [
    Path("/kaggle/working"),
    Path.cwd(),
]
DEFAULT_PROVENANCE_ENV = "ZYRA_NOTEBOOK_PROVENANCE"
DEFAULT_PROVENANCE_ENV = "ZYRA_NOTEBOOK_PROVENANCE"


def _noop_tool(ns: Any) -> dict[str, Any]:
    """Test helper: echo namespace as dict."""

    try:
        return vars(ns)
    except Exception:
        return {}


def _safe_repr(obj: Any) -> Any:
    """Best-effort to convert an object to a JSON-safe representation."""

    try:
        if isinstance(obj, dict):
            return {k: _safe_repr(v) for k, v in obj.items()}
        if hasattr(obj, "__dict__"):
            return {k: _safe_repr(v) for k, v in obj.__dict__.items()}
        if isinstance(obj, (list, tuple)):
            return [_safe_repr(v) for v in obj]
        return obj
    except Exception:
        try:
            return repr(obj)
        except Exception:
            return "<unserializable>"


@dataclass
class ToolMetadata:
    """Metadata describing a tool callable."""

    name: str
    impl: dict[str, str] | None
    callable_obj: Any | None
    returns: str | None
    output_arg: str | None
    stdin_arg: str | None
    extras: list[str] | None
    side_effects: list[str] | None


class ToolWrapper:
    """Callable wrapper exposing manifest metadata and logging provenance."""

    def __init__(self, meta: ToolMetadata, workdir: Path, session: Session) -> None:
        self.meta = meta
        self.workdir = workdir
        self._session = session

    def __call__(
        self, *args: Any, **kwargs: Any
    ) -> Any:  # pragma: no cover - thin wrapper until full execution wiring
        func = self._resolve_callable()
        ns, capture_path = self._build_namespace(kwargs)
        # Track last namespace for result post-processing (e.g., output paths).
        with contextlib.suppress(Exception):
            self._session._last_ns = ns  # noqa: SLF001
        result = func(ns)
        final = self._finalize_result(result, capture_path)
        self._log_provenance(ns, final)
        return final

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"<ToolWrapper {self.meta.name} returns={self.meta.returns or 'object'}>"

    def _resolve_callable(self) -> Any:
        if self.meta.callable_obj is not None:
            return self.meta.callable_obj
        if not self.meta.impl:
            raise NotImplementedError(
                f"No implementation metadata for tool '{self.meta.name}'"
            )
        module_name = self.meta.impl.get("module")
        func_name = self.meta.impl.get("callable")
        if not module_name or not func_name:
            raise NotImplementedError(
                f"Incomplete implementation metadata for tool '{self.meta.name}'"
            )
        try:
            import importlib

            mod = importlib.import_module(module_name)
            func = getattr(mod, func_name)
            return func
        except Exception as exc:  # pragma: no cover - defensive
            raise RuntimeError(
                f"Failed to import callable for tool '{self.meta.name}': {exc}"
            ) from exc

    def _build_namespace(self, user_kwargs: dict[str, Any]) -> tuple[Any, Path | None]:
        norm = {k.replace("-", "_"): v for k, v in user_kwargs.items()}
        norm.setdefault("workdir", str(self.workdir))
        capture: Path | None = None
        out_flag = self.meta.output_arg or ""
        if out_flag.startswith("--") and self.meta.returns == "bytes":
            key = out_flag.lstrip("-").replace("-", "_")
            desired = norm.get(key)
            if not desired or desired == "-":
                capture = (
                    self._session.workspace()
                    / f"{self.meta.name.replace(' ', '_')}.tmp"
                )
                norm[key] = str(capture)
        # Command-specific defaults
        if self.meta.name.startswith("narrate swarm"):
            norm.setdefault("list_presets", False)
            norm.setdefault("preset", None)
            norm.setdefault("swarm_config", None)
            norm.setdefault("agents", None)
            norm.setdefault("audiences", None)
            norm.setdefault("style", None)
            norm.setdefault("provider", None)
            norm.setdefault("model", None)
            norm.setdefault("base_url", None)
            norm.setdefault("pack", None)
            norm.setdefault("rubric", None)
            norm.setdefault("input", None)
            norm.setdefault("max_workers", None)
            norm.setdefault("max_rounds", None)
            norm.setdefault("memory", None)
            norm.setdefault("critic_structured", False)
            norm.setdefault("attach_images", False)
            norm.setdefault("strict_grounding", False)
            norm.setdefault("guardrails", None)
            norm.setdefault("strict_guardrails", False)
        try:
            import argparse

            return argparse.Namespace(**norm), capture
        except Exception:  # pragma: no cover - fall back

            class _NS:  # pragma: no cover - safety fallback
                def __init__(self, data: dict[str, Any]) -> None:
                    self.__dict__.update(data)

            return _NS(norm), capture

    def _finalize_result(self, result: Any, capture_path: Path | None) -> Any:
        # If the tool writes to a known output flag, surface that path even when the callable returns an exit code.
        if (
            self.meta.returns == "path"
            and self.meta.output_arg
            and self.meta.output_arg.startswith("--")
        ):
            arg_name = self.meta.output_arg.lstrip("-").replace("-", "_")
            with contextlib.suppress(Exception):
                target = getattr(self._session._last_ns, arg_name)  # noqa: SLF001
                if target:
                    return str(target)
        if self.meta.returns == "bytes" and capture_path and capture_path.exists():
            try:
                data = capture_path.read_bytes()
                return data
            except Exception:
                return result
        if self.meta.returns == "path" and capture_path:
            return str(capture_path)
        return result

    def _log_provenance(self, ns: Any, result: Any) -> None:
        store = self._session.provenance_store()
        if not store or not hasattr(store, "handle_event"):
            return
        # Track invocation for export helpers even if store handling fails
        with contextlib.suppress(Exception):
            self._session._invocations.append(  # noqa: SLF001
                {
                    "tool": self.meta.name,
                    "kwargs": _safe_repr(ns),
                    "returns": self.meta.returns or "object",
                }
            )
        payload: dict[str, Any] = {
            "tool": self.meta.name,
            "returns": self.meta.returns or "object",
            "workdir": str(self.workdir),
        }
        try:
            payload["args"] = _safe_repr(ns)
        except Exception:
            payload["args"] = "<unavailable>"
        try:
            length = None
            if isinstance(result, (bytes, bytearray)):
                length = len(result)
            elif hasattr(result, "__len__"):
                length = len(result)  # type: ignore[arg-type]
            payload["result_meta"] = {"type": type(result).__name__, "len": length}
        except Exception:
            payload["result_meta"] = {"type": type(result).__name__}
        try:
            store.handle_event("notebook_tool_completed", payload)
        except Exception:
            return


class StageNamespace:
    """Container for stage-specific tools (e.g., acquire.http)."""

    def __init__(
        self,
        domain: str,
        tools: dict[str, ToolMetadata],
        workdir: Path,
        session: Session,
    ) -> None:
        self._domain = domain
        self._tools = tools
        self._workdir = workdir
        self._session = session

    def __dir__(self) -> list[str]:  # pragma: no cover - cosmetic
        return sorted(self._tools.keys())

    def __getattr__(self, item: str) -> Any:
        if item not in self._tools:
            raise AttributeError(item)
        return ToolWrapper(self._tools[item], self._workdir, self._session)

    def register(
        self,
        name: str,
        func: Any,
        *,
        returns: str | None = "object",
        extras: list[str] | None = None,
        side_effects: list[str] | None = None,
    ) -> None:
        """Register an inline tool callable for this stage."""

        safe_name = name.replace("-", "_")
        meta = ToolMetadata(
            name=f"{self._domain} {name}",
            impl={
                "module": getattr(func, "__module__", None) or "",
                "callable": getattr(func, "__name__", safe_name),
            },
            callable_obj=func,
            returns=returns,
            output_arg=None,
            stdin_arg=None,
            extras=extras,
            side_effects=side_effects,
        )
        self._tools[safe_name] = meta


class Session:
    """Notebook session: holds manifest and stage namespaces."""

    def __init__(
        self,
        manifest: dict[str, Any] | None = None,
        workdir: Path | None = None,
        provenance_path: Path | str | None = None,
    ) -> None:
        self._manifest = manifest or build_manifest()
        self._workdir = self._resolve_workdir(workdir)
        self._provenance_path = self._resolve_provenance_path(provenance_path)
        self._provenance_store = open_provenance_store(self._provenance_path)
        self.acquire = self._build_namespace("acquire")
        self.process = self._build_namespace("process")
        self.transform = self._build_namespace("transform")
        self.visualize = self._build_namespace("visualize")
        self.render = self._build_namespace("render")
        self.disseminate = self._build_namespace("disseminate")
        self.decimate = self._build_namespace("decimate")
        self.export = self._build_namespace("export")
        self.narrate = self._build_namespace("narrate")
        self.verify = self._build_namespace("verify")
        self.run = self._build_namespace("run")
        self.search = self._build_namespace("search")
        self.simulate = self._build_namespace("simulate")
        self.decide = self._build_namespace("decide")
        self.optimize = self._build_namespace("optimize")
        self._invocations: list[dict[str, Any]] = []

    def _resolve_workdir(self, override: Path | None) -> Path:
        if override:
            return Path(override).expanduser()
        env_path = Path(os.environ.get(DEFAULT_WORKDIR_ENV, "")).expanduser()  # type: ignore[arg-type]
        if env_path:
            return env_path
        for cand in DEFAULT_WORKDIR_FALLBACKS:
            try:
                if cand.exists() or cand.parent.exists():
                    return cand
            except Exception:
                continue
        return Path.cwd()

    def _resolve_provenance_path(self, override: Path | str | None) -> Path | None:
        if override:
            return Path(override).expanduser()
        env_path = os.environ.get(DEFAULT_PROVENANCE_ENV)
        if env_path:
            return Path(env_path).expanduser()
        # Default: provenance.sqlite under workdir
        return self._workdir / "provenance.sqlite"

    def _build_namespace(self, domain: str) -> StageNamespace:
        tools: dict[str, ToolMetadata] = {}
        for key, meta in (self._manifest or {}).items():
            if not isinstance(key, str):
                continue
            if not key.startswith(f"{domain} "):
                continue
            tool_name = key.split(" ", 1)[1]
            tools[tool_name.replace("-", "_")] = ToolMetadata(
                name=key,
                impl=meta.get("impl"),
                callable_obj=None,
                returns=meta.get("returns"),
                output_arg=meta.get("output_arg"),
                stdin_arg=meta.get("stdin_arg"),
                extras=meta.get("extras"),
                side_effects=meta.get("side_effects"),
            )
        return StageNamespace(domain, tools, self._workdir, self)

    def workspace(self) -> Path:
        """Return the active working directory for notebook outputs."""

        return self._workdir

    def provenance_store(self) -> Any:
        """Return the provenance store (null/SQLite depending on config)."""

        return self._provenance_store

    def to_pipeline(self) -> list[dict[str, Any]]:
        """Export recorded invocations to a pipeline-like structure."""

        stages: list[dict[str, Any]] = []
        for inv in self._invocations:
            tool = inv.get("tool")
            if not isinstance(tool, str) or " " not in tool:
                continue
            domain, cmd = tool.split(" ", 1)
            stages.append(
                {
                    "stage": domain,
                    "command": cmd,
                    "args": inv.get("kwargs") or {},
                }
            )
        return stages

    def to_cli(self) -> list[str]:
        """Export recorded invocations to CLI-equivalent command strings."""

        cli_cmds: list[str] = []
        for inv in self._invocations:
            tool = inv.get("tool")
            if not isinstance(tool, str):
                continue
            args = inv.get("kwargs") or {}
            parts = ["zyra"] + tool.split(" ")
            for k, v in args.items():
                flag = f"--{k.replace('_', '-')}"
                if isinstance(v, bool):
                    if v:
                        parts.append(flag)
                else:
                    parts.extend([flag, str(v)])
            cli_cmds.append(" ".join(parts))
        return cli_cmds


def create_session(
    manifest: dict[str, Any] | None = None,
    *,
    workdir: Path | None = None,
    provenance_path: Path | str | None = None,
) -> Session:
    """Factory for notebook sessions."""

    return Session(manifest=manifest, workdir=workdir, provenance_path=provenance_path)


__all__ = ["Session", "create_session", "StageNamespace", "ToolMetadata"]
