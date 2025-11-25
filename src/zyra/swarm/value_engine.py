# SPDX-License-Identifier: Apache-2.0
"""Augmentation helper that proposes low-cost additions for swarm plans."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from zyra.swarm.classifier import SemanticClassifier

try:  # pragma: no cover - optional
    from zyra.transform import _compute_frames_metadata
except Exception:  # pragma: no cover - optional
    _compute_frames_metadata = None


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

    tags = _classify_tags(intent, manifest.get("plan_summary"))
    frame_stats = _scan_frames_stats(manifest)
    candidates: list[dict[str, Any]] = []
    candidates.extend(_heuristic_suggestions(manifest, tags, frame_stats))
    candidates.extend(_bundle_suggestions(manifest, tags))
    candidates.extend(
        _llm_suggestions(
            manifest,
            intent=intent,
            plan_summary=manifest.get("plan_summary"),
            tags=tags,
        )
    )
    return list(_dedupe_by_stage(candidates).values())


def _heuristic_suggestions(
    manifest: dict[str, Any],
    tags: list[dict[str, Any]],
    frame_stats: dict[str, Any] | None,
) -> list[dict[str, Any]]:
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
                intent_text=_narrate_intent_text(tags),
            )
        )
    missing_template = _missing_frame_summary(frame_stats)
    if missing_template and not _has("verify"):
        suggestion = Suggestion(
            stage="verify",
            description=missing_template["description"],
            confidence=0.95,
            intent_text="Verify completeness when gaps or duplicates are detected in the frames metadata.",
        )
        suggestion["agent_template"] = missing_template["template"]
        suggestions.append(suggestion)
    elif any(
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
    manifest: dict[str, Any],
    intent: str | None,
    plan_summary: str | None,
    tags: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    if not intent:
        return []
    client = _load_llm_client()
    if client is None:
        return []
    system_prompt = (
        "You are a Zyra planning copilot. Suggest optional, user-facing workflow augmentations as a JSON array with fields "
        "stage, description, confidence, and (optionally) intent_text. Only propose steps that add analytical value, new "
        "visualizations, or richer downstream outputs. Do NOT suggest generic logging/retry toggles. Use only commands/stages "
        "from the provided capabilities catalog."
    )
    user_prompt = json.dumps(
        {
            "intent": intent,
            "agents": manifest.get("agents", []),
            "plan_summary": plan_summary,
            "context_tags": tags or [],
            "capabilities": _capability_hints(),
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


_CLASSIFIER = SemanticClassifier()
_NARRATE_INTENT_PROMPTS = {
    "drought_risk": "After rendering the drought-risk animation, summarize how drought intensity evolves and highlight the hardest hit regions.",
    "map_viz": "Describe the generated map/animation for downstream audiences, calling out what the visualization shows.",
    "time_series": "Summarize the temporal trends shown in the visualization for non-technical audiences.",
}

_BUNDLE_TEMPLATES: dict[str, list[dict[str, Any]]] = {
    "drought_risk": [
        {
            "stage": "process",
            "description": (
                "Insert an analysis stage that scans drought frames for hotspots, missing dates, and trend summaries."
            ),
            "intent_text": (
                "Compute drought coverage statistics (earliest/latest frame, regions with worsening risk) before narration."
            ),
            "confidence": 0.9,
        },
        {
            "stage": "verify",
            "description": (
                "Add a verification step that compares first/last frames to confirm drought risk changes are captured."
            ),
            "confidence": 0.75,
            "intent_text": (
                "Check that the drought animation includes the expected weekly coverage and no frames are missing."
            ),
        },
    ],
    "map_viz": [
        {
            "stage": "narrate",
            "description": (
                "Provide a narration describing what the map visualization reveals and why it matters."
            ),
            "confidence": 0.78,
            "intent_text": (
                "Explain the key takeaways from the generated map/animation for downstream audiences."
            ),
        }
    ],
}


def _classify_tags(
    intent: str | None, plan_summary: str | None
) -> list[dict[str, Any]]:
    try:
        return _CLASSIFIER.classify(intent or "", plan_summary)
    except Exception:
        return []


def _narrate_intent_text(tags: list[dict[str, Any]]) -> str:
    if not tags:
        return "After creating the visualization, generate a short narration summarizing the animation output."
    sorted_tags = sorted(
        tags, key=lambda entry: entry.get("confidence", 0.0), reverse=True
    )
    for entry in sorted_tags:
        tag = entry.get("tag")
        if not isinstance(tag, str):
            continue
        prompt = _NARRATE_INTENT_PROMPTS.get(tag.lower())
        if prompt:
            return prompt
    return "After creating the visualization, generate a short narration summarizing the animation output."


def _bundle_suggestions(
    manifest: dict[str, Any], tags: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    if not tags:
        return []
    stages_present = {
        str((agent or {}).get("stage", "")).lower()
        for agent in manifest.get("agents", [])
        if isinstance(agent, dict)
    }
    candidates: list[dict[str, Any]] = []
    sorted_tags = sorted(
        tags, key=lambda entry: entry.get("confidence", 0.0), reverse=True
    )
    for entry in sorted_tags:
        tag = entry.get("tag")
        if not isinstance(tag, str):
            continue
        templates = _BUNDLE_TEMPLATES.get(tag.lower()) or []
        for template in templates:
            stage = str(template.get("stage") or "").strip().lower()
            if not stage or stage in stages_present:
                continue
            desc = template.get("description")
            if not isinstance(desc, str) or not desc.strip():
                continue
            confidence = float(template.get("confidence", entry.get("confidence", 0.7)))
            intent_text = template.get("intent_text")
            candidates.append(
                Suggestion(
                    stage=stage,
                    description=desc,
                    confidence=max(0.0, min(confidence, 1.0)),
                    intent_text=intent_text,
                )
            )
    return candidates


def _capability_hints() -> list[dict[str, Any]]:
    try:
        from zyra.api.services import manifest as manifest_service

        raw_caps = manifest_service.get_manifest()
    except Exception:
        return []
    hints: list[dict[str, Any]] = []
    for full_cmd, meta in raw_caps.items():
        if not isinstance(full_cmd, str):
            continue
        parts = full_cmd.split()
        if len(parts) < 2:
            continue
        stage = parts[0]
        command = " ".join(parts[1:])
        desc = ""
        if isinstance(meta, dict):
            desc = str(meta.get("description") or "")
        hints.append({"stage": stage, "command": command, "description": desc})
    return hints


def _scan_frames_stats(manifest: dict[str, Any]) -> dict[str, Any] | None:
    if _compute_frames_metadata is None:
        return None
    agents = manifest.get("agents") or []
    for agent in agents:
        if not isinstance(agent, dict):
            continue
        stage = str(agent.get("stage") or "").lower()
        command = str(agent.get("command") or "").lower()
        if stage == "process" and command == "scan-frames":
            args = agent.get("args") or {}
            frames_dir = args.get("frames_dir")
            if not isinstance(frames_dir, str):
                continue
            try:
                return _compute_frames_metadata(
                    frames_dir,
                    pattern=args.get("pattern"),
                    datetime_format=args.get("datetime_format"),
                    period_seconds=args.get("period_seconds"),
                )
            except Exception:
                return None
    return None


def _missing_frame_summary(stats: dict[str, Any] | None) -> dict[str, Any] | None:
    if not stats:
        return None
    missing = stats.get("missing_count")
    duplicates = stats.get("analysis", {}).get("duplicate_timestamps")

    def _format_missing_desc(prefix: str, items: list[str]) -> str:
        if not items:
            return prefix
        sample = ", ".join(items[:3])
        return f"{prefix} (examples: {sample})"

    if missing and missing > 0:
        missing_list = []
        miss = stats.get("missing_timestamps")
        if isinstance(miss, list):
            missing_list = [str(x) for x in miss if isinstance(x, str)]
        description = _format_missing_desc(
            f"Add a verification stage to address {missing} missing frame(s) detected in the scan metadata.",
            missing_list,
        )
    elif isinstance(duplicates, list) and duplicates:
        description = "Add a verification stage to inspect duplicate frame timestamps detected during scanning."
    else:
        return None
    template = {
        "stage": "verify",
        "behavior": "cli",
        "command": "evaluate",
        "args": {"metric": "completeness"},
        "depends_on": ["scan_frames"],
    }
    return {"description": description, "template": template}
