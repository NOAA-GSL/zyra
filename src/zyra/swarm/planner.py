# SPDX-License-Identifier: Apache-2.0
"""Planner entrypoint: convert user intent into zyra swarm manifests."""

from __future__ import annotations

import argparse
import difflib
import json
import re
import shlex
import subprocess
import sys
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from typing import Any

from zyra.pipeline_runner import _stage_group_alias
from zyra.swarm import open_provenance_store, suggest_augmentations
from zyra.swarm.spec import StageAgentSpec

_STAGE_SEQUENCE = [
    "acquire",
    "process",
    "simulate",
    "decide",
    "visualize",
    "narrate",
    "verify",
    "decimate",
]

_STAGE_DESCRIPTIONS = {
    "acquire": "Import, ingest, or fetch source data (ftp/http/s3/etc.).",
    "process": "Transform, clean, or analyze intermediate datasets.",
    "simulate": "Run models or scenario simulations that generate new data.",
    "decide": "Score, optimize, or select the best outcome from processed data.",
    "visualize": "Render maps, plots, animations, or interactive views.",
    "narrate": "Summarize results, produce narratives, or explanatory text.",
    "verify": "Run QC/validation steps to ensure results meet expectations.",
    "decimate": "Export, deliver, or disseminate finished artifacts.",
}

_STAGE_SYNONYMS = {
    "acquire": {
        "import",
        "ingest",
        "download",
        "fetch",
        "sync",
        "search",
        "acquisition",
    },
    "process": {
        "transform",
        "processing",
        "image_processing",
        "data_processing",
        "prepare",
        "clean",
        "analysis",
        "scan",
    },
    "visualize": {
        "render",
        "plot",
        "compose",
        "video",
        "visualization",
        "map",
        "chart",
        "timeseries",
    },
    "decimate": {
        "export",
        "disseminate",
        "save",
        "egress",
        "publish",
        "deliver",
        "file_management",
    },
    "simulate": {"model", "forecast", "run"},
    "decide": {"optimize", "plan", "score", "decision"},
    "narrate": {"summarize", "describe", "narration", "report", "explain"},
    "verify": {"validate", "qc", "quality", "check", "diagnostics"},
}

_STAGE_OVERRIDES = {
    "search": "acquire",
    "run": "simulate",
}

_EXAMPLE_MANIFEST = {
    "intent": "Download remote imagery, fill gaps, render an animation, and save it locally.",
    "agents": [
        {
            "id": "fetch_frames",
            "stage": "acquire",
            "command": "ftp",
            "args": {
                "path": "ftp://example.org/data/frames",
                "sync_dir": "data/frames_raw",
                "pattern": "^Frame_[0-9]{8}\\.png$",
                "since_period": "P1Y",
            },
        },
        {
            "id": "scan_frames",
            "stage": "process",
            "command": "scan-frames",
            "depends_on": ["fetch_frames"],
            "args": {
                "frames_dir": "data/frames_raw",
                "pattern": "^Frame_[0-9]{8}\\.png$",
                "datetime_format": "%Y%m%d",
                "output": "data/frames_meta.json",
            },
        },
        {
            "id": "pad_missing",
            "stage": "process",
            "command": "pad-missing",
            "depends_on": ["scan_frames"],
            "args": {
                "frames_meta": "data/frames_meta.json",
                "output_dir": "data/frames_filled",
                "fill_mode": "basemap",
                "basemap": "earth_vegetation.jpg",
            },
        },
        {
            "id": "compose_animation",
            "stage": "visualize",
            "command": "compose-video",
            "depends_on": ["pad_missing"],
            "args": {
                "frames": "data/frames_filled",
                "output": "data/drought_animation.mp4",
                "fps": 4,
            },
        },
        {
            "id": "save_local",
            "stage": "decimate",
            "command": "local",
            "depends_on": ["compose_animation"],
            "args": {
                "input": "data/drought_animation.mp4",
                "path": "data/drought_animation.mp4",
            },
        },
    ],
}

_MAX_COMMANDS_PER_STAGE = 8
_PLACEHOLDER_PATTERNS = [
    r"example\.(org|com|net)",
    r"/tmp/",
    r"/path/to",
    r"\byour[_-]",
    r"\btbd\b",
    r"<[^>]+>",
    r"todo",
    r"replace me",
]

_ARG_RESOLVERS: list[dict[str, Any]] = []
_PLANNER_VERBOSE = False
_CURRENT_ANSWER_CACHE: dict[tuple[str, str, str], Any] | None = None
_SUGGESTION_TEMPLATES: dict[str, dict[str, Any]] = {
    "narrate": {
        "stage": "narrate",
        "command": "swarm",
        "depends_on_stage": ["visualize"],
        "args": {
            "preset": "kids_policy_basic",
            "pack": "narrative_summary.yaml",
        },
        "inherit": [
            {
                "target": "input",
                "source": "dependency",
                "keys": ["output", "path"],
            }
        ],
    },
    "verify": {
        "stage": "verify",
        "command": None,
    },
}

_COMMAND_RULES: dict[str, dict[str, Any]] = {
    "process pad-missing": {
        "confirm": ["fill_mode"],
        "requires": {
            "fill_mode": {},
            "basemap": {"when": {"fill_mode": "basemap"}},
        },
    }
}


def _looks_like_placeholder(value: Any) -> bool:
    if value in (None, ""):
        return True
    if not isinstance(value, str):
        return False
    text = value.strip().lower()
    if not text:
        return True
    return any(re.search(pattern, text) for pattern in _PLACEHOLDER_PATTERNS)


