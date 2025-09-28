# SPDX-License-Identifier: Apache-2.0
"""Narration/reporting stage CLI.

Keeps a minimal ``describe`` command for back-compat and adds a new
``swarm`` command that accepts presets/config flags (plan-aligned).
"""

from __future__ import annotations

import argparse
import asyncio
import difflib
import json
import os
import sys
from contextlib import suppress
from datetime import datetime
from functools import lru_cache
from importlib import resources as ir
from typing import Any

from zyra.narrate.schemas import NarrativePack
from zyra.narrate.swarm import Agent, AgentSpec, SwarmOrchestrator
from zyra.wizard import _select_provider as _wiz_select_provider


def _cmd_describe(ns: argparse.Namespace) -> int:
    """Placeholder narrate/report command."""
    topic = ns.topic or "run"
    print(f"narrate describe: topic={topic} (skeleton)")
    return 0


def register_cli(subparsers: argparse._SubParsersAction) -> None:
    """Register narrate-stage commands on a subparsers action."""
    # Legacy/simple describe
    p = subparsers.add_parser(
        "describe", help="Produce a placeholder narrative/report (skeleton)"
    )
    p.add_argument("--topic", help="Topic to narrate (placeholder)")
    p.set_defaults(func=_cmd_describe)

    # New: swarm orchestrator (skeleton)
    ps = subparsers.add_parser(
        "swarm",
        help="Narrate with a simple multi-agent swarm",
        description=(
            "Run a lightweight narration swarm with presets and YAML merging. "
            "When audiences are provided, an internal audience_adapter agent emits "
            "<aud>_version outputs. Provenance is recorded per agent with started/model/"
            "prompt_ref/duration_ms and included in the Narrative Pack."
        ),
    )
    _add_swarm_flags(ps)
    ps.set_defaults(func=_cmd_swarm)


def _add_swarm_flags(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "-P",
        "--preset",
        help="Preset template name (use '-P help' to list presets)",
    )
    p.add_argument(
        "--list-presets",
        action="store_true",
        help="List available presets and exit",
    )
    p.add_argument("--swarm-config", help="YAML config with agents/graph/settings")
    p.add_argument("--agents", help="Comma-separated agent IDs (e.g., summary,critic)")
    p.add_argument("--audiences", help="Comma-separated audiences (e.g., kids,policy)")
    p.add_argument("--style", help="Target writing style (e.g., journalistic)")
    p.add_argument("--provider", help="LLM provider (mock|openai|ollama)")
    p.add_argument("--model", help="Model name (provider-specific)")
    p.add_argument("--base-url", dest="base_url", help="Provider base URL override")
    p.add_argument("--max-workers", type=int, help="Max concurrent agents (optional)")
    p.add_argument(
        "--max-rounds",
        type=int,
        default=None,
        help="Review rounds (0 disables critic/editor loop)",
    )
    p.add_argument(
        "--pack",
        help="Output file for Narrative Pack (yaml or json); '-' for stdout",
    )
    p.add_argument(
        "--rubric",
        help="Path to critic rubric YAML (defaults to packaged critic rubric)",
    )
    p.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose logging (shows per-agent dialog)",
    )
    p.add_argument(
        "--quiet",
        action="store_true",
        help="Quiet logging (errors only)",
    )
    p.add_argument(
        "--input",
        help="Optional input file path or '-' for stdin (JSON/YAML autodetect; falls back to text)",
    )
    p.add_argument(
        "--critic-structured",
        action="store_true",
        help="Emit structured critic output (critic_notes as {notes: ...})",
    )
    p.add_argument(
        "--attach-images",
        action="store_true",
        help="Attach images from input_data.images to LLM calls (multimodal models only)",
    )
    p.add_argument(
        "--strict-grounding",
        action="store_true",
        help="Fail the run if critic flags ungrounded content",
    )
    p.epilog = (
        "Provenance fields: agent, model, started (RFC3339), prompt_ref, duration_ms. "
        "Use '-P help' to list presets. Unknown preset exits 2 with suggestions."
    )


