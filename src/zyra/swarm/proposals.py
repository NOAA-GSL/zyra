# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Mapping

from zyra.api.services import manifest as manifest_service
from zyra.swarm.proposals_schema import validate_proposal


@dataclass
class ToolProposalRequest:
    """Description of a pending stage requiring a tool selection."""

    stage_id: str
    stage: str
    options: list[str]
    defaults: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)
    instructions: str | None = None


@dataclass
class ToolProposal:
    """Structured tool proposal returned by a stage agent."""

    stage_id: str
    command: str
    args: dict[str, Any]
    justification: str | None = None


def generate_proposal(request: ToolProposalRequest) -> ToolProposal:
    """Generate a tool proposal, preferring the LLM-backed hybrid workflow."""

    llm_proposal = _generate_proposal_via_llm(request)
    if llm_proposal:
        return llm_proposal

    if not request.options:
        raise ValueError(f"No proposal options available for stage {request.stage_id}")
    command = request.options[0]
    args = dict(request.defaults or {})
    payload = {
        "stage_id": request.stage_id,
        "command": command,
        "args": args,
        "justification": "auto-selected template",
    }
    return parse_proposal_payload(payload)


def coerce_proposal(data: Mapping[str, Any]) -> ToolProposal:
    """Build a ToolProposal from arbitrary mapping input."""

    if not isinstance(data, Mapping):
        raise TypeError("ToolProposal requires a mapping input")
    stage_id = str(data.get("stage_id") or "").strip()
    command = str(data.get("command") or "").strip()
    args = dict(data.get("args") or {})
    justification = data.get("justification")
    if not stage_id:
        raise ValueError("ToolProposal missing stage_id")
    if not command:
        raise ValueError("ToolProposal missing command")
    return ToolProposal(
        stage_id=stage_id,
        command=command,
        args=args,
        justification=str(justification) if justification else None,
    )


def parse_proposal_payload(data: Mapping[str, Any]) -> ToolProposal:
    """Validate and convert arbitrary payload to ToolProposal."""

    validated = validate_proposal(dict(data))
    return ToolProposal(
        stage_id=validated["stage_id"],
        command=validated["command"],
        args=validated["args"],
        justification=validated.get("justification"),
    )


def _generate_proposal_via_llm(request: ToolProposalRequest) -> ToolProposal | None:
    client = _load_llm_client()
    if client is None:
        return None
    stage_catalog = _load_stage_command_catalog()
    stage_meta = stage_catalog.get(request.stage)
    option_entries: list[dict[str, Any]] = []
    for option in request.options:
        meta = stage_meta.get(option) if stage_meta else None
        if not meta:
            continue
        option_entries.append(
            {
                "command": option,
                "description": str(meta.get("description") or ""),
                "required_args": _required_args(meta),
                "flags": _option_summaries(meta),
            }
        )
    if not option_entries:
        return None
    payload = {
        "stage": request.stage,
        "stage_id": request.stage_id,
        "options": option_entries,
        "defaults": request.defaults,
        "context": request.context,
    }
    if request.instructions:
        payload["instructions"] = request.instructions
    system_prompt = (
        "You are a Zyra stage specialist. Choose the best command from the provided option list and "
        "return a JSON object with fields stage_id, command, args, justification. Only pick commands "
        "from the list, include all required arguments, and avoid placeholder values."
    )
    user_prompt = json.dumps(payload, indent=2, sort_keys=True)
    try:
        raw = client.generate(system_prompt, user_prompt)
    except Exception:
        return None
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if (
        isinstance(data, dict)
        and "proposal" in data
        and isinstance(data["proposal"], Mapping)
    ):
        data = data["proposal"]
    try:
        return parse_proposal_payload(data)
    except Exception:
        return None


@lru_cache(maxsize=1)
def _load_stage_command_catalog() -> dict[str, dict[str, Any]]:
    try:
        manifest = manifest_service.get_manifest()
    except Exception:
        return {}
    catalog: dict[str, dict[str, Any]] = {}
    for full_cmd, meta in manifest.items():
        if not isinstance(full_cmd, str):
            continue
        parts = full_cmd.split()
        if len(parts) < 2:
            continue
        stage = parts[0]
        command = " ".join(parts[1:])
        catalog.setdefault(stage, {})[command] = meta or {}
    return catalog


def _required_args(meta: dict[str, Any]) -> list[str]:
    required: list[str] = []
    for pos in meta.get("positionals") or []:
        if isinstance(pos, dict) and pos.get("required") and pos.get("name"):
            required.append(str(pos["name"]))
    options = meta.get("options") or {}
    if isinstance(options, dict):
        for flag, info in options.items():
            if isinstance(info, dict) and info.get("required"):
                required.append(flag)
    return required


def _option_summaries(meta: dict[str, Any]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    options = meta.get("options") or {}
    if not isinstance(options, dict):
        return summaries
    for flag, info in options.items():
        if not isinstance(info, dict):
            continue
        summaries.append(
            {
                "flag": flag,
                "help": info.get("help"),
                "required": bool(info.get("required")),
            }
        )
    return sorted(summaries, key=lambda entry: entry["flag"])


def _load_llm_client():  # pragma: no cover - environment dependent
    try:
        from zyra.wizard import _select_provider
    except Exception:
        return None
    try:
        return _select_provider(None, None)
    except Exception:
        return None
