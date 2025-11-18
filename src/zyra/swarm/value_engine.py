# SPDX-License-Identifier: Apache-2.0
"""Augmentation helper that proposes low-cost additions for swarm plans."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass
class Suggestion(dict):
    """Small structure describing a potential augmentation."""

    stage: str
    description: str
    confidence: float
    intent_text: str | None = None

    def __post_init__(self) -> None:  # pragma: no cover - trivial guard
        dict.__init__(
            self,
            stage=self.stage,
            description=self.description,
            confidence=self.confidence,
            intent_text=self.intent_text,
        )


def suggest(
    manifest: dict[str, Any], intent: str | None = None
) -> list[dict[str, Any]]:
    """Return combined heuristic + LLM suggestions (deduped by stage)."""

    candidates: list[dict[str, Any]] = []
    candidates.extend(_heuristic_suggestions(manifest))
    candidates.extend(_llm_suggestions(manifest, intent=intent))
    return list(_dedupe_by_stage(candidates).values())


def _heuristic_suggestions(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    agents = manifest.get("agents") or []
    stages = {
        str((raw or {}).get("stage", "")).lower()
        for raw in agents
        if isinstance(raw, dict)
    }
    suggestions: list[dict[str, Any]] = []

    def _has(name: str) -> bool:
        return name in stages

    if any(stage in stages for stage in {"visualize", "render"}) and not _has(
        "narrate"
    ):
        suggestions.append(
            Suggestion(
                stage="narrate",
                description="Add a `narrate summary` stage after visualization to describe the animation output for downstream users.",
                confidence=0.88,
                intent_text="After creating the visualization, generate a short narration summarizing the animation output.",
            )
        )
    if any(
        stage in stages for stage in {"import", "acquire", "process", "transform"}
    ) and not _has("verify"):
        suggestions.append(
            Suggestion(
                stage="verify",
                description="Insert a verification stage after processing to confirm data completeness/quality before export.",
                confidence=0.82,
                intent_text="Add a verification step to ensure the downloaded and processed frames are complete before export.",
            )
        )
    return suggestions


def _llm_suggestions(
    manifest: dict[str, Any], intent: str | None
) -> list[dict[str, Any]]:
    if not intent:
        return []
    client = _load_llm_client()
    if client is None:
        return []
    system_prompt = (
        "You are a planning assistant for Zyra. Given a user's intent and a JSON manifest of stage agents, "
        "suggest optional low-cost augmentations as a JSON array of objects with fields stage, description, confidence."
    )
    user_prompt = json.dumps(
        {
            "intent": intent,
            "agents": manifest.get("agents", []),
        },
        indent=2,
        sort_keys=True,
    )
    try:
        raw = client.generate(system_prompt, user_prompt)
    except Exception:
        return []
    return _parse_suggestion_reply(raw)


def _load_llm_client():  # pragma: no cover - environment dependent
    try:
        from zyra.wizard import _select_provider
    except Exception:
        return None
    try:
        return _select_provider(None, None)
    except Exception:
        return None


def _parse_suggestion_reply(raw: str) -> list[dict[str, Any]]:
    if not raw:
        return []
    raw = raw.strip()
    try:
        data = json.loads(raw)
        return _coerce_suggestions(data)
    except json.JSONDecodeError:
        # attempt to salvage JSON array within text
        start = raw.find("[")
        end = raw.rfind("]")
        if start >= 0 and end > start:
            try:
                data = json.loads(raw[start : end + 1])
                return _coerce_suggestions(data)
            except Exception:
                return []
    return []


def _coerce_suggestions(obj: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not isinstance(obj, list):
        return out
    for item in obj:
        if not isinstance(item, dict):
            continue
        stage = str(item.get("stage") or "").strip().lower()
        desc = str(item.get("description") or "").strip()
        try:
            conf = float(item.get("confidence", 0))
        except (ValueError, TypeError):
            conf = 0.5
        intent_text = (
            str(item.get("intent_text") or item.get("intent") or "").strip() or None
        )
        if stage and desc:
            out.append(
                Suggestion(
                    stage=stage,
                    description=desc,
                    confidence=conf,
                    intent_text=intent_text,
                )
            )
    return out


def _dedupe_by_stage(suggestions: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for sug in suggestions:
        stage = str(sug.get("stage", "")).strip().lower()
        if not stage:
            continue
        existing = deduped.get(stage)
        if not existing or sug.get("confidence", 0) >= existing.get("confidence", 0):
            deduped[stage] = sug
    return deduped