@lru_cache(maxsize=1)
def _list_presets() -> list[str]:
    # Discover packaged presets under zyra.assets/llm/presets/narrate. Cache once
    # per process so repeated --list-presets invocations avoid repeated I/O.
    names: list[str] = []
    try:
        base = ir.files("zyra.assets").joinpath("llm/presets/narrate")
        if base.is_dir():
            for entry in base.iterdir():
                if entry.name.endswith((".yaml", ".yml")):
                    names.append(entry.name.rsplit(".", 1)[0])
    except Exception:
        pass
    return sorted(set(names))


def _cmd_swarm(ns: argparse.Namespace) -> int:
    # Configure logging per verbosity flags
    try:
        import os as _os

        from zyra.utils.cli_helpers import configure_logging_from_env as _cfg_log

        if getattr(ns, "verbose", False):
            _os.environ["ZYRA_VERBOSITY"] = "debug"
        elif getattr(ns, "quiet", False):
            _os.environ["ZYRA_VERBOSITY"] = "quiet"
        _cfg_log()
    except Exception:
        pass
    # Handle preset listing/alias behavior first
    if ns.list_presets or (ns.preset and ns.preset in {"help", "?"}):
        names = _list_presets()
        print("\n".join(names))
        return 0

    # Unknown preset: suggest matches and exit 2
    if ns.preset:
        names = _list_presets()
        if ns.preset not in names:
            sugg = difflib.get_close_matches(ns.preset, names, n=3)
            msg = f"unknown preset: {ns.preset}"
            if sugg:
                msg += f"; did you mean: {', '.join(sugg)}?"
            print(msg, file=sys.stderr)
            return 2

    # Resolve configuration from preset → file → CLI overrides
    try:
        resolved = _resolve_swarm_config(ns)
    except Exception as e:
        print(str(e), file=sys.stderr)
        return 2
    # Skeleton execution using the orchestrator for agent outputs
    try:
        pack = _build_pack_with_orchestrator(resolved)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    # Validate before writing; map validation errors to exit 2
    try:
        pack = NarrativePack.model_validate(pack)
    except Exception as e:  # pydantic.ValidationError
        # Print actionable error with field locations when available
        try:
            from pydantic import ValidationError

            if isinstance(e, ValidationError):
                for err in e.errors():
                    loc = ".".join(str(x) for x in err.get("loc", []))
                    msg = err.get("msg", "validation error")
                    print(f"{loc}: {msg}", file=sys.stderr)
                return 2
        except Exception:
            pass
        print(str(e), file=sys.stderr)
        return 2

    # Runtime validation (RFC3339 timestamps, monotonic per agent, failed_agents subset)
    try:
        _runtime_validate_pack_dict(pack.model_dump())
    except ValueError as ve:
        print(str(ve), file=sys.stderr)
        return 2

    if resolved.get("pack"):
        _write_pack(resolved["pack"], pack.model_dump(exclude_none=True))
    else:
        print("narrate swarm: completed (skeleton)")
    return 0 if pack.status.completed else 1


def _build_pack_with_orchestrator(cfg: dict[str, Any]) -> dict[str, Any]:
    agents_cfg = cfg.get("agents") or ["summary", "critic"]
    audiences = cfg.get("audiences") or []
    style = cfg.get("style") or "journalistic"
    input_path = cfg.get("input")
    input_data, inp_format = _load_input_payload(input_path)
    client = _wiz_select_provider(cfg.get("provider"), cfg.get("model"))

    agents = _create_agents(
        agents_cfg,
        cfg.get("depends_on") or {},
        audiences,
        style,
        client,
    )

    context, rubric_ref = _build_execution_context(client, cfg, input_data)
    outputs, orch = _execute_orchestrator(agents, cfg, context)

    return _build_pack_structure(
        cfg,
        outputs,
        orch,
        agents,
        client,
        audiences,
        style,
        rubric_ref,
        input_path,
        inp_format,
        input_data,
    )


def _load_input_payload(input_path: str | None) -> tuple[Any | None, str | None]:
    if not input_path:
        return None, None
    return _load_input_data(input_path)


