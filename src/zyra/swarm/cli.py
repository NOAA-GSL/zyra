# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Sequence

from zyra.pipeline_runner import _stage_group_alias

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
        "--agents",
        help=(
            "Comma-separated list of stages to run (e.g., 'acquire,visualize'); "
            "defaults to all stages declared in the plan."
        ),
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
    parser.add_argument(
        "--parallel",
        dest="parallel",
        action="store_true",
        help="Allow independent agents to run concurrently (default).",
    )
    parser.add_argument(
        "--no-parallel",
        dest="parallel",
        action="store_false",
        help="Force sequential execution (sets max-workers=1).",
    )
    parser.add_argument(
        "--provider",
        help=(
            "Override the LLM provider for proposal/narrate agents "
            "(openai|ollama|gemini|vertex|mock). Gemini supports GOOGLE_API_KEY or Vertex credentials."
        ),
    )
    parser.add_argument(
        "--model",
        help="Override the LLM model name for proposal/narrate agents",
    )
    parser.add_argument(
        "--base-url",
        dest="base_url",
        help="Override the LLM provider base URL (e.g., Ollama endpoint)",
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
    stage_filter = _parse_stage_filter(ns.agents)
    try:
        specs = _resolve_specs(plan, allowed_stages=stage_filter)
    except ValueError as exc:
        print(str(exc))
        return 2
    if ns.dry_run:
        print(_format_dry_run(specs))
        return 0
    effective_workers = ns.max_workers
    if ns.parallel is False:
        effective_workers = 1
    try:
        with _temporary_llm_env(ns.provider, ns.model, ns.base_url):
            outputs = _execute_specs(
                specs,
                plan=plan,
                plan_path=ns.plan,
                max_workers=effective_workers,
                max_rounds=ns.max_rounds,
                memory=ns.memory,
                guardrails=ns.guardrails,
                strict_guardrails=bool(ns.strict_guardrails),
                log_events=bool(ns.log_events),
                llm_overrides={
                    "provider": ns.provider,
                    "model": ns.model,
                    "base_url": ns.base_url,
                },
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


def _resolve_specs(
    plan: dict[str, Any], allowed_stages: set[str] | None = None
) -> list[StageAgentSpec]:
    specs = load_stage_agent_specs(plan)
    if not specs:
        raise ValueError("plan must include an 'agents' list with at least one entry")
    depends_map = plan.get("depends_on")
    if isinstance(depends_map, dict):
        for spec in specs:
            custom = depends_map.get(spec.id)
            if isinstance(custom, list) and not spec.depends_on:
                spec.depends_on = [str(v) for v in custom if isinstance(v, str)]
    if allowed_stages:
        filtered: list[StageAgentSpec] = [
            spec for spec in specs if spec.stage in allowed_stages
        ]
        if not filtered:
            raise ValueError(
                "No agents remain after applying --agents filter "
                f"(requested: {', '.join(sorted(allowed_stages))})"
            )
        available = {spec.stage for spec in specs}
        missing = allowed_stages - available
        if missing:
            plural = "s" if len(missing) > 1 else ""
            raise ValueError(
                f"Unknown stage{plural} in --agents filter: {', '.join(sorted(missing))}"
            )
        specs = filtered
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
    llm_overrides: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    agents = [build_stage_agent(spec) for spec in specs]
    plan_meta = dict(plan.get("metadata") or {})
    intent_text = plan.get("intent")
    if intent_text and not plan_meta.get("intent"):
        plan_meta["intent"] = intent_text
    summary_text = plan.get("plan_summary")
    if summary_text:
        plan_meta["plan_summary"] = summary_text
    if llm_overrides:
        llm_meta = {k: v for k, v in llm_overrides.items() if v}
        if llm_meta:
            plan_meta.setdefault("llm", {}).update(llm_meta)
    ctx = StageContext(
        state={"outputs": {}},
        inputs=plan.get("inputs"),
        metadata=plan_meta,
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
    if name == "agent_verify_result":
        agent = payload.get("agent") or "?"
        stage = payload.get("stage") or "?"
        verdict = payload.get("verdict") or "unknown"
        metric = payload.get("metric")
        message = payload.get("message") or ""
        bits = [
            f"agent={agent}",
            f"stage={stage}",
            f"verdict={verdict}",
        ]
        if metric:
            bits.append(f"metric={metric}")
        if message:
            bits.append(f"message={message}")
        return " ".join(bits)
    return json.dumps(payload, sort_keys=True)


def _render_short(value: Any) -> str:
    try:
        text = json.dumps(value, sort_keys=True)
    except Exception:  # pragma: no cover - fallback for unserializable
        text = str(value)
    return text if len(text) <= 180 else text[:177] + "..."


def _parse_stage_filter(value: str | None) -> set[str] | None:
    if not value:
        return None
    if isinstance(value, (list, tuple)):
        items: Iterable[str] = value
    else:
        items = value.split(",")
    normalized: set[str] = set()
    for item in items:
        token = item.strip()
        if not token:
            continue
        normalized.add(_stage_group_alias(token.lower()))
    return normalized or None


@contextmanager
def _temporary_llm_env(
    provider: str | None, model: str | None, base_url: str | None
) -> Sequence[str]:
    overrides: dict[str, str] = {}
    if provider:
        overrides["LLM_PROVIDER"] = provider
        overrides["DATAVIZHUB_LLM_PROVIDER"] = provider
    if model:
        overrides["LLM_MODEL"] = model
        overrides["DATAVIZHUB_LLM_MODEL"] = model
    if base_url:
        overrides["LLM_BASE_URL"] = base_url
        overrides["DATAVIZHUB_LLM_BASE_URL"] = base_url
    previous: dict[str, str | None] = {}
    for key, value in overrides.items():
        previous[key] = os.environ.get(key)
        os.environ[key] = value
    try:
        yield overrides.keys()
    finally:
        for key, old in previous.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old
