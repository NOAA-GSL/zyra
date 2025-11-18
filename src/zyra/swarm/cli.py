# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

from . import (
    StageAgentSpec,
    StageContext,
    build_guardrails_adapter,
    build_stage_agent,
    load_stage_agent_specs,
    open_provenance_store,
)
from .core import SwarmOrchestrator


def register_cli(parser: argparse.ArgumentParser) -> None:
    """Attach swarm CLI arguments to an argparse parser."""
    parser.add_argument(
        "--plan",
        required=False,
        help="YAML or JSON manifest describing stage agents",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        help="Max concurrent stage agents (auto when omitted)",
    )
    parser.add_argument(
        "--max-rounds",
        type=int,
        default=1,
        help="Review rounds; >1 re-runs critic/editor agents",
    )
    parser.add_argument(
        "--memory",
        help="Provenance store path (SQLite). Use '-' for in-memory only.",
    )
    parser.add_argument(
        "--guardrails",
        help="Optional Guardrails (.rail) schema to validate outputs",
    )
    parser.add_argument(
        "--strict-guardrails",
        action="store_true",
        help="Fail the run if guardrails validation fails",
    )
    parser.add_argument(
        "--output",
        help="Write final outputs to JSON file ('-' for stdout; default prints summary)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the resolved agents/graph without running",
    )
    parser.add_argument(
        "--log-events",
        action="store_true",
        help="Print provenance events to stdout as they are recorded",
    )
    parser.add_argument(
        "--dump-memory",
        help="Inspect an existing provenance DB (no execution performed)",
    )
    parser.set_defaults(func=_cmd_swarm)


def _cmd_swarm(ns: argparse.Namespace) -> int:
    if ns.dump_memory:
        return _dump_memory(ns.dump_memory)
    if not ns.plan:
        print("--plan is required when not using --dump-memory", file=sys.stderr)
        return 2
    try:
        plan = _load_plan(ns.plan)
    except ValueError as exc:
        print(str(exc))
        return 2
    try:
        specs = _resolve_specs(plan)
    except ValueError as exc:
        print(str(exc))
        return 2
    if ns.dry_run:
        print(_format_dry_run(specs))
        return 0
    try:
        outputs = _execute_specs(
            specs,
            plan=plan,
            plan_path=ns.plan,
            max_workers=ns.max_workers,
            max_rounds=ns.max_rounds,
            memory=ns.memory,
            guardrails=ns.guardrails,
            strict_guardrails=bool(ns.strict_guardrails),
            log_events=bool(ns.log_events),
        )
    except ValueError as exc:
        print(str(exc))
        return 2
    if ns.output:
        _write_outputs(ns.output, outputs)
    else:
        print(
            "swarm completed; outputs:",
            ", ".join(sorted(outputs.keys())) or "(none)",
        )
    return 0


def _load_plan(path: str) -> dict[str, Any]:
    target = Path(path)
    if not target.exists():
        raise ValueError(f"plan file not found: {path}")
    text = target.read_text(encoding="utf-8")
    if path.lower().endswith((".yaml", ".yml")):
        try:
            import yaml  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dep
            raise ValueError("PyYAML is required to parse YAML plans") from exc
        data = yaml.safe_load(text) or {}
    else:
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"failed to parse plan {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("plan file must contain a mapping at the root")
    return data


def _resolve_specs(plan: dict[str, Any]) -> list[StageAgentSpec]:
    specs = load_stage_agent_specs(plan)
    if not specs:
        raise ValueError("plan must include an 'agents' list with at least one entry")
    depends_map = plan.get("depends_on")
    if isinstance(depends_map, dict):
        for spec in specs:
            custom = depends_map.get(spec.id)
            if isinstance(custom, list) and not spec.depends_on:
                spec.depends_on = [str(v) for v in custom if isinstance(v, str)]
    return specs


def _execute_specs(
    specs: list[StageAgentSpec],
    *,
    plan: dict[str, Any],
    plan_path: str,
    max_workers: int | None,
    max_rounds: int | None,
    memory: str | None,
    guardrails: str | None,
    strict_guardrails: bool,
    log_events: bool = False,
) -> dict[str, Any]:
    agents = [build_stage_agent(spec) for spec in specs]
    ctx = StageContext(
        state={"outputs": {}},
        inputs=plan.get("inputs"),
        metadata=plan.get("metadata") or {},
    )
    store = open_provenance_store(
        memory, metadata={"plan": plan_path, "agent_count": len(agents)}
    )
    adapter = build_guardrails_adapter(guardrails, strict=strict_guardrails)
    try:
        base_hook = store.as_event_hook()

        if log_events:

            def _log_and_store(name: str, payload: dict[str, Any]) -> None:
                print(f"[event {name}] {_format_event_payload(name, payload)}")
                base_hook(name, payload)

            hook = _log_and_store
        else:
            hook = base_hook

        ctx.event_hook = hook
        ctx.state["event_hook"] = hook
        orch = SwarmOrchestrator(
            agents,
            max_workers=max_workers,
            max_rounds=int(max_rounds or 1),
            event_hook=hook,
            guardrails=adapter,
        )
        outputs = asyncio.run(orch.execute(ctx))
    finally:
        store.close()
    return outputs