def _create_agents(
    agents_cfg: list[Any],
    depends_map: dict[str, list[str]],
    audiences: list[str],
    style: str,
    client: Any,
) -> list[Agent]:
    def role_for_id(aid: str) -> str:
        if aid == "critic":
            return "critic"
        if aid == "editor":
            return "editor"
        return "specialist"

    def output_for_id(aid: str) -> str:
        if aid == "critic":
            return "critic_notes"
        if aid == "editor":
            return "edited"
        return aid

    agents: list[Agent] = []
    for entry in agents_cfg:
        if isinstance(entry, dict):
            raw_id = str(entry.get("id") or "").strip()
            if not raw_id:
                continue
            aid = raw_id
            role = str(entry.get("role") or role_for_id(aid))
            outputs_list = _coerce_outputs(entry.get("outputs"), output_for_id(aid))
            entry_depends = _as_str_list(entry.get("depends_on"))
            params = (
                entry.get("params") if isinstance(entry.get("params"), dict) else None
            )
            prompt_value = (
                entry.get("prompt") if isinstance(entry.get("prompt"), str) else None
            )
            prompt_ref_override = (
                entry.get("prompt_ref")
                if isinstance(entry.get("prompt_ref"), str)
                else None
            )
        else:
            raw_id = str(entry).strip()
            if not raw_id:
                continue
            aid = raw_id
            role = role_for_id(aid)
            outputs_list = [output_for_id(aid)]
            entry_depends = []
            params = None
            prompt_value = None
            prompt_ref_override = None

        base_depends = _as_str_list(depends_map.get(aid))
        resolved_depends = _merge_unique_ids(base_depends, entry_depends)
        prompt_text, prompt_ref = _resolve_prompt_template(aid, role)
        if prompt_value:
            override_text, override_ref = _resolve_prompt_override(prompt_value)
            if override_text is not None:
                prompt_text = override_text
                prompt_ref = override_ref or prompt_ref
        if prompt_ref_override:
            prompt_ref = prompt_ref_override
        spec = AgentSpec(
            id=aid,
            role=role,
            prompt=prompt_text,
            prompt_ref=prompt_ref,
            outputs=outputs_list,
            params=params,
            depends_on=resolved_depends or None,
        )
        agents.append(Agent(spec, audience=audiences, style=style, llm=client))

    if audiences:
        aud_outputs = [f"{a}_version" for a in audiences]
        aud_prompt, aud_prompt_ref = _resolve_prompt_template(
            "audience_adapter", "specialist"
        )
        agents.append(
            Agent(
                AgentSpec(
                    id="audience_adapter",
                    role="specialist",
                    prompt=aud_prompt,
                    prompt_ref=aud_prompt_ref,
                    outputs=aud_outputs,
                ),
                audience=audiences,
                style=style,
                llm=client,
            )
        )

    return agents


def _build_execution_context(
    client: Any, cfg: dict[str, Any], input_data: Any | None
) -> tuple[dict[str, Any], str]:
    rubric, rubric_ref = _load_critic_rubric(cfg.get("rubric"))
    context: dict[str, Any] = {
        "llm": client,
        "critic_rubric": rubric,
        "outputs": {},
        "critic_structured": bool(cfg.get("critic_structured")),
        "strict_grounding": bool(cfg.get("strict_grounding")),
        "attach_images": bool(cfg.get("attach_images")),
        "input_data": input_data,
    }
    return context, rubric_ref


def _execute_orchestrator(
    agents: list[Agent], cfg: dict[str, Any], context: dict[str, Any]
) -> tuple[dict[str, Any], SwarmOrchestrator]:
    orch = SwarmOrchestrator(
        agents,
        max_workers=cfg.get("max_workers"),
        max_rounds=int(cfg.get("max_rounds") or 1),
    )
    outputs = asyncio.run(orch.execute(context))
    return outputs, orch


