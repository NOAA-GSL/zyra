# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, MutableMapping

from zyra.pipeline_runner import _build_argv_for_stage, _run_cli
from zyra.swarm.core import SwarmAgentProtocol
from zyra.swarm.spec import StageAgentSpec


class StageAgent(SwarmAgentProtocol):
    """Base class implementing the SwarmAgentProtocol for stage agents."""

    def __init__(self, spec: StageAgentSpec) -> None:
        self.spec = spec

    async def run(self, context: MutableMapping[str, Any]) -> dict[str, Any]:
        raise NotImplementedError


class CliStageAgent(StageAgent):
    """Agent that executes a Zyra CLI stage using pipeline_runner helpers."""

    def __init__(
        self,
        spec: StageAgentSpec,
        *,
        build_stage_argv: Callable[[dict[str, Any]], list[str]] | None = None,
        run_cli: Callable[[list[str], bytes | None], tuple[int, bytes, str]]
        | None = None,
    ) -> None:
        super().__init__(spec)
        self.build_stage_argv = build_stage_argv or _build_argv_for_stage
        self.run_cli = run_cli or _run_cli

    def _read_input_bytes(self, context: MutableMapping[str, Any]) -> bytes | None:
        source = self.spec.stdin_from
        if not source:
            return None
        outputs = context.get("outputs") if isinstance(context, dict) else None
        payload = outputs.get(source) if isinstance(outputs, dict) else None
        if payload is None:
            return None
        if isinstance(payload, bytes):
            return payload
        if isinstance(payload, str):
            return payload.encode("utf-8")
        if isinstance(payload, dict):
            path = payload.get("path")
            if isinstance(path, str):
                try:
                    return Path(path).read_bytes()
                except OSError:
                    return None
        raise TypeError(
            f"{self.spec.id}: unsupported stdin payload type {type(payload)!r}"
        )

    def _emit_outputs(self, stdout: bytes) -> dict[str, Any]:
        key = self.spec.stdout_key
        if not key:
            return {}
        return {key: stdout}

    async def run(self, context: MutableMapping[str, Any]) -> dict[str, Any]:
        stage_mapping = self.spec.to_stage_mapping()
        argv = self.build_stage_argv(stage_mapping)
        stdin_bytes = self._read_input_bytes(context)
        rc, stdout_bytes, stderr_text = self.run_cli(argv, stdin_bytes)
        if rc != 0:
            raise RuntimeError(
                f"{self.spec.id}: CLI exited {rc} ({stderr_text or 'no stderr captured'})"
            )
        return self._emit_outputs(stdout_bytes)


class NoopStageAgent(StageAgent):
    """Placeholder agent used for not-yet-implemented stage types."""

    async def run(self, context: MutableMapping[str, Any]) -> dict[str, Any]:
        key = self.spec.stdout_key or self.spec.id
        if not key:
            return {}
        return {key: f"{self.spec.id}:noop"}


class MockStageAgent(StageAgent):
    """Lightweight agent that emits structured mock data per stage."""

    DEFAULT_MESSAGES = {
        "simulate": "simulate stage {id}: generated mock ensemble",
        "decide": "decide stage {id}: selected baseline option",
        "narrate": "narrate stage {id}: produced placeholder summary",
        "verify": "verify stage {id}: computed mock metric",
    }

    async def run(self, context: MutableMapping[str, Any]) -> dict[str, Any]:
        key = self.spec.stdout_key or self.spec.id
        if not key:
            return {}
        template = (
            self.spec.metadata.get("template")
            if isinstance(self.spec.metadata, dict)
            else None
        )
        if not template:
            template = self.DEFAULT_MESSAGES.get(
                self.spec.stage, "stage {id}: mock output available"
            )
        ctx_outputs = (
            context.get("outputs") if isinstance(context, MutableMapping) else None
        )
        depends: list[str] = []
        if isinstance(ctx_outputs, dict):
            for d in self.spec.depends_on or []:
                if ctx_outputs.get(d) is not None:
                    depends.append(d)
        message = template.format(stage=self.spec.stage, id=self.spec.id)
        payload: dict[str, Any] = {
            "stage": self.spec.stage,
            "agent_id": self.spec.id,
            "message": message,
            "depends_on": depends,
        }
        outputs: dict[str, Any] = {}
        targets = list(self.spec.outputs) if self.spec.outputs else [key]
        for target in targets:
            outputs[target] = payload
        return outputs


def build_stage_agent(spec: StageAgentSpec) -> StageAgent:
    """Factory that returns the appropriate agent for a StageAgentSpec."""
    behavior = (spec.behavior or "cli").lower()
    if behavior == "cli":
        return CliStageAgent(spec)
    if behavior == "mock":
        return MockStageAgent(spec)
    return NoopStageAgent(spec)
