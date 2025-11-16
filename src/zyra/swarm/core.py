# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import Callable, Iterable, MutableMapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterator, Protocol, runtime_checkable

from .guardrails import BaseGuardrailsAdapter, NullGuardrailsAdapter

LOG = logging.getLogger("zyra.swarm.core")
DEFAULT_MAX_WORKERS = 8


@runtime_checkable
class AgentSpecProtocol(Protocol):
    """Subset of AgentSpec attributes used by the orchestrator."""

    id: str
    role: str | None
    prompt_ref: str | None
    params: dict[str, Any] | None
    depends_on: list[str] | None


class SwarmAgentProtocol(Protocol):
    """Minimal agent surface required by the orchestrator."""

    spec: AgentSpecProtocol

    async def run(self, context: MutableMapping[str, Any]) -> dict[str, Any]:
        """Execute the agent asynchronously and return output mapping."""


@dataclass
class StageContext(MutableMapping[str, Any]):
    """Shared mutable context passed between stage agents."""

    state: dict[str, Any] = field(default_factory=dict)
    inputs: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __getitem__(self, key: str) -> Any:
        return self.state[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.state[key] = value

    def __delitem__(self, key: str) -> None:
        del self.state[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.state)

    def __len__(self) -> int:
        return len(self.state)

    def get(self, key: str, default: Any | None = None) -> Any:
        return self.state.get(key, default)

    def setdefault(self, key: str, default: Any | None = None) -> Any:
        return self.state.setdefault(key, default)

    @property
    def outputs(self) -> dict[str, Any]:
        return self.state.setdefault("outputs", {})


class SwarmOrchestrator:
    """Async orchestrator that coordinates cooperative agents."""

    def __init__(
        self,
        agents: Iterable[SwarmAgentProtocol],
        *,
        max_workers: int | None = None,
        max_rounds: int = 1,
        event_hook: Callable[[str, dict[str, Any]], None] | None = None,
        guardrails: BaseGuardrailsAdapter | None = None,
    ) -> None:
        self.agents = list(agents)
        self.max_workers = max_workers
        self.max_rounds = max_rounds
        self.provenance: list[dict[str, Any]] = []
        self.errors: list[dict[str, Any]] = []
        self.failed_agents: list[str] = []
        self._event_hook = event_hook
        self._guardrails = guardrails or NullGuardrailsAdapter()

    def _emit_event(self, name: str, payload: dict[str, Any]) -> None:
        if not self._event_hook:
            return
        try:
            self._event_hook(name, payload)
        except Exception:
            LOG.debug("swarm event hook failed for %s", name, exc_info=True)

    def _auto_pool_size(self, n: int) -> int:
        env_cap = int(
            os.getenv("ZYRA_SWARM_MAX_WORKERS_CAP", str(DEFAULT_MAX_WORKERS))
            or DEFAULT_MAX_WORKERS
        )
        cores = os.cpu_count() or DEFAULT_MAX_WORKERS
        pool = max(1, min(n, cores, env_cap))
        return pool

    async def _run_agent_with_retries(
        self, agent: SwarmAgentProtocol, context: MutableMapping[str, Any]
    ) -> dict[str, Any]:
        p = agent.spec.params or {}
        max_retries = int(p.get("max_retries", 0) or 0)
        backoff_ms = int(p.get("backoff_ms", 50) or 0)
        backoff_factor = float(p.get("backoff_factor", 2.0) or 2.0)
        max_backoff_ms = int(p.get("max_backoff_ms", 500) or 500)

        attempt = 0
        while True:
            try:
                return await agent.run(context)
            except Exception:
                if attempt >= max_retries:
                    raise
                delay_ms = int(
                    min(max_backoff_ms, backoff_ms * (backoff_factor**attempt))
                )
                if delay_ms > 0:
                    await asyncio.sleep(delay_ms / 1000.0)
                attempt += 1

    async def _run_round(
        self, agents: list[SwarmAgentProtocol], context: MutableMapping[str, Any]
    ) -> dict[str, Any]:
        outputs: dict[str, Any] = {}
        pool_size = (
            self.max_workers
            if self.max_workers and self.max_workers > 0
            else self._auto_pool_size(len(agents))
        )
        sem = asyncio.Semaphore(pool_size)
        debug = (os.environ.get("ZYRA_VERBOSITY") or "").lower() == "debug"
        if debug:
            LOG.debug("[swarm] running %d agents (pool=%d)", len(agents), pool_size)

        async def run_one(agent: SwarmAgentProtocol) -> dict[str, Any]:
            async with sem:
                t0 = time.perf_counter()
                started = datetime.now(timezone.utc).isoformat()
                aid = agent.spec.id
                role = agent.spec.role or "specialist"
                if debug:
                    LOG.debug("[agent %s] start", aid)
                self._emit_event(
                    "agent_started", {"agent": aid, "role": role, "started": started}
                )
                try:
                    res = await self._run_agent_with_retries(agent, context)
                    if isinstance(res, dict):
                        res = self._guardrails.validate(agent, res)
                    else:
                        res = {}
                except Exception as exc:  # pragma: no cover
                    self.errors.append(
                        {
                            "agent": aid,
                            "message": str(exc) or "agent failed",
                            "retried": int(
                                (agent.spec.params or {}).get("max_retries", 0) or 0
                            ),
                        }
                    )
                    if aid not in self.failed_agents:
                        self.failed_agents.append(aid)
                    if debug:
                        LOG.warning("[agent %s] fail: %s", aid, exc)
                    self._emit_event(
                        "agent_failed",
                        {"agent": aid, "role": role, "error": str(exc) or "failed"},
                    )
                    res = {}
                dt_ms = int((time.perf_counter() - t0) * 1000)
                if dt_ms < 0:
                    dt_ms = 0
                if debug and isinstance(res, dict) and res:
                    try:
                        from zyra.utils.cli_helpers import sanitize_for_log

                        for key, value in res.items():
                            s = value if isinstance(value, str) else str(value)
                            s = sanitize_for_log(s)
                            preview = s[:160] + ("…" if len(s) > 160 else "")
                            LOG.info("[agent %s:%s] -> %s: %s", aid, role, key, preview)
                    except Exception:
                        pass
                prompt_ref = agent.spec.prompt_ref
                if not prompt_ref:
                    known_ids = {
                        "summary",
                        "context",
                        "critic",
                        "editor",
                        "audience_adapter",
                    }
                    base_name = aid if aid in known_ids else role
                    prompt_ref = f"zyra.assets/llm/prompts/narrate/{base_name}.md"
                llm_obj = getattr(agent, "llm", None) or context.get("llm")
                self.provenance.append(
                    {
                        "agent": aid,
                        "model": getattr(llm_obj, "model", None),
                        "started": started,
                        "prompt_ref": prompt_ref,
                        "duration_ms": dt_ms,
                    }
                )
                if debug:
                    LOG.debug("[agent %s] done in %d ms", aid, dt_ms)
                self._emit_event(
                    "agent_completed",
                    {"agent": aid, "role": role, "duration_ms": dt_ms},
                )
                return res

        results = await asyncio.gather(*(run_one(agent) for agent in agents))
        for res in results:
            outputs.update(res)
        try:
            context.setdefault("outputs", {})
            context["outputs"].update(outputs)
        except Exception:
            pass
        return outputs

    async def _execute_dag(self, context: MutableMapping[str, Any]) -> dict[str, Any]:
        id_to_agent = {agent.spec.id: agent for agent in self.agents}
        deps: dict[str, set[str]] = {
            aid: set(id_to_agent[aid].spec.depends_on or []) for aid in id_to_agent
        }
        remaining = set(id_to_agent.keys())
        outputs: dict[str, Any] = {}
        while remaining:
            ready_ids = [aid for aid in remaining if not deps.get(aid)]
            if not ready_ids:
                for aid in sorted(remaining):
                    if aid not in self.failed_agents:
                        self.failed_agents.append(aid)
                        self.errors.append(
                            {
                                "agent": aid,
                                "message": "skipped due to unmet dependencies",
                                "retried": 0,
                            }
                        )
                        self._emit_event(
                            "agent_blocked",
                            {"agent": aid, "reason": "unmet dependencies"},
                        )
                break
            ready = [id_to_agent[aid] for aid in ready_ids]
            outputs.update(await self._run_round(ready, context))
            for aid in ready_ids:
                remaining.discard(aid)
                if aid not in self.failed_agents:
                    for dep in deps.values():
                        dep.discard(aid)
        return outputs

    async def execute(
        self, context: MutableMapping[str, Any] | None = None
    ) -> dict[str, Any]:
        ctx: MutableMapping[str, Any] = {} if context is None else context
        outputs: dict[str, Any] = {}
        if not self.agents:
            return outputs

        started_ts = datetime.now(timezone.utc).isoformat()
        self._emit_event(
            "run_started",
            {"agent_count": len(self.agents), "started": started_ts},
        )

        if any(agent.spec.depends_on for agent in self.agents):
            outputs.update(await self._execute_dag(ctx))
        else:
            review_agents = [
                agent
                for agent in self.agents
                if agent.spec.role in {"critic", "editor"}
            ]
            outputs.update(await self._run_round(self.agents, ctx))
            rounds = max(0, int(self.max_rounds or 0))
            extra = max(0, rounds - 1)
            for _ in range(extra):
                if not review_agents:
                    break
                outputs.update(await self._run_round(review_agents, ctx))

        completed_ts = datetime.now(timezone.utc).isoformat()
        self._emit_event(
            "run_completed",
            {
                "agent_count": len(self.agents),
                "errors": list(self.errors),
                "failed_agents": list(self.failed_agents),
                "completed": completed_ts,
            },
        )
        return outputs