def _build_pack_structure(
    cfg: dict[str, Any],
    outputs: dict[str, Any],
    orch: SwarmOrchestrator,
    agents: list[Agent],
    client: Any,
    audiences: list[str],
    style: str,
    rubric_ref: str,
    input_path: str | None,
    inp_format: str | None,
    input_data: Any | None,
) -> dict[str, Any]:
    declared_agents = [a.spec.id for a in agents]
    failed = {
        a for a in getattr(orch, "failed_agents", []) if a in set(declared_agents)
    }

    prov = list(getattr(orch, "provenance", []))
    with suppress(Exception):
        prov.sort(key=lambda p: (p.get("agent") or "", p.get("started") or ""))

    critical = {"summary", "critic", "editor"}
    completed = not any(a in failed for a in critical)

    if bool(cfg.get("strict_grounding")):
        _cn = outputs.get("critic_notes")

        def _has_ungrounded(val: Any) -> bool:
            try:
                if isinstance(val, dict):
                    s = str(val.get("notes", ""))
                else:
                    s = str(val or "")
                u = s.upper()
                return "[UNGROUNDED]" in u or u.startswith("UNGROUNDED")
            except Exception:
                return False

        if _has_ungrounded(_cn):
            completed = False

    reviews: dict[str, Any] = {}
    _cn = outputs.get("critic_notes")
    if (isinstance(_cn, str) and _cn.strip()) or (
        isinstance(_cn, dict) and _cn.get("notes")
    ):
        reviews["critic"] = _cn

    inputs_section: dict[str, Any] = {
        "audiences": audiences,
        "style": style,
        "rubric": rubric_ref,
        **({"file": input_path, "format": inp_format} if input_path else {}),
    }
    if cfg.get("preset"):
        inputs_section["preset"] = cfg.get("preset")
    try:
        if input_data and isinstance(input_data, dict) and input_data.get("images"):
            from pathlib import Path

            imgs_meta = []
            for it in input_data.get("images")[:8]:
                if not isinstance(it, dict):
                    continue
                p = it.get("path")
                if not isinstance(p, str):
                    continue
                meta = {"path": p}
                if it.get("label"):
                    meta["label"] = it.get("label")
                try:
                    sz = Path(p).stat().st_size
                    meta["bytes"] = int(sz)
                except Exception:
                    pass
                imgs_meta.append(meta)
            if imgs_meta:
                inputs_section["images"] = imgs_meta
    except Exception:
        pass

    return {
        "version": 0,
        "inputs": inputs_section,
        "models": {
            "provider": cfg.get("provider") or getattr(client, "name", "mock"),
            "model": cfg.get("model") or getattr(client, "model", "placeholder"),
        },
        "status": {"completed": bool(completed), "failed_agents": sorted(list(failed))},
        "outputs": outputs,
        "reviews": reviews,
        "errors": getattr(orch, "errors", []),
        "provenance": prov,
    }


def _is_rfc3339(ts: str) -> bool:
    try:
        s = ts.strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        if "T" not in s:
            return False
        datetime.fromisoformat(s)
        return True
    except Exception:
        return False


def _runtime_validate_pack_dict(d: dict[str, Any]) -> None:
    # Note: failed_agents may include agents that were skipped before execution
    # (e.g., unmet dependencies), so they may not appear in provenance. We do not
    # enforce membership here.
    prov = d.get("provenance") or []
    if not isinstance(prov, list):
        return
    times_by_agent: dict[str, list[str]] = {}
    for i, p in enumerate(prov):
        if not isinstance(p, dict):
            continue
        agent = str(p.get("agent") or "")
        ts = p.get("started")
        if ts:
            if not isinstance(ts, str) or not _is_rfc3339(ts):
                raise ValueError(f"provenance[{i}].started: invalid RFC3339 timestamp")
            times_by_agent.setdefault(agent, []).append(ts)
    from contextlib import suppress as _suppress

    with _suppress(Exception):
        for agent, seq in times_by_agent.items():

            def _to_dt(s: str) -> datetime:
                s2 = s[:-1] + "+00:00" if s.endswith("Z") else s
                return datetime.fromisoformat(s2)

            seq_dt = [_to_dt(s) for s in seq]
            if any(seq_dt[i] > seq_dt[i + 1] for i in range(len(seq_dt) - 1)):
                raise ValueError(
                    f"provenance: timestamps not monotonic for agent '{agent}'"
                )
    # Audience outputs must be present and non-empty when audiences requested
    try:
        audiences = (d.get("inputs") or {}).get("audiences") or []
        outs = d.get("outputs") or {}
        for aud in audiences:
            key = f"{aud}_version"
            val = outs.get(key)
            if not isinstance(val, str) or not val.strip():
                raise ValueError(
                    f"outputs.{key}: missing or empty for audience '{aud}'"
                )
    except Exception as exc:
        raise ValueError(str(exc)) from exc


