# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
import re
from dataclasses import asdict
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Mapping, MutableMapping

from zyra.api.services import manifest as manifest_service
from zyra.pipeline_runner import _build_argv_for_stage, _run_cli
from zyra.swarm.core import SwarmAgentProtocol
from zyra.swarm.guardrails import build_guardrails_adapter
from zyra.swarm.proposals import (
    ToolProposal,
    ToolProposalRequest,
    generate_proposal,
    parse_proposal_payload,
)
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
        message = template.format(
            stage=self.spec.stage,
            id=self.spec.id,
            depends_on=",".join(depends) or "",
        )
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
    if behavior == "proposal":
        return ProposalStageAgent(spec)
    return NoopStageAgent(spec)


class ProposalStageAgent(StageAgent):
    """Agent that produces a structured tool proposal before execution."""

    def __init__(self, spec: StageAgentSpec) -> None:
        super().__init__(spec)
        self._cli_runner = CliStageAgent(spec)
        metadata = self.spec.metadata or {}
        schema = metadata.get("proposal_guardrails")
        strict = bool(metadata.get("proposal_guardrails_strict"))
        self._proposal_guardrails = build_guardrails_adapter(schema, strict=strict)

    def _build_request(self, context: MutableMapping[str, Any]) -> ToolProposalRequest:
        metadata = self.spec.metadata or {}
        options = metadata.get("proposal_options") or []
        defaults: dict[str, Any] = dict(self.spec.args or {})
        meta_defaults = metadata.get("proposal_defaults") or {}
        for key, value in (
            meta_defaults.items() if isinstance(meta_defaults, Mapping) else []
        ):
            defaults.setdefault(key, value)
        instructions = metadata.get("proposal_instructions")
        if not options:
            raise ValueError(
                f"{self.spec.id}: proposal stage requires proposal_options"
            )
        ctx_meta = context.get("metadata") if isinstance(context, dict) else None
        request_ctx: dict[str, Any] = {}
        if isinstance(ctx_meta, dict) and ctx_meta.get("intent"):
            request_ctx["intent"] = ctx_meta["intent"]
        return ToolProposalRequest(
            stage_id=self.spec.id,
            stage=self.spec.stage,
            options=[str(opt) for opt in options],
            defaults=dict(defaults or {}),
            context=request_ctx,
            instructions=str(instructions) if isinstance(instructions, str) else None,
        )

    def _proposal_to_spec(self, command: str, args: dict[str, Any]) -> StageAgentSpec:
        resolved = StageAgentSpec(
            id=self.spec.id,
            stage=self.spec.stage,
            command=command,
            args=dict(args or {}),
            role=self.spec.role,
            outputs=list(self.spec.outputs or []),
            stdin_from=self.spec.stdin_from,
            stdout_key=self.spec.stdout_key,
            depends_on=list(self.spec.depends_on or []),
            params=dict(self.spec.params or {}),
            parallel_ok=self.spec.parallel_ok,
            behavior="cli",
            metadata=dict(self.spec.metadata or {}),
            prompt_ref=self.spec.prompt_ref,
        )
        return resolved

    def _apply_proposal_guardrails(self, proposal: ToolProposal) -> ToolProposal:
        payload = {"proposal": asdict(proposal)}
        validated = self._proposal_guardrails.validate(self, payload)
        data = validated.get("proposal")
        if data is None:
            return proposal
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except json.JSONDecodeError as exc:  # pragma: no cover - JSON detail
                raise ValueError(
                    f"{self.spec.id}: proposal guardrails returned invalid JSON"
                ) from exc
        if not isinstance(data, Mapping):
            raise ValueError(
                f"{self.spec.id}: proposal guardrails must return JSON object"
            )
        try:
            return parse_proposal_payload(data)
        except ValueError as exc:
            raise ValueError(
                f"{self.spec.id}: proposal guardrails produced invalid payload"
            ) from exc

    async def run(self, context: MutableMapping[str, Any]) -> dict[str, Any]:
        request = self._build_request(context)
        self._log_event(context, "proposal_request", request)
        proposal = generate_proposal(request)
        self._log_event(context, "proposal_generated", proposal)
        try:
            proposal = self._apply_proposal_guardrails(proposal)
            canonical_command, command_meta = self._ensure_supported_command(
                proposal.command
            )
            self._validate_proposal_args(canonical_command, proposal.args, command_meta)
        except ValueError as exc:
            self._log_event(
                context,
                "proposal_invalid",
                {"command": proposal.command, "error": str(exc)},
            )
            raise
        resolved_spec = self._proposal_to_spec(canonical_command, proposal.args)
        self._log_event(
            context,
            "proposal_validated",
            {"command": canonical_command, "args": proposal.args},
        )
        self._record_proposal(context, canonical_command, proposal.args)
        # Reuse the CLI agent with resolved spec
        cli_agent = CliStageAgent(resolved_spec)
        return await cli_agent.run(context)

    def _ensure_supported_command(self, command: str) -> tuple[str, dict[str, Any]]:
        entry = _command_entry(self.spec.stage, command)
        if not entry:
            raise ValueError(
                f"Unsupported command '{self.spec.stage} {command}' for proposal"
            )
        return entry["command"], dict(entry.get("meta") or {})

    def _validate_proposal_args(
        self, command: str, args: dict[str, Any] | None, meta: dict[str, Any]
    ) -> None:
        payload = dict(args or {})
        missing = _missing_required_args(payload, meta)
        if missing:
            raise ValueError(
                f"{self.spec.id}: proposal '{self.spec.stage} {command}' "
                f"missing required arguments: {', '.join(sorted(missing))}"
            )
        placeholders = _placeholder_fields(payload)
        if placeholders:
            raise ValueError(
                f"{self.spec.id}: proposal '{self.spec.stage} {command}' "
                f"contains placeholder values for: {', '.join(sorted(placeholders))}"
            )

    def _record_proposal(
        self, context: MutableMapping[str, Any], command: str, args: dict[str, Any]
    ) -> None:
        if not isinstance(context, MutableMapping):
            return
        try:
            log = context.setdefault("proposal_log", {})
        except Exception:
            return
        if isinstance(log, MutableMapping):
            log[self.spec.id] = {
                "stage": self.spec.stage,
                "command": command,
                "args": dict(args or {}),
            }

    def _log_event(
        self,
        context: MutableMapping[str, Any],
        name: str,
        payload: Any,
    ) -> None:
        hook = _extract_event_hook(context)
        if callable(hook):
            hook(
                f"agent_{name}",
                {
                    "agent": self.spec.id,
                    "stage": self.spec.stage,
                    "payload": _safe_jsonable(payload),
                },
            )


