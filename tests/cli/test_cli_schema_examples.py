from __future__ import annotations

from typing import Dict, List, Set

# Avoid external dependencies and sockets: call router functions directly.
from datavizhub.api.routers import cli as cli_router


def _get_commands() -> Dict[str, dict]:
    data = cli_router.list_cli_commands()
    assert isinstance(data, dict)
    return data


def _get_examples() -> List[dict]:
    payload = cli_router.list_cli_examples()
    assert isinstance(payload, dict) and "examples" in payload
    examples = payload["examples"]
    assert isinstance(examples, list)
    return examples


def test_examples_stage_command_exist_in_commands() -> None:
    cmds = _get_commands()
    examples = _get_examples()

    for ex in examples:
        req = ex.get("request", {})
        stage = req.get("stage")
        command = req.get("command")
        assert stage in cmds, f"Example '{ex.get('name')}' uses unknown stage '{stage}'"
        stage_info = cmds[stage]
        assert (
            command in stage_info.get("commands", [])
        ), f"Example '{ex.get('name')}' uses unknown command '{command}' for stage '{stage}'"
        # Also ensure schema exists for the command
        schema = stage_info.get("schema", {})
        assert command in schema, f"No schema found for {stage}.{command}"


def test_examples_args_match_schema() -> None:
    cmds = _get_commands()
    examples = _get_examples()

    for ex in examples:
        req = ex.get("request", {})
        stage = req.get("stage")
        command = req.get("command")
        args = req.get("args", {}) or {}
        stage_info = cmds[stage]
        schema_items = stage_info.get("schema", {}).get(command) or []
        allowed: Set[str] = {
            item.get("name") for item in schema_items if item.get("name")
        }
        unknown = sorted(set(args.keys()) - allowed)
        assert not unknown, (
            f"Example '{ex.get('name')}' has unknown args for {stage}.{command}: {unknown}. "
            f"Allowed: {sorted(allowed)}"
        )