def _coerce_outputs(value: Any, default_output: str) -> list[str]:
    outputs = _as_str_list(value)
    return outputs or [default_output]


def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return _split_csv(value)
    if isinstance(value, (list, tuple, set)):
        out: list[str] = []
        for item in value:
            if isinstance(item, str) and item.strip():
                out.append(item.strip())
        return out
    return []


def _merge_unique_ids(left: list[str], right: list[str]) -> list[str]:
    merged: list[str] = []
    for seq in (left or [], right or []):
        for item in seq:
            if item not in merged:
                merged.append(item)
    return merged


def _resolve_prompt_template(aid: str, role: str) -> tuple[str | None, str | None]:
    name_map = {
        "summary": "summary",
        "context": "context",
        "critic": "critic",
        "editor": "editor",
        "audience_adapter": "audience_adapter",
    }
    key = name_map.get(aid)
    if not key and role == "critic":
        key = "critic"
    if not key and role == "editor":
        key = "editor"
    if not key:
        return None, None
    try:
        base = ir.files("zyra.assets").joinpath(f"llm/prompts/narrate/{key}.md")
        return (
            base.read_text(encoding="utf-8"),
            f"zyra.assets/llm/prompts/narrate/{key}.md",
        )
    except Exception:
        return None, None


def _resolve_prompt_override(value: str) -> tuple[str | None, str | None]:
    candidate = value.strip()
    if not candidate:
        return None, None
    if "\n" in candidate:
        return candidate, None
    pathish = any(
        sep in candidate for sep in ("/", "\\")
    ) or candidate.lower().endswith((".md", ".txt", ".yaml", ".yml"))
    if candidate.startswith("zyra.assets/"):
        rel = candidate.split("zyra.assets/", 1)[1]
        try:
            base = ir.files("zyra.assets").joinpath(rel)
            return base.read_text(encoding="utf-8"), candidate
        except Exception as exc:  # pragma: no cover - exercised via CLI tests
            raise ValueError(f"failed to read prompt '{candidate}': {exc}") from exc
    if pathish:
        from pathlib import Path

        path = Path(candidate).expanduser()
        if path.is_file():
            try:
                return path.read_text(encoding="utf-8"), str(path)
            except Exception as exc:  # pragma: no cover - file read errors rare
                raise ValueError(f"failed to read prompt '{candidate}': {exc}") from exc
        # Attempt to resolve relative to packaged assets
        try:
            base = ir.files("zyra.assets").joinpath(candidate)
            if base.is_file():
                return base.read_text(encoding="utf-8"), f"zyra.assets/{candidate}"
        except Exception:
            pass
        raise ValueError(f"prompt file not found: {candidate}")
    return candidate, None


_FALLBACK_CRITIC_RUBRIC = [
    "Clarity for non-experts",
    "Avoid bias and stereotypes",
    "Include citations where possible",
    "Flag unverifiable claims",
]


