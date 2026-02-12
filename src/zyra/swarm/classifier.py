# SPDX-License-Identifier: Apache-2.0
"""Semantic intent classifier used by the planner/value engine."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable

_DEFAULT_TAG_CATALOG: list[dict[str, Any]] = [
    {
        "tag": "drought_risk",
        "description": "Weekly drought risk imagery, risk maps, drought outlooks",
        "keywords": ["drought", "risk", "weekly", "noaa"],
    },
    {
        "tag": "map_viz",
        "description": "General geospatial or map-based visualization",
        "keywords": ["map", "frame", "visualize", "animation"],
    },
    {
        "tag": "time_series",
        "description": "Temporal metrics, trends, or time-series plots",
        "keywords": ["time", "series", "trend", "weekly"],
    },
    {
        "tag": "research",
        "description": "Need textual research, summaries, or policy context",
        "keywords": ["policy", "research", "report", "explain"],
    },
    {
        "tag": "generic",
        "description": "No strong semantic match",
        "keywords": [],
    },
]


@dataclass
class SemanticClassifier:
    """LLM-backed helper that maps intent text to semantic tags."""

    client: Any | None = None
    tag_catalog: Iterable[dict[str, Any]] | None = None

    def classify(
        self, intent: str | None, plan_summary: str | None = None
    ) -> list[dict[str, Any]]:
        text = " ".join(part for part in (intent or "", plan_summary or "") if part)
        if not text.strip():
            return [{"tag": "generic", "confidence": 0.2}]
        catalog = list(self.tag_catalog or _DEFAULT_TAG_CATALOG)
        client = self.client if self.client is not None else _load_llm_client()
        if client is not None:
            payload = {
                "intent": intent,
                "plan_summary": plan_summary,
                "tag_catalog": [
                    {"tag": entry["tag"], "description": entry.get("description", "")}
                    for entry in catalog
                ],
            }
            system_prompt = (
                "You are the Zyra workflow classifier. Return JSON with a 'context_tags' array,"
                " each entry having fields tag and confidence (0-1). Only use tags from the catalog."
                " If unsure, return generic with low confidence."
            )
            try:
                raw = client.generate(
                    system_prompt, json.dumps(payload, indent=2, sort_keys=True)
                )
            except Exception:
                raw = None
            tags = self._parse_response(raw)
            if tags:
                return tags
        return self._fallback_classify(text, catalog)

    def _parse_response(self, raw: str | None) -> list[dict[str, Any]]:
        if not raw:
            return []
        raw = raw.strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []
        entries = data.get("context_tags") if isinstance(data, dict) else None
        if not isinstance(entries, list):
            return []
        normalized: list[dict[str, Any]] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            tag = str(entry.get("tag") or "").strip().lower()
            if not tag:
                continue
            try:
                conf = float(entry.get("confidence", 0))
            except (TypeError, ValueError):
                conf = 0.0
            normalized.append({"tag": tag, "confidence": max(0.0, min(conf, 1.0))})
        return normalized

    def _fallback_classify(
        self, text: str, catalog: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        lowered = text.lower()
        scored: list[tuple[str, float]] = []
        for entry in catalog:
            tag = entry.get("tag")
            if not tag:
                continue
            keywords = [
                str(word).lower()
                for word in entry.get("keywords", [])
                if isinstance(word, str)
            ]
            if not keywords:
                continue
            score = 0
            for word in keywords:
                if word and word in lowered:
                    score += 1
            if score:
                scored.append((tag, float(score) / len(keywords)))
        if not scored:
            return [{"tag": "generic", "confidence": 0.2}]
        scored.sort(key=lambda item: item[1], reverse=True)
        top = [{"tag": tag, "confidence": min(score, 1.0)} for tag, score in scored[:3]]
        return top


def _load_llm_client():  # pragma: no cover - environment dependent
    try:
        from zyra.wizard import _select_provider
    except Exception:
        return None
    try:
        return _select_provider(None, None)
    except Exception:
        return None


__all__ = ["SemanticClassifier", "_DEFAULT_TAG_CATALOG"]