def _dump_memory(path: str) -> int:
    target = Path(path)
    if not target.exists():
        print(f"provenance DB not found: {path}", file=sys.stderr)
        return 2
    conn = sqlite3.connect(str(target))
    try:
        conn.row_factory = sqlite3.Row
        runs = conn.execute(
            "SELECT run_id, started, completed, status, metadata FROM runs ORDER BY started DESC"
        ).fetchall()
        if not runs:
            print("No runs recorded.")
            return 0
        for run in runs:
            status = run["status"]
            meta = run["metadata"]
            print(
                f"Run {run['run_id']} started={run['started']} completed={run['completed']}"
            )
            if meta:
                print(f"  metadata: {meta}")
            if status:
                print(f"  status: {status}")
            events = conn.execute(
                "SELECT event, agent, created, payload FROM events WHERE run_id=? ORDER BY id",
                (run["run_id"],),
            ).fetchall()
            for evt in events:
                payload_raw = evt["payload"] or "{}"
                try:
                    payload_obj = json.loads(payload_raw)
                except Exception:  # pragma: no cover - corrupt payload
                    payload_obj = {"raw": payload_raw}
                body = _format_event_payload(evt["event"], payload_obj)
                print(f"    [{evt['created']}] [event {evt['event']}] {body}")
    finally:
        conn.close()
    return 0


def _format_dry_run(specs: list[StageAgentSpec]) -> str:
    lines = ["Swarm plan:"]
    for spec in specs:
        deps = f" depends_on={','.join(spec.depends_on)}" if spec.depends_on else ""
        behavior = f" behavior={spec.behavior}"
        stdin = f" stdin_from={spec.stdin_from}" if spec.stdin_from else ""
        lines.append(
            f"- {spec.id}: stage={spec.stage} command={spec.command or 'auto'}{deps}{stdin}{behavior}"
        )
    return "\n".join(lines)


def _write_outputs(path: str, outputs: dict[str, Any]) -> None:
    payload = {"outputs": outputs}
    if path.strip() == "-":
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _format_event_payload(name: str, payload: dict[str, Any]) -> str:
    if not isinstance(payload, dict):
        return json.dumps(payload, sort_keys=True)
    if name == "run_completed":
        base = (
            f"agent_count={payload.get('agent_count')} "
            f"errors={len(payload.get('errors') or [])} "
            f"failed={len(payload.get('failed_agents') or [])}"
        )
        proposals = payload.get("proposals")
        if isinstance(proposals, dict) and proposals:
            summary = ", ".join(
                f"{agent}:{info.get('command')}"
                for agent, info in proposals.items()
                if isinstance(info, dict)
            )
            return f"{base} proposals={summary}"
        return base
    if name.startswith("agent_proposal_"):
        agent = payload.get("agent") or "?"
        stage = payload.get("stage") or "?"
        inner = payload.get("payload") or {}
        if name == "agent_proposal_request":
            options = inner.get("options")
            defaults = inner.get("defaults") or {}
            intent = (inner.get("context") or {}).get("intent")
            extras = []
            if options:
                extras.append(f"options={options}")
            if defaults:
                extras.append(f"defaults={defaults}")
            if intent:
                extras.append(f"intent={intent!r}")
            extra_str = " ".join(extras) if extras else "no details"
            return f"agent={agent} stage={stage} {extra_str}"
        if name == "agent_proposal_generated":
            command = inner.get("command")
            args = inner.get("args")
            return (
                f"agent={agent} stage={stage} proposed command={command} "
                f"args={_render_short(args)}"
            )
        if name == "agent_proposal_validated":
            command = inner.get("command")
            args = inner.get("args")
            return (
                f"agent={agent} stage={stage} validated command={command} "
                f"args={_render_short(args)}"
            )
        if name == "agent_proposal_invalid":
            error = inner.get("error") or payload.get("error")
            command = inner.get("command") or payload.get("command")
            return (
                f"agent={agent} stage={stage} rejected command={command} "
                f"reason={error}"
            )
    return json.dumps(payload, sort_keys=True)


def _render_short(value: Any) -> str:
    try:
        text = json.dumps(value, sort_keys=True)
    except Exception:  # pragma: no cover - fallback for unserializable
        text = str(value)
    return text if len(text) <= 180 else text[:177] + "..."