def _load_critic_rubric(path: str | None) -> tuple[list[str], str]:
    if path:
        from pathlib import Path

        try:
            text = Path(path).expanduser().read_text(encoding="utf-8")
        except FileNotFoundError as err:
            raise ValueError(f"rubric file not found: {path}") from err
        except Exception as exc:  # pragma: no cover - rare read failure
            raise ValueError(f"failed to read rubric '{path}': {exc}") from exc
        try:
            import yaml  # type: ignore

            data = yaml.safe_load(text) or []
        except Exception as exc:  # pragma: no cover - yaml parse failure
            raise ValueError(f"failed to parse rubric '{path}': {exc}") from exc
        if not isinstance(data, list) or not all(isinstance(x, str) for x in data):
            raise ValueError("rubric must be a list of strings")
        return [str(x) for x in data], str(Path(path).expanduser())

    env_fallback = os.getenv("ZYRA_CRITIC_RUBRIC_FALLBACK")
    if env_fallback:
        from pathlib import Path

        try:
            text = Path(env_fallback).expanduser().read_text(encoding="utf-8")
        except FileNotFoundError as err:
            raise ValueError(f"fallback rubric file not found: {env_fallback}") from err
        except Exception as exc:  # pragma: no cover - rare read failure
            raise ValueError(
                f"failed to read fallback rubric '{env_fallback}': {exc}"
            ) from exc
        try:
            import yaml  # type: ignore

            data = yaml.safe_load(text) or []
        except Exception as exc:  # pragma: no cover - yaml parse failure
            raise ValueError(
                f"failed to parse fallback rubric '{env_fallback}': {exc}"
            ) from exc
        if not isinstance(data, list) or not all(isinstance(x, str) for x in data):
            raise ValueError("fallback rubric must be a list of strings")
        return [str(x) for x in data], str(Path(env_fallback).expanduser())

    try:
        base = ir.files("zyra.assets").joinpath("llm/rubrics/critic.yaml")
        text = base.read_text(encoding="utf-8")
        import yaml  # type: ignore

        data = yaml.safe_load(text) or []
        if isinstance(data, list) and all(isinstance(x, str) for x in data):
            return [str(x) for x in data], "zyra.assets/llm/rubrics/critic.yaml"
    except Exception:
        pass
    return _FALLBACK_CRITIC_RUBRIC, "zyra.assets/llm/rubrics/critic.yaml"


def _load_default_critic_rubric() -> list[str]:  # pragma: no cover - legacy helper
    rubric, _ = _load_critic_rubric(None)
    return rubric


def _resolve_swarm_config(ns: argparse.Namespace) -> dict[str, Any]:
    # Start with defaults
    cfg: dict[str, Any] = {}
    # Env toggles (fallback when CLI lacks flags)
    try:
        import os as _os

        if _os.environ.get("ZYRA_STRICT_GROUNDING"):
            cfg["strict_grounding"] = True
        if _os.environ.get("ZYRA_CRITIC_STRUCTURED"):
            cfg["critic_structured"] = True
    except Exception:
        pass
    # Preset layer
    preset_name = ns.preset
    if preset_name and preset_name not in {"help", "?"}:
        preset_cfg = _load_preset(preset_name)
        if preset_cfg is None:
            raise ValueError(f"failed to load preset: {preset_name}")
        cfg.update(_normalize_cfg(preset_cfg))
    # YAML file layer
    if ns.swarm_config:
        file_cfg = _load_yaml_file(ns.swarm_config)
        cfg.update(_normalize_cfg(file_cfg))

    # CLI overrides
    def _merge_cli(key: str, value: Any) -> None:
        if value is None:
            return
        prev = cfg.get(key)
        if prev is not None and prev != value:
            print(
                f"Overriding config '{key}' from '{prev}' to '{value}' via CLI",
                file=sys.stderr,
            )
        cfg[key] = value

    # Map CLI fields
    _merge_cli("style", ns.style)
    _merge_cli("provider", ns.provider)
    _merge_cli("model", ns.model)
    _merge_cli("base_url", getattr(ns, "base_url", None))
    _merge_cli("pack", ns.pack)
    _merge_cli("rubric", ns.rubric)
    _merge_cli("input", getattr(ns, "input", None))
    _merge_cli("max_workers", ns.max_workers)
    _merge_cli("max_rounds", ns.max_rounds)
    if getattr(ns, "critic_structured", False):
        _merge_cli("critic_structured", True)
    if getattr(ns, "attach_images", False):
        _merge_cli("attach_images", True)
    if getattr(ns, "strict_grounding", False):
        _merge_cli("strict_grounding", True)
    if ns.agents:
        _merge_cli("agents", _split_csv(ns.agents))
    if ns.audiences:
        _merge_cli("audiences", _split_csv(ns.audiences))
    if preset_name and preset_name not in {"help", "?"}:
        cfg.setdefault("preset", preset_name)
    return cfg


