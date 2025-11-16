# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from zyra.pipeline_runner import _stage_group_alias


def _as_list(val: Any | None) -> list[str]:
    if val is None:
        return []
    if isinstance(val, str):
        return [val] if val else []
    if isinstance(val, Sequence):
        out: list[str] = []
        for item in val:
            if not isinstance(item, str):
                continue
            item = item.strip()
            if item:
                out.append(item)
        return out
    return []


_STAGES_DEFAULT_MOCK = {"simulate", "decide", "narrate", "verify"}


@dataclass(slots=True)
class StageAgentSpec:
    """Normalized description of a stage-aware agent in `zyra swarm`."""

    id: str
    stage: str
    command: str | None = None
    args: dict[str, Any] = field(default_factory=dict)
    role: str | None = None
    outputs: list[str] = field(default_factory=list)
    stdin_from: str | None = None
    stdout_key: str | None = None
    depends_on: list[str] = field(default_factory=list)
    params: dict[str, Any] = field(default_factory=dict)
    parallel_ok: bool = True
    behavior: str = "cli"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("StageAgentSpec requires id")
        if not self.stage:
            raise ValueError(f"StageAgentSpec({self.id}) requires stage")
        self.stage = _stage_group_alias(str(self.stage))
        if not self.stage:
            raise ValueError(
                f"StageAgentSpec({self.id}) stage must resolve to CLI group"
            )
        if self.stdout_key is None:
            self.stdout_key = self.id
        self.depends_on = [d for d in (self.depends_on or []) if d and d != self.id]
        self.outputs = [o for o in (self.outputs or []) if o]
        if self.role is None and self.stage in {"decide", "narrate"}:
            self.role = self.stage
        behavior = (self.behavior or "").strip().lower()
        if not behavior:
            behavior = "cli"
        if (
            behavior == "cli"
            and not self.command
            and self.stage in _STAGES_DEFAULT_MOCK
        ):
            behavior = "mock"
        self.behavior = behavior
        if not isinstance(self.metadata, dict):
            self.metadata = {}

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> StageAgentSpec:
        """Build a StageAgentSpec from a manifest mapping."""
        if not isinstance(data, Mapping):
            raise TypeError("StageAgentSpec.from_mapping expects a mapping")
        spec_id = str(data.get("id") or "").strip()
        stage = str(data.get("stage") or "").strip()
        command = data.get("command")
        if command is not None:
            command = str(command).strip()
        args = dict(data.get("args") or {})
        role = data.get("role")
        role = str(role).strip() if isinstance(role, str) and role.strip() else None
        outputs = _as_list(data.get("outputs"))
        stdin_from = data.get("stdin_from")
        if isinstance(stdin_from, str):
            stdin_from = stdin_from.strip() or None
        stdout_key = data.get("stdout_key")
        if isinstance(stdout_key, str):
            stdout_key = stdout_key.strip() or None
        depends_on = _as_list(data.get("depends_on"))
        params = dict(data.get("params") or {})
        parallel_ok = bool(data.get("parallel_ok", True))
        behavior = str(data.get("behavior") or "cli").strip() or "cli"
        metadata = dict(data.get("metadata") or {})
        return cls(
            id=spec_id,
            stage=stage,
            command=command,
            args=args,
            role=role,
            outputs=outputs,
            stdin_from=stdin_from,
            stdout_key=stdout_key,
            depends_on=depends_on,
            params=params,
            parallel_ok=parallel_ok,
            behavior=behavior,
            metadata=metadata,
        )

    def to_stage_mapping(self) -> dict[str, Any]:
        """Return a pipeline-runner stage mapping for CLI execution."""
        return {
            "stage": self.stage,
            "command": self.command,
            "args": dict(self.args),
        }


def load_stage_agent_specs(doc: Mapping[str, Any]) -> list[StageAgentSpec]:
    """Parse a manifest mapping into StageAgentSpec objects."""
    agents_val = doc.get("agents")
    if agents_val is None:
        return []
    specs: list[StageAgentSpec] = []
    if isinstance(agents_val, Mapping):
        items: Iterable[tuple[str, Any]] = agents_val.items()
    elif isinstance(agents_val, Sequence):
        items = [(None, item) for item in agents_val]
    else:
        return []
    for key, raw in items:
        if isinstance(raw, Mapping):
            data = dict(raw)
            if not data.get("id") and key:
                data["id"] = key
            specs.append(StageAgentSpec.from_mapping(data))
        elif isinstance(raw, str):
            specs.append(
                StageAgentSpec(
                    id=raw,
                    stage=raw,
                    command=None,
                )
            )
    return specs
