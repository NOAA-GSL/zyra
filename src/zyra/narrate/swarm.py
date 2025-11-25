# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from zyra.swarm import SwarmOrchestrator as _BaseSwarmOrchestrator

SwarmOrchestrator = _BaseSwarmOrchestrator

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

        frames_context = _summarize_frames_context(idata)
        verify_context = _summarize_verify_context(idata)

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
                frames_clause = f" Frames: {frames_context}." if frames_context else ""
                verify_clause = (
                    f" Verification: {verify_context}." if verify_context else ""
                )
                user_prompt = (
                    f"Role: {role}. Output: {name}. Style: {self.style or 'journalistic'}. "
                    f"Audiences: {', '.join(self.audience) or 'general'}."
                    f"{seed_clause}{h_clause}{img_clause}{frames_clause}{verify_clause}"
                    " Write exactly one sentence grounded in the seed if present."
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


def _summarize_frames_context(input_data: Any) -> str:
    if not isinstance(input_data, dict):
        return ""
    meta = input_data.get("frames_metadata")
    if not isinstance(meta, dict):
        raw_meta = input_data.get("metadata")
        meta = raw_meta if isinstance(raw_meta, dict) else None
    analysis = input_data.get("frames_analysis")
    if not isinstance(analysis, dict) and isinstance(meta, dict):
        raw_analysis = meta.get("analysis")
        analysis = raw_analysis if isinstance(raw_analysis, dict) else None
    parts: list[str] = []
    start = meta.get("start_datetime") if isinstance(meta, dict) else None
    end = meta.get("end_datetime") if isinstance(meta, dict) else None
    count = meta.get("frame_count_actual") if isinstance(meta, dict) else None
    missing = meta.get("missing_count") if isinstance(meta, dict) else None
    missing_list: list[str] = []
    if isinstance(meta, dict):
        miss = meta.get("missing_timestamps")
        if isinstance(miss, list):
            missing_list = [str(x) for x in miss if isinstance(x, str)]
    if count is not None:
        parts.append(f"{count} frames")
    if start and end:
        parts.append(f"{start} → {end}")
    if isinstance(analysis, dict):
        span = analysis.get("span_seconds")
        if isinstance(span, (int, float)) and span > 0:
            parts.append(_format_human_span(int(span)))
        missing_detail = analysis.get("missing_timestamps")
        if isinstance(missing_detail, list):
            missing_list = missing_list or [
                str(x) for x in missing_detail if isinstance(x, str)
            ]
            if missing is None:
                missing = len(missing_detail)
        samples = analysis.get("sample_frames")
        if isinstance(samples, list) and samples:
            labels: list[str] = []
            for entry in samples[:3]:
                label = entry.get("label") if isinstance(entry, dict) else None
                path = entry.get("path") if isinstance(entry, dict) else None
                if isinstance(label, str) and label:
                    labels.append(label)
                elif isinstance(path, str) and path:
                    labels.append(Path(path).stem)
            if labels:
                parts.append(f"samples {', '.join(labels)}")
    if missing and missing > 0:
        snippet = f"missing {missing}"
        if missing_list:
            snippet += f" (examples: {', '.join(missing_list[:3])})"
        parts.append(snippet)
    elif missing == 0:
        parts.append("no missing frames")
    return "; ".join(parts)


def _format_human_span(seconds: int) -> str:
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if sec and not parts:
        parts.append(f"{sec}s")
    return "span " + "".join(parts)


def _summarize_verify_context(input_data: Any) -> str:
    if not isinstance(input_data, dict):
        return ""
    verify = input_data.get("verify_results")
    if not isinstance(verify, list):
        meta = input_data.get("metadata")
        if isinstance(meta, dict):
            verify = meta.get("verify_results")
    if not isinstance(verify, list):
        return ""
    summaries: list[str] = []
    for entry in verify:
        if not isinstance(entry, dict):
            continue
        message = entry.get("message") or entry.get("text")
        verdict = entry.get("verdict")
        metric = entry.get("metric")
        snippet_parts = []
        if isinstance(metric, str) and metric:
            snippet_parts.append(metric)
        if isinstance(verdict, str) and verdict:
            snippet_parts.append(verdict)
        snippet = " ".join(snippet_parts).strip()
        detail = _clean_verify_message(message) if message else ""
        if snippet and detail:
            summaries.append(f"{snippet}: {detail}")
        elif snippet:
            summaries.append(snippet)
        elif detail:
            summaries.append(detail)
        if len(summaries) >= 2:
            break
    return "; ".join(summaries)


def _clean_verify_message(message: Any) -> str:
    text = str(message or "").strip()
    if not text:
        return ""
    lower = text.lower()
    if lower.startswith("verify "):
        idx = text.find(":")
        if idx != -1:
            text = text[idx + 1 :].strip()
    return text