def _split_csv(v: str) -> list[str]:
    return [a.strip() for a in v.split(",") if a.strip()]


def _normalize_cfg(d: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    # Support either dash/underscore keys; keep minimal fields for now
    if "agents" in d:
        out["agents"] = (
            d["agents"]
            if isinstance(d["agents"], list)
            else _split_csv(str(d["agents"]))
        )
    if "audiences" in d:
        out["audiences"] = (
            d["audiences"]
            if isinstance(d["audiences"], list)
            else _split_csv(str(d["audiences"]))
        )
    for k in (
        "style",
        "provider",
        "model",
        "base_url",
        "pack",
        "rubric",
        "strict_grounding",
        "critic_structured",
        "attach_images",
    ):
        if k in d:
            out[k] = d[k]
    # Graph: from/to edges into depends_on map
    graph = d.get("graph")
    if isinstance(graph, list):
        depends: dict[str, set[str]] = {}
        for edge in graph:
            if not isinstance(edge, dict):
                continue
            from_v = edge.get("from")
            to_v = edge.get("to")
            if to_v is None:
                continue
            tos = to_v if isinstance(to_v, list) else [to_v]
            froms = from_v if isinstance(from_v, list) else [from_v]
            for t in tos:
                if not isinstance(t, str):
                    continue
                depends.setdefault(t, set()).update(
                    x for x in froms if isinstance(x, str)
                )
        if depends:
            out["depends_on"] = {k: sorted(list(v)) for k, v in depends.items()}
    for k in ("max_workers", "max_rounds"):
        if k in d:
            with suppress(Exception):
                out[k] = int(d[k]) if d[k] is not None else None
    return out


def _load_yaml_file(path: str) -> dict[str, Any]:
    try:
        from pathlib import Path

        import yaml  # type: ignore

        text = Path(path).read_text(encoding="utf-8")
        data = yaml.safe_load(text) or {}
        if not isinstance(data, dict):
            raise ValueError("swarm-config must be a mapping")
        return data
    except FileNotFoundError as err:
        raise ValueError(f"config file not found: {path}") from err
    except Exception as e:
        raise ValueError(f"failed to read config '{path}': {e}") from e


def _load_preset(name: str) -> dict[str, Any] | None:
    try:
        base = ir.files("zyra.assets").joinpath("llm/presets/narrate")
        for ext in (".yaml", ".yml"):
            p = base / f"{name}{ext}"
            if p.is_file():
                import yaml  # type: ignore

                return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception:
        return None
    return None


def _write_pack(dest: str, data: dict[str, Any]) -> None:
    if dest == "-":
        # Emit YAML if possible, else JSON
        try:
            import yaml  # type: ignore

            print(yaml.safe_dump({"narrative_pack": data}, sort_keys=False))
            return
        except Exception:
            print(json.dumps({"narrative_pack": data}, indent=2))
            return
    # File output
    try:
        from pathlib import Path

        import yaml  # type: ignore

        text = yaml.safe_dump({"narrative_pack": data}, sort_keys=False)
        Path(dest).write_text(text, encoding="utf-8")
    except Exception:
        from pathlib import Path

        Path(dest).write_text(
            json.dumps({"narrative_pack": data}, indent=2), encoding="utf-8"
        )


def _load_input_data(path_or_dash: str) -> tuple[Any, str | None]:
    # Read bytes (stdin or file)
    from zyra.utils.cli_helpers import read_all_bytes

    b = read_all_bytes(path_or_dash)
    text = b.decode("utf-8", errors="replace")
    # Try JSON
    try:
        return json.loads(text), "json"
    except Exception:
        pass
    # Try YAML
    try:
        import yaml  # type: ignore

        y = yaml.safe_load(text)
        if y is not None:
            return y, "yaml"
    except Exception:
        pass
    # Fallback to text
    return text, "text"