def _extract_event_hook(context: Any) -> Callable[[str, dict[str, Any]], None] | None:
    if hasattr(context, "event_hook") and callable(context.event_hook):
        return context.event_hook
    if isinstance(context, MutableMapping):
        hook = context.get("event_hook")
        if callable(hook):
            return hook
    return None


def _safe_jsonable(obj: Any) -> Any:
    try:
        json.dumps(obj)  # type: ignore[arg-type]
        return obj
    except Exception:
        if isinstance(obj, ToolProposalRequest):
            return {
                "stage_id": obj.stage_id,
                "stage": obj.stage,
                "options": obj.options,
                "defaults": obj.defaults,
                "context": obj.context,
                "instructions": obj.instructions,
            }
        if isinstance(obj, ToolProposal):
            return asdict(obj)
        if hasattr(obj, "__dict__"):
            return {k: getattr(obj, k) for k in vars(obj)}
        return str(obj)


@lru_cache(maxsize=1)
def _manifest_command_catalog() -> dict[str, dict[str, dict[str, Any]]]:
    try:
        manifest = manifest_service.get_manifest()
    except Exception:
        return {}
    catalog: dict[str, dict[str, dict[str, Any]]] = {}
    for full_cmd, meta in manifest.items():
        if not isinstance(full_cmd, str):
            continue
        parts = full_cmd.split()
        if len(parts) < 2:
            continue
        stage = _normalize_stage(parts[0])
        command_name = " ".join(parts[1:]).strip()
        command_key = _normalize_command(command_name)
        catalog.setdefault(stage, {})[command_key] = {
            "command": command_name,
            "meta": meta or {},
        }
    return catalog


def _command_supported(stage: str, command: str) -> bool:
    return _command_entry(stage, command) is not None


def _command_entry(stage: str, command: str) -> dict[str, Any] | None:
    if not stage or not command:
        return None
    catalog = _manifest_command_catalog()
    stage_key = _normalize_stage(stage)
    command_key = _normalize_command(command)
    return catalog.get(stage_key, {}).get(command_key)


def _normalize_stage(stage: str) -> str:
    return str(stage or "").strip().lower()


def _normalize_command(command: str) -> str:
    return str(command or "").strip().lower()


def _missing_required_args(args: dict[str, Any], meta: dict[str, Any]) -> list[str]:
    required: list[str] = []
    for pos in meta.get("positionals") or []:
        if isinstance(pos, dict) and pos.get("required") and pos.get("name"):
            required.append(str(pos["name"]))
    options = meta.get("options") or {}
    if isinstance(options, dict):
        for flag, info in options.items():
            if not isinstance(info, dict) or not info.get("required"):
                continue
            required.append(_option_to_dest(flag))
    missing: list[str] = []
    for name in required:
        if not _arg_present(args, name):
            missing.append(name)
    return missing


def _placeholder_fields(args: dict[str, Any]) -> list[str]:
    fields: list[str] = []
    for key, value in args.items():
        if _looks_like_placeholder(value):
            fields.append(str(key))
    return fields


def _option_to_dest(flag: str) -> str:
    if not isinstance(flag, str):
        return ""
    stripped = flag.lstrip("-")
    return stripped.replace("-", "_")


def _arg_present(args: dict[str, Any], name: str) -> bool:
    if not name:
        return False
    keys = {
        name,
        name.replace("-", "_"),
        name.replace("_", "-"),
    }
    return any(key in args and args[key] not in (None, "", []) for key in keys)


_PLACEHOLDER_PATTERNS = [
    r"example\.(org|com|net)",
    r"/tmp/",
    r"/path/to",
    r"\byour[_-]",
    r"\btbd\b",
    r"<[^>]+>",
    r"todo",
    r"replace me",
]


def _looks_like_placeholder(value: Any) -> bool:
    if value in (None, ""):
        return True
    if not isinstance(value, str):
        return False
    text = value.strip().lower()
    if not text:
        return True
    return any(re.search(pattern, text) for pattern in _PLACEHOLDER_PATTERNS)