def _drop_placeholder_args(args: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key, value in args.items():
        if _looks_like_placeholder(value):
            continue
        clean[key] = value
    return clean


def _register_arg_resolver(stage: str, command: str, field: str):
    def decorator(func):
        _ARG_RESOLVERS.append(
            {"stage": stage, "command": command, "field": field, "handler": func}
        )
        return func

    return decorator


def _log_verbose(message: str) -> None:
    if _PLANNER_VERBOSE:
        print(message, file=sys.stderr)


def _print_listing_preview(
    listing: str, label: str = "listing preview", verbose_only: bool = False
) -> None:
    lines = [line for line in listing.splitlines() if line.strip()]
    if not lines:
        return
    if verbose_only and not _PLANNER_VERBOSE:
        print(
            f"  (re-run with --verbose to inspect {label})",
            file=sys.stderr,
        )
        return
    limit = 20 if _PLANNER_VERBOSE else 5
    limit = min(limit, len(lines))
    print(f"  {label} (first {limit} line(s)):", file=sys.stderr)
    for line in lines[:limit]:
        print(f"    {line}", file=sys.stderr)
    remaining = len(lines) - limit
    if remaining > 0:
        if _PLANNER_VERBOSE:
            print(f"    ... (+{remaining} more)", file=sys.stderr)
        else:
            print(
                f"    ... (+{remaining} more, use --verbose to show additional lines)",
                file=sys.stderr,
            )


def _resolver_fields_for_command(stage: str, command: str) -> set[str]:
    fields: set[str] = set()
    for resolver in _ARG_RESOLVERS:
        if resolver.get("stage") == stage and resolver.get("command") == command:
            fields.add(resolver.get("field"))
    return fields


class Planner:
    """Placeholder planner; future iterations will integrate LLM reasoning."""

    def __init__(self) -> None:
        self._rules: list[callable[[str], list[StageAgentSpec]]] = []
        self._llm = None
        self._caps: dict[str, dict[str, Any]] | None = None

    def register_rule(
        self, func: callable[[str], list[StageAgentSpec]]
    ) -> callable[[str], list[StageAgentSpec]]:
        self._rules.append(func)
        return func

    def plan(self, intent: str) -> dict[str, Any]:
        for rule in self._rules:
            specs = rule(intent)
            if specs:
                return {"intent": intent, "agents": [asdict(spec) for spec in specs]}
        specs = self._llm_plan(intent)
        if specs:
            return {"intent": intent, "agents": [asdict(spec) for spec in specs]}
        raise ValueError("planner: no rule matched the provided intent")

    def _llm_plan(self, intent: str) -> list[StageAgentSpec]:
        client = _load_llm_client()
        if client is None:
            return []
        caps = _load_capabilities()
        stage_commands = caps.get("stage_commands") or {}
        if not stage_commands:
            return []
        prompt_caps = caps.get("prompt") or {}
        manifest_hint = {
            "intent": intent,
            "catalog": prompt_caps,
            "manifest_schema": {
                "fields": ["id", "stage", "command", "depends_on", "args"],
                "stage_choices": prompt_caps.get("stage_order", _STAGE_SEQUENCE),
            },
        }
        system_prompt = (
            "You are the Zyra swarm planner. Generate a JSON object with an 'agents' array following the provided "
            "schema and catalog. Only use canonical stage names and command names from the catalog. Preserve logical "
            "stage ordering (acquire → process → simulate → decide → visualize → narrate → verify → decimate) and "
            "set depends_on to enforce data dependencies."
        )
        user_prompt = json.dumps(manifest_hint, indent=2, sort_keys=True)
        try:
            raw = client.generate(system_prompt, user_prompt)
        except Exception:
            return []
        data = _parse_llm_json(raw)
        specs: list[StageAgentSpec] = []
        entries = data if isinstance(data, list) else data.get("agents", [])
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            mapped = _map_to_capabilities(entry, caps)
            if mapped:
                try:
                    specs.append(StageAgentSpec.from_mapping(mapped))
                except Exception:
                    continue
        return specs


planner = Planner()


@planner.register_rule
def _mock_rule(intent: str) -> list[StageAgentSpec]:
    if "mock swarm" in intent.lower():
        return [
            StageAgentSpec(id="simulate", stage="simulate", outputs=["simulated"]),
            StageAgentSpec(
                id="narrate",
                stage="narrate",
                depends_on=["simulate"],
                outputs=["story"],
            ),
        ]
    return []


def register_cli(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument(
        "--intent",
        help="Free-form user request describing the desired workflow",
    )
    subparser.add_argument(
        "--intent-file",
        help="Read intent text from file (if not provided via --intent)",
    )
    subparser.add_argument(
        "--output",
        help="Write planned manifest to file ('-' for stdout)",
    )
    subparser.add_argument(
        "--guardrails",
        help="Optional Guardrails (.rail) schema to validate planner output",
    )
    subparser.add_argument(
        "--strict",
        action="store_true",
        help="Treat validation warnings as errors",
    )
    subparser.add_argument(
        "--memory",
        help="Optional provenance DB path to log planning events",
    )
    subparser.add_argument(
        "--verbose",
        action="store_true",
        help="Print additional planner debug output (resolver traces, listings)",
    )
    subparser.add_argument(
        "--no-clarify",
        action="store_true",
        help="Skip interactive prompts for missing planner arguments",
    )
    subparser.set_defaults(func=_cmd_plan)


def _cmd_plan(ns: argparse.Namespace) -> int:
    intent = ns.intent
    if not intent and ns.intent_file:
        intent = Path(ns.intent_file).read_text(encoding="utf-8")
    if not intent:
        print("--intent or --intent-file is required", file=sys.stderr)
        return 2
    global _PLANNER_VERBOSE
    _PLANNER_VERBOSE = bool(getattr(ns, "verbose", False))
    stripped_intent = intent.strip()
    intent_text = stripped_intent
    final_manifest: dict[str, Any] | None = None
    final_clarifications: list[str] = []
    final_suggestions: list[dict[str, Any]] = []
    accepted_history: list[dict[str, Any]] = []
    accepted_stages: set[str] = set()
    answer_cache: dict[tuple[str, str, str], Any] = {}
    global _CURRENT_ANSWER_CACHE
    pending_manifest: dict[str, Any] | None = None

    while True:
        if pending_manifest is not None:
            manifest = pending_manifest
            pending_manifest = None
        else:
            try:
                manifest = planner.plan(intent_text)
            except ValueError as exc:
                print(str(exc), file=sys.stderr)
                return 2

        _CURRENT_ANSWER_CACHE = answer_cache
        _apply_cached_answers(manifest, answer_cache)
        manifest = _maybe_prompt_for_followups(
            manifest, allow_prompt=not getattr(ns, "no_clarify", False)
        )
        manifest = _propagate_inferred_args(manifest)
        errors = _validate_manifest(manifest)
        if errors:
            for err in errors:
                print(f"planner validation: {err}", file=sys.stderr)
            if ns.strict:
                return 2

        if ns.guardrails:
            try:
                _run_guardrails(ns.guardrails, manifest)
            except Exception as exc:
                print(f"guardrails validation failed: {exc}", file=sys.stderr)
                if ns.strict:
                    return 2

        clarifications = _detect_clarifications(manifest)
        for msg in clarifications:
            print(f"clarification needed: {msg}", file=sys.stderr)

        suggestions = [
            s
            for s in suggest_augmentations(manifest, intent=intent_text)
            if s.get("stage") not in accepted_stages
        ]
        accepted = _prompt_accept_suggestions(
            suggestions,
            allow_prompt=not getattr(ns, "no_clarify", False),
        )
        if accepted:
            accepted_history.extend(accepted)
            accepted_stages.update(
                {str(s.get("stage") or "").lower() for s in accepted}
            )
            manifest = _apply_suggestion_templates(manifest, accepted)
            pending_manifest = manifest
            intent_text = _augment_intent(intent_text, accepted)
            continue

        final_manifest = manifest
        final_clarifications = clarifications
        final_suggestions = suggestions
        break

    _CURRENT_ANSWER_CACHE = None
    if final_manifest is None:
        return 2

    if ns.memory:
        store = open_provenance_store(ns.memory)
        hook = store.as_event_hook()
        hook(
            "plan_generated",
            {
                "intent": intent_text,
                "agent_count": len(final_manifest.get("agents", [])),
                "clarifications": final_clarifications,
                "suggestions": final_suggestions,
            },
        )
        store.close()
    final_manifest["suggestions"] = [
        s for s in final_suggestions if s.get("stage") not in accepted_stages
    ]
    if accepted_history:
        final_manifest["accepted_suggestions"] = accepted_history
    _strip_internal_fields(final_manifest)
    payload = json.dumps(final_manifest, indent=2, sort_keys=True)
    if ns.output and ns.output != "-":
        Path(ns.output).write_text(payload, encoding="utf-8")
    else:
        print(payload)
    return 0


def _validate_manifest(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    agents = manifest.get("agents") or []
    if not isinstance(agents, list):
        return ["manifest.agents must be a list"]
    seen_ids: set[str] = set()
    allowed_stages = {
        "import",
        "acquire",
        "process",
        "transform",
        "simulate",
        "decide",
        "visualize",
        "narrate",
        "verify",
        "export",
        "disseminate",
        "decimate",
    }
    for idx, raw in enumerate(agents):
        if not isinstance(raw, dict):
            errors.append(f"agents[{idx}] must be a mapping")
            continue
        try:
            StageAgentSpec.from_mapping(raw)
        except Exception as exc:  # pragma: no cover - validation detail
            errors.append(f"agents[{idx}]: {exc}")
        stage = str(raw.get("stage", "")).lower()
        if stage not in allowed_stages:
            errors.append(f"agents[{idx}]: unsupported stage '{stage}'")
        agent_id = str(raw.get("id", "")).strip()
        if not agent_id:
            errors.append(f"agents[{idx}]: missing id")
        elif agent_id in seen_ids:
            errors.append(f"duplicate agent id '{agent_id}'")
        else:
            seen_ids.add(agent_id)
    return errors


def _detect_clarifications(manifest: dict[str, Any]) -> list[str]:
    return _clarification_messages(_collect_arg_gaps(manifest))


def _clarification_messages(gaps: list[dict[str, Any]]) -> list[str]:
    messages: list[str] = []
    for gap in gaps:
        msg = str(gap.get("message") or "").strip()
        if msg:
            messages.append(msg)
    return messages


def _collect_arg_gaps(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    agents = manifest.get("agents") or []
    caps = _load_capabilities()
    stage_commands = caps.get("stage_commands") or {}
    for raw in agents:
        if not isinstance(raw, dict):
            continue
        stage = str(raw.get("stage") or "").strip()
        command = str(raw.get("command") or "").strip()
        args = raw.get("args") or {}
        if not isinstance(args, dict):
            continue
        agent_id = raw.get("id")
        flagged_fields: set[str] = set()
        basemap = args.get("basemap")
        if (
            isinstance(basemap, str)
            and basemap.strip()
            and not _basemap_exists(basemap)
        ):
            gaps.append(
                _gap_entry(
                    agent_ref=raw,
                    agent_id=agent_id,
                    stage=stage,
                    command=command,
                    field="basemap",
                    reason="basemap_missing",
                    message=f"Agent '{agent_id or stage}' requires basemap '{basemap}' which was not found",
                    current=basemap,
                )
            )
            flagged_fields.add("basemap")
        meta = stage_commands.get(stage, {}).get(command) if stage and command else None
        missing = _missing_required_args(args, meta)
        for name in missing:
            gaps.append(
                _gap_entry(
                    agent_ref=raw,
                    agent_id=agent_id,
                    stage=stage,
                    command=command,
                    field=name,
                    reason="missing_arg",
                    message=f"Agent '{agent_id or stage}' is missing required argument '{name}'",
                )
            )
            flagged_fields.add(name)
        placeholders = _placeholder_args(args)
        for name in placeholders:
            gaps.append(
                _gap_entry(
                    agent_ref=raw,
                    agent_id=agent_id,
                    stage=stage,
                    command=command,
                    field=name,
                    reason="placeholder",
                    message=f"Agent '{agent_id or stage}' has placeholder value for '{name}'",
                    current=args.get(name),
                )
            )
            flagged_fields.add(name)
        expected_fields = _resolver_fields_for_command(stage, command)
        for name in expected_fields:
            if name in flagged_fields:
                continue
            if not _arg_present(args, name):
                gaps.append(
                    _gap_entry(
                        agent_ref=raw,
                        agent_id=agent_id,
                        stage=stage,
                        command=command,
                        field=name,
                        reason="resolver_hint",
                        message=f"Agent '{agent_id or stage}' is missing recommended argument '{name}'",
                    )
                )
                flagged_fields.add(name)
        gaps.extend(_command_rule_gaps(stage, command, raw, args, agent_id))
    return gaps


def _gap_entry(
    *,
    agent_ref: dict[str, Any],
    agent_id: str | None,
    stage: str | None,
    command: str | None,
    field: str,
    reason: str,
    message: str,
    current: Any | None = None,
) -> dict[str, Any]:
    return {
        "agent_ref": agent_ref,
        "agent_id": agent_id,
        "stage": stage,
        "command": command,
        "field": field,
        "reason": reason,
        "message": message,
        "current": current,
    }


def _propagate_inferred_args(manifest: dict[str, Any]) -> dict[str, Any]:
    agents = manifest.get("agents")
    if not isinstance(agents, list):
        return manifest
    by_id: dict[str, dict[str, Any]] = {}
    for agent in agents:
        if isinstance(agent, dict) and agent.get("id"):
            by_id[str(agent["id"])] = agent
    for agent in agents:
        if not isinstance(agent, dict):
            continue
        stage = str(agent.get("stage") or "")
        command = str(agent.get("command") or "")
        args = agent.setdefault("args", {})
        if stage in {"process", "transform"} and command == "scan-frames":
            propagated = _copy_pattern_from_dependencies(agent, by_id)
            if propagated:
                current = args.get("pattern")
                if (
                    current is None
                    or _looks_like_placeholder(current)
                    or _is_example_pattern(current)
                ):
                    args["pattern"] = propagated
    return manifest


def _apply_suggestion_templates(
    manifest: dict[str, Any], suggestions: list[dict[str, Any]]
) -> dict[str, Any]:
    agents = manifest.setdefault("agents", [])
    for suggestion in suggestions:
        stage = str(suggestion.get("stage") or "").lower()
        template = _SUGGESTION_TEMPLATES.get(stage)
        if not template:
            continue
        new_agent = _build_agent_from_template(manifest, template, stage)
        if new_agent:
            agents.append(new_agent)
    return manifest


def _build_agent_from_template(
    manifest: dict[str, Any], template: dict[str, Any], fallback_stage: str
) -> dict[str, Any] | None:
    agents = manifest.setdefault("agents", [])
    stage = template.get("stage") or fallback_stage
    stage = str(stage or "").strip()
    if not stage:
        return None
    command = template.get("command")
    if command is not None:
        command = str(command).strip()
    new_agent: dict[str, Any] = {
        "id": template.get("id") or _next_agent_id(manifest, stage.replace(" ", "_")),
        "stage": stage,
        "command": command,
        "args": deepcopy(template.get("args") or {}),
        "depends_on": [],
        "metadata": {},
        "outputs": [],
        "parallel_ok": True,
        "params": {},
        "prompt_ref": None,
    }
    depends = list(template.get("depends_on") or [])
    dep_stages = template.get("depends_on_stage")
    if isinstance(dep_stages, str):
        dep_stages = [dep_stages]
    for dep_stage in dep_stages or []:
        dep_id = _find_last_agent_id_by_stage(agents, dep_stage)
        if dep_id:
            depends.append(dep_id)
    new_agent["depends_on"] = depends
    _inherit_template_args(new_agent, template, manifest)
    return new_agent


def _next_agent_id(manifest: dict[str, Any], base: str) -> str:
    agents = manifest.get("agents") or []
    existing = {str(agent.get("id")) for agent in agents if isinstance(agent, dict)}
    index = 1
    candidate = f"{base}_{index}"
    while candidate in existing:
        index += 1
        candidate = f"{base}_{index}"
    return candidate


def _find_last_agent_id_by_stage(agents: list[Any], stage_name: str) -> str | None:
    target = _stage_group_alias(stage_name)
    for agent in reversed(agents):
        if not isinstance(agent, dict):
            continue
        current = _stage_group_alias(str(agent.get("stage") or ""))
        if current == target and agent.get("id"):
            return str(agent.get("id"))
    return None


def _find_agent_by_id(manifest: dict[str, Any], agent_id: str) -> dict[str, Any] | None:
    for agent in manifest.get("agents") or []:
        if isinstance(agent, dict) and str(agent.get("id")) == agent_id:
            return agent
    return None


def _inherit_template_args(
    agent: dict[str, Any], template: dict[str, Any], manifest: dict[str, Any]
) -> None:
    inherit_rules = template.get("inherit") or []
    if not inherit_rules:
        return
    for rule in inherit_rules:
        target = rule.get("target")
        if not target:
            continue
        source = rule.get("source")
        if source == "dependency":
            keys = rule.get("keys") or []
            for dep_id in agent.get("depends_on") or []:
                dep_agent = _find_agent_by_id(manifest, dep_id)
                if not dep_agent:
                    continue
                dep_args = dep_agent.get("args") or {}
                for key in keys:
                    value = dep_args.get(key)
                    if value:
                        agent["args"][target] = value
                        break
                if agent["args"].get(target):
                    break


def _apply_cached_answers(
    manifest: dict[str, Any], cache: dict[tuple[str, str, str], Any]
) -> None:
    if not cache:
        return
    agents = manifest.get("agents")
    if not isinstance(agents, list):
        return
    for agent in agents:
        if not isinstance(agent, dict):
            continue
        stage = str(agent.get("stage") or "")
        command = str(agent.get("command") or "")
        args = agent.setdefault("args", {})
        for (c_stage, c_command, field), value in cache.items():
            if stage == c_stage and command == c_command:
                args[field] = value
                _mark_manual_field(agent, field)


def _command_rule_gaps(
    stage: str, command: str, agent: dict[str, Any], args: dict[str, Any], agent_id
) -> list[dict[str, Any]]:
    rule = _COMMAND_RULES.get(f"{stage} {command}")
    if not rule:
        return []
    gaps: list[dict[str, Any]] = []
    required = rule.get("requires") or {}
    for field, meta in required.items():
        condition = meta.get("when")
        if condition and not _rule_condition_met(args, condition):
            continue
        if not args.get(field):
            gaps.append(
                _gap_entry(
                    agent_ref=agent,
                    agent_id=agent_id,
                    stage=stage,
                    command=command,
                    field=field,
                    reason="missing_arg",
                    message=f"Agent '{agent_id or stage}' is missing required argument '{field}'.",
                )
            )
    confirm_fields = rule.get("confirm") or []
    for field in confirm_fields:
        if args.get(field) and not _field_is_manual(agent, field):
            gaps.append(
                _gap_entry(
                    agent_ref=agent,
                    agent_id=agent_id,
                    stage=stage,
                    command=command,
                    field=field,
                    reason="confirm_choice",
                    message=f"Agent '{agent_id or stage}' currently plans to use {field}='{args.get(field)}'. Enter a value to confirm or override.",
                    current=args.get(field),
                )
            )
    return gaps


def _rule_condition_met(args: dict[str, Any], condition: dict[str, str]) -> bool:
    return all(str(args.get(key)) == value for key, value in condition.items())


def _strip_internal_fields(manifest: dict[str, Any]) -> None:
    agents = manifest.get("agents")
    if not isinstance(agents, list):
        return
    for agent in agents:
        if not isinstance(agent, dict):
            continue
        agent.pop("_planner_manual_fields", None)


def _mark_manual_field(agent: dict[str, Any], field: str) -> None:
    if not field:
        return
    manual = agent.setdefault("_planner_manual_fields", [])
    if isinstance(manual, list) and field not in manual:
        manual.append(field)


def _field_is_manual(agent: dict[str, Any], field: str) -> bool:
    manual = agent.get("_planner_manual_fields")
    if not isinstance(manual, list):
        return False
    return field in manual


def _remember_answer(stage: str, command: str, field: str, value: Any) -> None:
    if not (stage and command and field):
        return
    if _CURRENT_ANSWER_CACHE is None:
        return
    _CURRENT_ANSWER_CACHE[(stage, command, field)] = value


def _copy_pattern_from_dependencies(
    agent: dict[str, Any], by_id: dict[str, dict[str, Any]]
) -> str | None:
    for dep in agent.get("depends_on") or []:
        source = by_id.get(dep)
        if not isinstance(source, dict):
            continue
        src_args = source.get("args") or {}
        pattern = src_args.get("pattern")
        if isinstance(pattern, str) and pattern.strip():
            return pattern
    return None


def _maybe_prompt_for_followups(
    manifest: dict[str, Any], allow_prompt: bool = True
) -> dict[str, Any]:
    if not allow_prompt or not sys.stdin.isatty() or not sys.stdout.isatty():
        return manifest
    skipped: set[tuple[Any, ...]] = set()
    _maybe_prompt_for_followups._printed_banner = False  # type: ignore[attr-defined]
    while True:
        gaps = _collect_arg_gaps(manifest)
        actionable = [
            gap
            for gap in gaps
            if gap.get("reason")
            in {"missing_arg", "placeholder", "resolver_hint", "confirm_choice"}
            and _gap_key(gap) not in skipped
        ]
        if not actionable:
            break
        resolved = False
        for gap in actionable:
            if _resolve_gap_via_tools(gap):
                resolved = True
        if resolved:
            continue
        gap = actionable[0]
        field = gap.get("field")
        agent_ref = gap.get("agent_ref")
        if not field or not isinstance(agent_ref, dict):
            skipped.add(_gap_key(gap))
            continue
        if not getattr(_maybe_prompt_for_followups, "_printed_banner", False):
            print(
                "Some planner inputs are missing or incomplete. Provide overrides or press Enter to skip.",
                file=sys.stderr,
            )
            _maybe_prompt_for_followups._printed_banner = True  # type: ignore[attr-defined]
        label = gap.get("agent_id") or gap.get("stage") or "agent"
        stage = gap.get("stage") or ""
        command = gap.get("command") or ""
        current = gap.get("current")
        suffix = f" (current: {current})" if current else ""
        help_text = _field_help_text(stage, command, field)
        if help_text:
            print(f"    hint: {help_text}", file=sys.stderr)
        prompt = f"[{label} — {stage} {command}] Provide value for '{field}'{suffix}: "
        try:
            response = input(prompt)
        except EOFError:  # pragma: no cover - depends on shell piping
            break
        value = response.strip()
        if not value:
            skipped.add(_gap_key(gap))
            continue
        args = agent_ref.setdefault("args", {})
        args[field] = value
        _mark_manual_field(agent_ref, field)
        _remember_answer(stage, command, field, value)
    return manifest


def _prompt_accept_suggestions(
    suggestions: list[dict[str, Any]], allow_prompt: bool
) -> list[dict[str, Any]]:
    actionable = [
        s for s in suggestions if isinstance(s, dict) and s.get("description")
    ]
    if (
        not allow_prompt
        or not actionable
        or not sys.stdin.isatty()
        or not sys.stdout.isatty()
    ):
        return []
    print(
        "\nPlanner suggestions (enter numbers to accept, press Enter to skip):",
        file=sys.stderr,
    )
    for idx, suggestion in enumerate(actionable, 1):
        stage = suggestion.get("stage") or ""
        desc = suggestion.get("description") or ""
        confidence = suggestion.get("confidence")
        conf_str = ""
        if isinstance(confidence, (int, float)):
            conf_str = f" (confidence {confidence:.2f})"
        print(f"  [{idx}] ({stage}) {desc}{conf_str}", file=sys.stderr)
    prompt = "Select suggestions to accept (comma-separated numbers, 'a' for all, Enter to skip): "
    try:
        response = input(prompt)
    except EOFError:  # pragma: no cover - depends on shell piping
        return []
    response = response.strip()
    if not response:
        return []
    if response.lower() in {"a", "all"}:
        return list(actionable)
    chosen: list[dict[str, Any]] = []
    seen_indexes: set[int] = set()
    for token in response.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            idx = int(token)
        except ValueError:
            continue
        if 1 <= idx <= len(actionable) and idx not in seen_indexes:
            chosen.append(actionable[idx - 1])
            seen_indexes.add(idx)
    return chosen


def _augment_intent(intent: str, suggestions: list[dict[str, Any]]) -> str:
    extras: list[str] = []
    for suggestion in suggestions:
        text = str(
            suggestion.get("intent_text") or suggestion.get("description") or ""
        ).strip()
        if text:
            extras.append(text)
    if not extras:
        return intent
    base = intent.rstrip()
    if base and base[-1] not in ".!?":
        base += "."
    addition = " ".join(extras)
    return f"{base} {addition}".strip()


def _gap_key(gap: dict[str, Any]) -> tuple[Any, ...]:
    return (
        gap.get("agent_id"),
        gap.get("stage"),
        gap.get("command"),
        gap.get("field"),
    )


def _resolve_gap_via_tools(gap: dict[str, Any]) -> bool:
    stage = gap.get("stage")
    command = gap.get("command")
    field = gap.get("field")
    if not stage or not command or not field:
        return False
    for resolver in _ARG_RESOLVERS:
        if (
            resolver.get("stage") == stage
            and resolver.get("command") == command
            and resolver.get("field") == field
        ):
            handler = resolver.get("handler")
            if not callable(handler):
                continue
            try:
                return bool(handler(gap))
            except Exception:
                return False
    return False


def _basemap_exists(ref: str) -> bool:
    path = Path(ref).expanduser()
    if path.exists():
        return True
    s = ref.strip()
    if not s:
        return False
    # pkg:package/resource
    if s.startswith("pkg:"):
        spec = s[4:]
        if ":" in spec and "/" not in spec:
            pkg, res = spec.split(":", 1)
        else:
            parts = spec.split("/", 1)
            pkg = parts[0]
            res = parts[1] if len(parts) > 1 else ""
        if not pkg or not res:
            return False
        return _package_resource_exists(pkg, res)
    # Bare filename under zyra.assets/images
    if "/" not in s and "\\" not in s:
        return _package_resource_exists("zyra.assets", f"images/{s}")
    if s.startswith("images/"):
        return _package_resource_exists("zyra.assets", s)
    return False


def _package_resource_exists(package: str, resource: str) -> bool:
    try:
        from importlib import resources as importlib_resources
    except Exception:  # pragma: no cover - fallback
        import importlib_resources  # type: ignore

    try:
        handle = importlib_resources.files(package).joinpath(resource)
        if getattr(handle, "is_file", None) and handle.is_file():  # type: ignore[attr-defined]
            return True
        with importlib_resources.as_file(handle) as candidate:
            return Path(candidate).exists()
    except Exception:
        return False


def _missing_required_args(
    args: dict[str, Any], meta: dict[str, Any] | None
) -> list[str]:
    if not meta:
        return []
    required: list[str] = []
    for pos in meta.get("positionals") or []:
        if isinstance(pos, dict) and pos.get("required") and pos.get("name"):
            required.append(str(pos["name"]))
    options = meta.get("options") or {}
    if isinstance(options, dict):
        for flag, info in options.items():
            if not isinstance(info, dict) or not info.get("required"):
                continue
            required.append(_option_to_dest(flag))
    missing: list[str] = []
    for name in required:
        if not _arg_present(args, name):
            missing.append(name)
    return missing


def _option_to_dest(flag: str) -> str:
    if not isinstance(flag, str):
        return ""
    stripped = flag.lstrip("-")
    return stripped.replace("-", "_")


def _arg_present(args: dict[str, Any], name: str) -> bool:
    if not name:
        return False
    keys = {
        name,
        name.replace("-", "_"),
        name.replace("_", "-"),
    }
    return any(key in args and args[key] not in (None, "", []) for key in keys)


def _placeholder_args(args: dict[str, Any]) -> list[str]:
    placeholders: list[str] = []
    for key, value in args.items():
        if _looks_like_placeholder(value):
            placeholders.append(str(key))
    return placeholders


def _is_example_pattern(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    normalized = value.strip().lower().replace("\\\\", "\\")
    defaults = {
        "^frame_[0-9]{8}\\.png$",
        "frame_[0-9]{8}\\.png",
    }
    return normalized in defaults


def _field_help_text(stage: str, command: str, field: str | None) -> str:
    if not field:
        return ""
    caps = _load_capabilities()
    meta = (
        caps.get("stage_commands", {}).get(stage, {}).get(command)
        if stage and command
        else None
    )
    if not meta:
        return ""
    for pos in meta.get("positionals") or []:
        if isinstance(pos, dict) and str(pos.get("name")) == field:
            return str(pos.get("help") or "")
    options = meta.get("options") or {}
    for flag, info in options.items():
        if not isinstance(info, dict):
            continue
        dest = _option_to_dest(flag)
        if dest == field:
            return str(info.get("help") or "")
    return ""


def _run_guardrails(schema_path: str, manifest: dict[str, Any]) -> None:
    try:
        from guardrails import Guard  # type: ignore
    except Exception as exc:  # pragma: no cover - guardrails optional
        raise RuntimeError(
            "guardrails library not installed; pip install guardrails-ai"
        ) from exc
    text = Path(schema_path).read_text(encoding="utf-8")
    guard = Guard.from_rail(text)  # type: ignore
    guard.parse(json.dumps(manifest, sort_keys=True))


def _load_llm_client():  # pragma: no cover - environment dependent
    if getattr(planner, "_llm", None) is not None:
        return planner._llm
    try:
        from zyra.wizard import _select_provider
    except Exception:
        planner._llm = None
        return None
    try:
        planner._llm = _select_provider(None, None)
    except Exception:
        planner._llm = None
    return planner._llm


def _load_capabilities() -> dict[str, Any]:
    if planner._caps is not None:
        return planner._caps
    try:
        from zyra.api.services import manifest as manifest_service

        raw_caps = manifest_service.get_manifest()
    except Exception:
        planner._caps = {
            "raw": {},
            "stage_commands": {},
            "stage_aliases": {},
            "command_aliases": {},
            "prompt": {},
        }
        return planner._caps

    stage_commands: dict[str, dict[str, Any]] = {}
    for full_cmd, meta in raw_caps.items():
        if not isinstance(full_cmd, str):
            continue
        parts = full_cmd.split()
        if len(parts) < 2:
            continue
        stage = _canonical_stage_name(parts[0])
        command = parts[1]
        if not stage or not command:
            continue
        stage_commands.setdefault(stage, {})[command] = meta or {}

    caps_payload = {
        "raw": raw_caps,
        "stage_commands": stage_commands,
        "stage_aliases": _build_stage_aliases(stage_commands),
        "command_aliases": _build_command_aliases(stage_commands),
        "prompt": _build_prompt_payload(stage_commands),
    }
    planner._caps = caps_payload
    return caps_payload


def _parse_llm_json(raw: str) -> Any:
    raw = (raw or "").strip()
    if not raw:
        return []
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("[")
        end = raw.rfind("]")
        if start >= 0 and end > start:
            try:
                return json.loads(raw[start : end + 1])
            except Exception:
                return []
    return []


def _map_to_capabilities(entry: dict[str, Any], caps: dict[str, Any]) -> dict[str, Any]:
    stage = _resolve_stage(entry.get("stage"), caps)
    if not stage:
        return {}
    command_info = _resolve_command(stage, entry.get("command"), caps)
    if not command_info:
        return {}
    args = _coerce_args(entry.get("args"), command_info["meta"])
    args = _drop_placeholder_args(args)
    args = _normalize_args_for_command(stage, command_info["name"], args)
    return {
        "id": entry.get("id") or command_info["name"],
        "stage": stage,
        "command": command_info["name"],
        "depends_on": entry.get("depends_on") or [],
        "args": args,
    }


def _coerce_args(args: Any, meta: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    positional = meta.get("positionals") or []
    if isinstance(args, dict):
        for key, val in args.items():
            result[key] = val
    if positional and "path" not in result and positional[0].get("name") == "path":
        result["path"] = (
            args.get("ftp_url") or args.get("path") if isinstance(args, dict) else None
        )
    return {k: v for k, v in result.items() if v not in (None, "")}


def _normalize_args_for_command(
    stage: str, command: str, args: dict[str, Any]
) -> dict[str, Any]:
    normalized = dict(args)
    if stage == "acquire" and command == "ftp" and "path" not in normalized:
        normalized.pop("pattern", None)
        normalized.pop("sync_dir", None)
    return normalized


def _canonical_stage_name(stage: str) -> str:
    canonical = _stage_group_alias(stage or "")
    canonical = _STAGE_OVERRIDES.get(canonical, canonical)
    return canonical


def _build_stage_aliases(stage_commands: dict[str, dict[str, Any]]) -> dict[str, str]:
    alias_map: dict[str, str] = {}
    for stage in stage_commands:
        norm = _normalize_alias(stage)
        if norm:
            alias_map[norm] = stage
    for stage, synonyms in _STAGE_SYNONYMS.items():
        norm = _normalize_alias(stage)
        if norm:
            alias_map.setdefault(norm, stage)
        for alias in synonyms:
            alias_norm = _normalize_alias(alias)
            if alias_norm:
                alias_map.setdefault(alias_norm, stage)
    return alias_map


def _build_command_aliases(
    stage_commands: dict[str, dict[str, Any]],
) -> dict[str, dict[str, str]]:
    alias_map: dict[str, dict[str, str]] = {}
    for stage, commands in stage_commands.items():
        per_stage: dict[str, str] = {}
        for command in commands:
            for alias in _command_aliases(stage, command):
                per_stage.setdefault(alias, command)
        alias_map[stage] = per_stage
    return alias_map


def _build_prompt_payload(stage_commands: dict[str, dict[str, Any]]) -> dict[str, Any]:
    ordered: list[str] = []
    for stage in _STAGE_SEQUENCE:
        if stage in stage_commands and stage not in ordered:
            ordered.append(stage)
    for stage in sorted(stage_commands.keys()):
        if stage not in ordered:
            ordered.append(stage)

    alias_listing: dict[str, list[str]] = {}
    for stage in ordered:
        alias_set = {stage}
        alias_set.update(_STAGE_SYNONYMS.get(stage, set()))
        alias_listing[stage] = sorted(alias_set)

    payload = {
        "stage_order": ordered,
        "stage_aliases": alias_listing,
        "example_manifest": _EXAMPLE_MANIFEST,
        "stages": [],
    }
    for stage in ordered:
        commands = stage_commands.get(stage, {})
        if not commands:
            continue
        entries: list[dict[str, str]] = []
        for cmd_name in sorted(commands.keys())[:_MAX_COMMANDS_PER_STAGE]:
            desc = str(commands[cmd_name].get("description") or "").strip()
            if len(desc) > 180:
                desc = desc[:177] + "..."
            entries.append({"name": cmd_name, "description": desc})
        payload["stages"].append(
            {
                "name": stage,
                "description": _STAGE_DESCRIPTIONS.get(stage, ""),
                "commands": entries,
            }
        )
    return payload


def _normalize_alias(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def _tokenize_alias(value: Any) -> list[str]:
    norm = _normalize_alias(value)
    if not norm:
        return []
    parts = [norm]
    for token in re.split(r"[_\-\s/]+", str(value or "").lower()):
        token_norm = _normalize_alias(token)
        if token_norm and token_norm not in parts:
            parts.append(token_norm)
    if norm.replace("_", "") and norm.replace("_", "") not in parts:
        parts.append(norm.replace("_", ""))
    return parts


def _resolve_stage(raw_stage: Any, caps: dict[str, Any]) -> str | None:
    alias_map = caps.get("stage_aliases") or {}
    for candidate in _tokenize_alias(raw_stage):
        stage = alias_map.get(candidate)
        if stage:
            return stage
    return None


def _resolve_command(
    stage: str, raw_command: Any, caps: dict[str, Any]
) -> dict[str, Any] | None:
    commands = (caps.get("stage_commands") or {}).get(stage, {})
    if not commands:
        return None
    alias_map = (caps.get("command_aliases") or {}).get(stage, {})
    tokens = _tokenize_alias(raw_command)
    for candidate in tokens:
        command = alias_map.get(candidate)
        if command and command in commands:
            return {"name": command, "meta": commands.get(command, {})}
    if tokens:
        keys = list(alias_map.keys())
        match = difflib.get_close_matches(tokens[0], keys, n=1, cutoff=0.74)
        if match:
            command = alias_map.get(match[0])
            if command and command in commands:
                return {"name": command, "meta": commands.get(command, {})}
    return None


def _command_aliases(stage: str, command: str) -> set[str]:
    aliases: set[str] = set()
    aliases.add(_normalize_alias(command))
    aliases.add(_normalize_alias(command.replace("-", "_")))
    aliases.add(_normalize_alias(command.replace("-", "")))
    aliases.add(_normalize_alias(f"{stage}_{command}"))
    aliases.add(_normalize_alias(f"{command}_{stage}"))
    tokens = re.split(r"[\s_\-]+", command)
    combined = "".join(tokens)
    aliases.add(_normalize_alias(combined))
    for token in tokens:
        aliases.add(_normalize_alias(token))
    return {alias for alias in aliases if alias}


@_register_arg_resolver(stage="acquire", command="ftp", field="pattern")
def _resolve_ftp_pattern_from_listing(gap: dict[str, Any]) -> bool:
    agent_ref = gap.get("agent_ref")
    if not isinstance(agent_ref, dict):
        return False
    args = agent_ref.setdefault("args", {})
    path = args.get("path")
    if not isinstance(path, str) or _looks_like_placeholder(path):
        return False
    print(
        "planner: sampling FTP listing to infer pattern...",
        file=sys.stderr,
    )
    ok, listing, err = _list_remote_entries("acquire", "ftp", path, args)
    if not ok:
        print(
            f"planner: unable to list '{path}' via zyra acquire ftp --list ({err})",
            file=sys.stderr,
        )
        if listing.strip():
            _print_listing_preview(listing, "FTP listing output", verbose_only=True)
        print(
            "  Provide the --pattern regex manually or rerun 'zyra acquire ftp --list' to debug.",
            file=sys.stderr,
        )
        return False
    samples = _extract_file_candidates(listing)
    if not samples:
        print(
            "planner: FTP listing did not contain obvious filenames; unable to infer pattern.",
            file=sys.stderr,
        )
        _print_listing_preview(listing, "FTP listing preview", verbose_only=True)
        return False
    pattern = _derive_pattern_from_samples(samples)
    if not pattern:
        pattern = _infer_pattern_via_llm(samples)
    if not pattern:
        print(
            "planner: could not infer a regex from the listing. Sample filenames:",
            file=sys.stderr,
        )
        for sample in samples[:5]:
            print(f"    - {sample}", file=sys.stderr)
        print(
            "  Please enter a regex pattern (e.g., '^Frame_[0-9]{8}\\.png$').",
            file=sys.stderr,
        )
        return False
    args["pattern"] = pattern
    _remember_answer("acquire", "ftp", "pattern", pattern)
    _log_verbose(f"planner: inferred pattern '{pattern}' from FTP listing")
    _print_listing_preview(listing, "FTP listing preview")
    return True


def _list_remote_entries(
    stage: str,
    command: str,
    path: str,
    args: dict[str, Any],
    *,
    include_filters: bool = False,
) -> tuple[bool, str, str]:
    cmd = ["zyra", stage, command, path, "--list", "--quiet"]
    if include_filters:
        passthrough = {
            "since": "--since",
            "since_period": "--since-period",
            "date_format": "--date-format",
        }
        for key, flag in passthrough.items():
            if args.get(key):
                cmd.extend([flag, str(args[key])])
    if _PLANNER_VERBOSE:
        printed = " ".join(shlex.quote(part) for part in cmd)
        _log_verbose(f"planner verbose: running {printed}")
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return False, "", "zyra CLI not found in PATH"
    if proc.returncode != 0:
        err = proc.stderr.strip() or f"exit status {proc.returncode}"
        return False, proc.stdout, err
    return True, proc.stdout, proc.stderr


def _extract_file_candidates(listing: str) -> list[str]:
    candidates: list[str] = []
    token_re = re.compile(r"[A-Za-z0-9_.\-/]+")
    for line in listing.splitlines():
        line = line.strip()
        if not line:
            continue
        matches = token_re.findall(line)
        for token in reversed(matches):
            if "." in token and not token.endswith("."):
                candidates.append(token.split("/")[-1])
                break
        else:
            if matches:
                candidates.append(matches[-1])
    return candidates[:20]


def _derive_pattern_from_samples(samples: list[str]) -> str | None:
    if not samples:
        return None
    names = [Path(sample).name for sample in samples if sample]
    if not names:
        return None
    pattern = _pattern_from_filename(names[0])
    if not pattern:
        return None
    try:
        regex = re.compile(pattern)
    except re.error:
        return None
    if all(regex.match(name) for name in names[:5]):
        return pattern
    return None


def _pattern_from_filename(name: str) -> str:
    buf: list[str] = []
    run = 0
    for ch in name:
        if ch.isdigit():
            run += 1
            continue
        if run:
            buf.append(rf"[0-9]{{{run}}}")
            run = 0
        if ch.isalnum():
            buf.append(ch)
        else:
            buf.append("\\" + ch)
    if run:
        buf.append(rf"[0-9]{{{run}}}")
    return "^" + "".join(buf) + "$"


def _infer_pattern_via_llm(samples: list[str]) -> str | None:
    client = _load_llm_client()
    if client is None:
        return None
    system_prompt = (
        "You are helping determine a regex file-matching pattern for Zyra CLI workflows. "
        "Given a list of filenames, respond with just the regex pattern that matches them."
    )
    user_prompt = json.dumps({"filenames": samples[:20]}, indent=2)
    try:
        raw = client.generate(system_prompt, user_prompt)
    except Exception:
        return None
    if not raw:
        return None
    pattern = raw.strip().splitlines()[0]
    try:
        re.compile(pattern)
    except re.error:
        return None
    return pattern
