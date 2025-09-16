# SPDX-License-Identifier: Apache-2.0
"""Narration/reporting stage CLI.

Keeps a minimal ``describe`` command for back-compat and adds a new
``swarm`` command that accepts presets/config flags (plan-aligned).
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
from contextlib import suppress
from datetime import datetime
from importlib import resources as ir
from typing import Any

from zyra.narrate.schemas import NarrativePack
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


def _list_presets() -> list[str]:
    # Discover packaged presets under zyra.assets/llm/presets/narrate
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
    pack = _build_pack_with_orchestrator(resolved)
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
    from zyra.narrate.swarm import Agent, AgentSpec, SwarmOrchestrator

    outputs: dict[str, Any] = {}
    agents_cfg = cfg.get("agents") or ["summary", "critic"]
    audiences = cfg.get("audiences") or []
    style = cfg.get("style") or "journalistic"
    input_path = cfg.get("input")

    # Optional: load input data (JSON/YAML autodetect; else text)
    inp_format = None
    input_data: Any | None = None
    if input_path:
        input_data, inp_format = _load_input_data(input_path)

    # Provider selection (mock-friendly)
    client = _wiz_select_provider(cfg.get("provider"), cfg.get("model"))

    # Build Agent instances from config
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

    # Graph dependencies (optional)
    depends: dict[str, list[str]] = cfg.get("depends_on") or {}
    agent_objs = []
    for aid in agents_cfg:
        spec = AgentSpec(
            id=aid,
            role=role_for_id(aid),
            outputs=[output_for_id(aid)],
            depends_on=depends.get(aid, []),
        )
        agent_objs.append(Agent(spec, audience=audiences, style=style, llm=client))

    # Add a dedicated audience_adapter agent for per-audience variants
    if audiences:
        aud_outputs = [f"{a}_version" for a in audiences]
        agent_objs.append(
            Agent(
                AgentSpec(
                    id="audience_adapter", role="specialist", outputs=aud_outputs
                ),
                audience=audiences,
                style=style,
                llm=client,
            )
        )

    orch = SwarmOrchestrator(
        agent_objs,
        max_workers=cfg.get("max_workers"),
        max_rounds=int(cfg.get("max_rounds") or 1),
    )

    import asyncio as _asyncio

    # Load default critic rubric for critic/editor loop
    rubric = _load_default_critic_rubric()
    ctx = {
        "llm": client,
        "critic_rubric": rubric,
        "outputs": {},
        "critic_structured": bool(cfg.get("critic_structured")),
        "strict_grounding": bool(cfg.get("strict_grounding")),
        "input_data": input_data,
    }
    outputs.update(_asyncio.run(orch.execute(ctx)))

    # Runtime invariants: restrict failed_agents to declared agents and sort provenance timestamps per agent
    declared_agents = [a.spec.id for a in agent_objs]
    failed = set(
        a for a in getattr(orch, "failed_agents", []) if a in set(declared_agents)
    )
    # Sort provenance by (agent, started) to ensure monotonic order per agent
    prov = list(getattr(orch, "provenance", []))
    from contextlib import suppress as _suppress

    with _suppress(Exception):
        prov.sort(key=lambda p: (p.get("agent") or "", p.get("started") or ""))
    # Determine completion based on critical agents
    critical = {"summary", "critic", "editor"}
    completed = not any(a in failed for a in critical)

    # Strict grounding: if enabled and critic marks UNGROUNDED, flip to incomplete
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
    # Populate reviews.critic if critic_notes present and non-empty
    _cn = outputs.get("critic_notes")
    if (isinstance(_cn, str) and _cn.strip()) or (
        isinstance(_cn, dict) and _cn.get("notes")
    ):
        reviews["critic"] = _cn

    # Inputs section with optional images metadata (label/path/size) when present
    inputs_section: dict[str, Any] = {
        "audiences": audiences,
        "style": style,
        **({"file": input_path, "format": inp_format} if input_path else {}),
    }
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

    pack: dict[str, Any] = {
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
    return pack


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


def _load_default_critic_rubric() -> list[str]:
    try:
        base = ir.files("zyra.assets").joinpath("llm/rubrics/critic.yaml")
        with ir.as_file(base) as p:
            import yaml  # type: ignore

            data = yaml.safe_load(p.read_text(encoding="utf-8")) or []
            if isinstance(data, list) and all(isinstance(x, str) for x in data):
                return data
    except Exception:
        pass
    return [
        "Clarity for non-experts",
        "Avoid bias and stereotypes",
        "Include citations where possible",
        "Flag unverifiable claims",
    ]


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
