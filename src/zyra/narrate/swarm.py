# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

# Default worker cap used when no explicit limit is provided via CLI/env.
# Eight threads keeps concurrency modest on laptops/CI while still exercising
# parallel behaviour in tests.
DEFAULT_MAX_WORKERS = 8
IMAGE_MAX_BYTES = 1_500_000


@dataclass
class AgentSpec:
    id: str
    role: str = "specialist"  # specialist|critic|editor|planner
    prompt: str | None = None
    prompt_ref: str | None = None
    outputs: list[str] | None = None
    params: dict[str, Any] | None = None
    depends_on: list[str] | None = None


class Agent:
    def __init__(
        self,
        spec: AgentSpec,
        audience: list[str] | None = None,
        style: str | None = None,
        llm: Any | None = None,
    ):
        self.spec = spec
        self.audience = audience or []
        self.style = style
        self.llm = llm

    async def run(self, context: dict[str, Any]) -> dict[str, Any]:
        # Minimal LLM-backed behavior: one sentence per declared output
        outs: dict[str, Any] = {}
        llm = self.llm or context.get("llm")
        sys_prompt = (
            self.spec.prompt
            or "You are a narration agent for Zyra. Keep outputs concise."
        )
        role = self.spec.role
        ctx_outputs: dict[str, Any] = (
            context.get("outputs", {}) if isinstance(context, dict) else {}
        )
        critic_rubric: list[str] = (
            context.get("critic_rubric", []) if isinstance(context, dict) else []
        )
        # Prepare optional seed narration and highlights from input_data
        seed_text = ""
        highlights = []
        idata = context.get("input_data") if isinstance(context, dict) else None
        if isinstance(idata, dict):
            # Seed narration
            seed = (
                idata.get("narrative") or idata.get("description") or idata.get("title")
            )
            if isinstance(seed, str) and seed.strip():
                seed_text = seed.strip()[:280]
            # Generic highlights: pull up to 3 recent numeric values from lists
            try:

                def _human_key(k: str) -> str:
                    k2 = str(k).replace("_", " ").strip()
                    return k2[:24]

                def _add_highlight(label: str, val: float) -> None:
                    if len(highlights) < 3:
                        highlights.append(f"{label} ≈ {val:g}")

                def _scan(obj, prefix: str | None = None):
                    if isinstance(obj, dict):
                        for kk, vv in obj.items():
                            _scan(vv, prefix=kk)
                    elif isinstance(obj, list) and obj:
                        last = obj[-1]
                        if isinstance(last, (int, float)):
                            _add_highlight(_human_key(prefix or "value"), float(last))
                        elif isinstance(last, dict):
                            v = last.get("value")
                            if isinstance(v, (int, float)):
                                _add_highlight(_human_key(prefix or "value"), float(v))

                _scan(idata.get("data", idata))
            except Exception:
                pass
        elif isinstance(idata, str) and idata.strip():
            seed_text = idata.strip()[:280]

        # Optional image attachments (multimodal): build once and reuse
        attach_images = (
            bool(context.get("attach_images")) if isinstance(context, dict) else False
        )
        image_b64: list[str] = []
        image_list_for_prompt: list[str] = []
        if attach_images and isinstance(idata, dict):
            try:
                cache = (
                    context.setdefault("_image_cache", {})
                    if isinstance(context, dict)
                    else {}
                )
                if cache and cache.get("b64"):
                    image_b64 = cache.get("b64")
                    image_list_for_prompt = cache.get("labels", [])
                else:
                    imgs = idata.get("images") or []
                    if isinstance(imgs, list):
                        # Import lazily so Path/file I/O helpers are only loaded when
                        # callers opt into image attachments (WPS433).
                        import base64  # noqa: WPS433
                        from pathlib import Path  # noqa: WPS433

                        for it in imgs[:4]:
                            p = (it or {}).get("path") if isinstance(it, dict) else None
                            label = (
                                (it or {}).get("label")
                                if isinstance(it, dict)
                                else None
                            )
                            if not isinstance(p, str):
                                continue
                            try:
                                data = Path(p).read_bytes()
                                if len(data) > IMAGE_MAX_BYTES:
                                    continue
                                image_b64.append(base64.b64encode(data).decode("ascii"))
                                image_list_for_prompt.append(label or Path(p).name)
                            except Exception:
                                continue
                        if isinstance(cache, dict):
                            cache["b64"] = image_b64
                            cache["labels"] = image_list_for_prompt
            except Exception:
                pass

        for name in self.spec.outputs or []:
            if role == "critic":
                sample = "; ".join(
                    f"{k}: {str(v)[:60]}" for k, v in list(ctx_outputs.items())[:3]
                )
                rubric_text = "; ".join(critic_rubric[:4]) if critic_rubric else ""
                base_for_critic = ctx_outputs.get("summary") or seed_text
                base_clause = f" Base: {base_for_critic!r}." if base_for_critic else ""
                flags: list[str] = []
                if context.get("strict_grounding"):
                    flags.append("strict_grounding")
                if context.get("critic_structured"):
                    flags.append("structured")
                flag_clause = f" Flags: {', '.join(flags)}." if flags else ""
                user_prompt = (
                    f"Review outputs [{sample}] against rubric [{rubric_text}] and provide one-sentence notes."
                    f"{base_clause}{flag_clause}"
                )
            elif role == "editor":
                base = ctx_outputs.get("summary") or next(
                    iter(ctx_outputs.values()), ""
                )
                notes_val = ctx_outputs.get("critic_notes") or ""
                if isinstance(notes_val, dict):
                    notes = notes_val.get("notes", "")
                else:
                    notes = notes_val
                user_prompt = f"Rewrite for clarity/style based on notes: {notes!r}. Base text: {base!r}."
            else:
                # Seed-aware prompt for summary/context/audience_adapter
                seed_clause = f" Seed: {seed_text!r}." if seed_text else ""
                h_clause = (
                    f" Highlights: {', '.join(highlights)}." if highlights else ""
                )
                img_clause = (
                    f" Images: {', '.join(image_list_for_prompt)}."
                    if image_list_for_prompt
                    else ""
                )
                user_prompt = (
                    f"Role: {role}. Output: {name}. Style: {self.style or 'journalistic'}. "
                    f"Audiences: {', '.join(self.audience) or 'general'}."
                    f"{seed_clause}{h_clause}{img_clause} Write exactly one sentence grounded in the seed if present."
                )
            text: str
            outval: Any
            if hasattr(llm, "generate"):
                try:
                    text = llm.generate(
                        sys_prompt, user_prompt, images=image_b64 or None
                    )
                except Exception:
                    if role == "editor" and ctx_outputs:
                        text = f"Edited: {str(ctx_outputs.get('summary') or next(iter(ctx_outputs.values()), ''))[:80]}"
                    elif role == "critic":
                        text = (
                            "; ".join(critic_rubric[:2])
                            or "Review for clarity and citations"
                        )
                    else:
                        text = (
                            f"[{getattr(llm, 'name', 'mock')}] placeholder for {name}"
                        )
            else:
                if role == "editor" and ctx_outputs:
                    text = f"Edited: {str(ctx_outputs.get('summary') or next(iter(ctx_outputs.values()), ''))[:80]}"
                elif role == "critic":
                    text = (
                        "; ".join(critic_rubric[:2])
                        or "Review for clarity and citations"
                    )
                else:
                    text = f"placeholder output from {self.spec.id}"
            # Structured critic mode: wrap in a JSON object when requested
            if role == "critic" and (
                context.get("critic_structured") if isinstance(context, dict) else False
            ):
                outval = {"notes": text}
            else:
                outval = text
            outs[name] = outval
        return outs


class SwarmOrchestrator:
    def __init__(
        self,
        agents: Iterable[Agent],
        *,
        max_workers: int | None = None,
        max_rounds: int = 1,
    ) -> None:
        self.agents = list(agents)
        self.max_workers = max_workers
        self.max_rounds = max_rounds
        self.provenance: list[dict[str, Any]] = []
        self.errors: list[dict[str, Any]] = []
        self.failed_agents: list[str] = []

    def _auto_pool_size(self, n: int) -> int:
        env_cap = int(
            os.getenv("ZYRA_SWARM_MAX_WORKERS_CAP", str(DEFAULT_MAX_WORKERS))
            or DEFAULT_MAX_WORKERS
        )
        cores = os.cpu_count() or DEFAULT_MAX_WORKERS
        pool = max(1, min(n, cores, env_cap))
        return pool

    async def _run_agent_with_retries(
        self, a: Agent, context: dict[str, Any]
    ) -> dict[str, Any]:
        p = a.spec.params or {}
        max_retries = int(p.get("max_retries", 0) or 0)
        backoff_ms = int(p.get("backoff_ms", 50) or 0)
        backoff_factor = float(p.get("backoff_factor", 2.0) or 2.0)
        max_backoff_ms = int(p.get("max_backoff_ms", 500) or 500)

        attempt = 0
        while True:
            try:
                return await a.run(context)
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
        self, agents: list[Agent], context: dict[str, Any]
    ) -> dict[str, Any]:
        outputs: dict[str, Any] = {}
        pool_size = (
            self.max_workers
            if self.max_workers and self.max_workers > 0
            else self._auto_pool_size(len(agents))
        )
        sem = asyncio.Semaphore(pool_size)
        log = logging.getLogger("zyra.narrate.swarm")
        debug = (os.environ.get("ZYRA_VERBOSITY") or "").lower() == "debug"
        if debug:
            log.debug("[swarm] running %d agents (pool=%d)", len(agents), pool_size)

        async def run_one(a: Agent) -> dict[str, Any]:
            async with sem:
                t0 = time.perf_counter()
                started = datetime.now(timezone.utc).isoformat()
                # Agent start
                if debug:
                    log.debug("[agent %s] start", a.spec.id)
                try:
                    res = await self._run_agent_with_retries(a, context)
                except Exception as exc:  # pragma: no cover
                    self.errors.append(
                        {
                            "agent": a.spec.id,
                            "message": str(exc) or "agent failed",
                            "retried": int(
                                (a.spec.params or {}).get("max_retries", 0) or 0
                            ),
                        }
                    )
                    if a.spec.id not in self.failed_agents:
                        self.failed_agents.append(a.spec.id)
                    if debug:
                        log.warning("[agent %s] fail: %s", a.spec.id, exc)
                    res = {}
                dt_ms = int((time.perf_counter() - t0) * 1000)
                if dt_ms < 0:
                    dt_ms = 0
                # Conversational trace: show agent outputs (redacted) in debug mode
                if debug and isinstance(res, dict) and res:
                    try:
                        from zyra.utils.cli_helpers import (
                            sanitize_for_log,
                        )  # lazy import

                        for k, v in res.items():
                            s = v if isinstance(v, str) else str(v)
                            s = sanitize_for_log(s)
                            preview = s[:160] + ("…" if len(s) > 160 else "")
                            log.info(
                                "[agent %s:%s] -> %s: %s",
                                a.spec.id,
                                a.spec.role,
                                k,
                                preview,
                            )
                    except Exception:
                        # Never fail the run on logging/preview issues
                        pass
                # Derive a simple prompt reference path based on id/role
                if a.spec.prompt_ref:
                    ref = a.spec.prompt_ref
                else:
                    known_ids = {
                        "summary",
                        "context",
                        "critic",
                        "editor",
                        "audience_adapter",
                    }
                    base_name = (
                        a.spec.id
                        if a.spec.id in known_ids
                        else (a.spec.role or "specialist")
                    )
                    ref = f"zyra.assets/llm/prompts/narrate/{base_name}.md"
                self.provenance.append(
                    {
                        "agent": a.spec.id,
                        "model": getattr(a.llm or context.get("llm"), "model", None),
                        "started": started,
                        "prompt_ref": ref,
                        "duration_ms": dt_ms,
                    }
                )
                if debug:
                    log.debug("[agent %s] done in %d ms", a.spec.id, dt_ms)
                return res

        results = await asyncio.gather(*(run_one(a) for a in agents))
        for res in results:
            outputs.update(res)
        # Update context's outputs so subsequent rounds can see prior results
        try:
            if isinstance(context, dict):
                context.setdefault("outputs", {})
                context["outputs"].update(outputs)
        except Exception:
            pass
        return outputs

    async def _execute_dag(self, context: dict[str, Any]) -> dict[str, Any]:
        id_to_agent = {a.spec.id: a for a in self.agents}
        deps: dict[str, set[str]] = {
            aid: set(id_to_agent[aid].spec.depends_on or []) for aid in id_to_agent
        }
        remaining = set(id_to_agent.keys())
        outputs: dict[str, Any] = {}
        while remaining:
            ready_ids = [aid for aid in remaining if not deps.get(aid)]
            if not ready_ids:
                # cycle or unmet deps
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
                break
            ready = [id_to_agent[aid] for aid in ready_ids]
            outputs.update(await self._run_round(ready, context))
            # Remove completed nodes (that did not fail) and drop their deps
            for aid in ready_ids:
                remaining.discard(aid)
                if aid not in self.failed_agents:
                    for s in deps.values():
                        s.discard(aid)
        return outputs

    async def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        outputs: dict[str, Any] = {}
        if not self.agents:
            return outputs

        # If any dependencies are declared, prefer DAG execution (critic/editor
        # agents will be skipped when prerequisites fail). This aligns with tests
        # expecting unmet deps to block dependents.
        if any(a.spec.depends_on for a in self.agents):
            outputs.update(await self._execute_dag(context))
            return outputs

        review_agents = [a for a in self.agents if a.spec.role in {"critic", "editor"}]

        # Round 1: run all agents once
        outputs.update(await self._run_round(self.agents, context))

        # Subsequent rounds: run only critic/editor agents (rounds - 1 times)
        rounds = max(0, int(self.max_rounds or 0))
        extra = max(0, rounds - 1)
        for _ in range(extra):
            if not review_agents:
                break
            outputs.update(await self._run_round(review_agents, context))
        return outputs
