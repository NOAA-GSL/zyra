# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import argparse
import difflib
import time
from typing import Any

from zyra.api.schemas.domain_args import resolve_model
from zyra.utils.env import env_int

# Percentage-to-decimal divisor constant (e.g., 50 -> 0.5)
PERCENT_TO_DECIMAL_DIVISOR = 100.0

# Allowed detail keys for get_command()
VALID_DETAILS = {"options", "example"}


def percentage_to_decimal(percent: int | float) -> float:
    """Convert a 0–100 percentage to a 0.0–1.0 decimal fraction."""
    try:
        return float(percent) / PERCENT_TO_DECIMAL_DIVISOR
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Invalid percentage value: {percent!r}. Expected a numeric 0–100."
        ) from exc


# In-memory cache for the computed manifest
_CACHE: dict[str, Any] | None = None
_CACHE_TS: float | None = None


def _type_name(t: Any) -> str | None:
    if t is None:
        return None
    if t in (str, int, float, bool):
        return t.__name__
    try:
        return t.__class__.__name__
    except Exception:
        return None


def _extract_arg_schema(
    p: argparse.ArgumentParser,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return (positionals, options_map) extracted from an argparse parser."""
    positionals: list[dict[str, Any]] = []
    options: dict[str, Any] = {}
    option_names: list[str] = []

    for act in getattr(p, "_actions", []):
        # Skip help actions
        if (
            getattr(act, "help", None) == argparse.SUPPRESS
            or act.__class__.__name__ == "_HelpAction"
        ):
            continue
        if getattr(act, "dest", None) in {"help", "_help"}:
            continue

        flags = list(getattr(act, "option_strings", []) or [])
        help_text = getattr(act, "help", None)
        default = getattr(act, "default", None)
        # Capture but do not use here; positional `nargs` is handled by the
        # shared collector to avoid duplicated semantics.
        _nargs = getattr(act, "nargs", None)
        choices = list(getattr(act, "choices", []) or []) or None
        tp = getattr(act, "type", None)
        # Derive type name and bool store actions
        if tp is None:
            cname = act.__class__.__name__
            if cname in {"_StoreTrueAction", "_StoreFalseAction"}:
                type_name = "bool"
            else:
                type_name = None
        else:
            type_name = _type_name(tp)

        if flags:
            # Heuristic: mark path-like flags (used by some UIs)
            dest = (getattr(act, "dest", "") or "").lower()
            path_arg = False
            for needle in ("path", "file", "dir", "output", "input"):
                if needle in dest:
                    path_arg = True
                    break

            options_meta: dict[str, Any] = {
                "help": help_text,
                "type": type_name,
                "default": default,
                # For option flags (arguments with option strings), argparse’s
                # `.required` indicates a mandatory option (e.g., `--file` must
                # be provided) versus a truly optional one (e.g., `--verbose`).
                "required": bool(getattr(act, "required", False)),
            }
            if path_arg:
                options_meta["path_arg"] = True
            if choices:
                options_meta["choices"] = choices

            # Export under each flag; prefer longest form (e.g., --long over -l)
            # but keep all keys present for quick lookup
            for fl in flags:
                options[fl] = options_meta
            option_names.extend(flags)
        else:
            # Defer positional handling; we will reuse the shared collector
            # to ensure consistent `nargs` semantics across the project.
            continue

    # Reuse the Wizard's positional collector to avoid duplicated `nargs` logic.
    # Falls back to a minimal local extraction if import is unavailable.
    try:
        from zyra.wizard.manifest import _collect_positionals as _wiz_collect

        positionals = _wiz_collect(p)  # type: ignore[assignment]
    except Exception:
        # Minimal fallback: include dest/help/type without required inference
        positionals = []
        for act in getattr(p, "_actions", []):
            if getattr(act, "option_strings", None):
                continue
            help_text = getattr(act, "help", None)
            choices = list(getattr(act, "choices", []) or []) or None
            tp = getattr(act, "type", None)
            type_name = _type_name(tp)
            positionals.append(
                {
                    "name": getattr(act, "dest", None),
                    "help": help_text,
                    "type": type_name,
                    "choices": choices,
                }
            )

    return positionals, options


def _parsers_from_register(register_fn) -> dict[str, argparse.ArgumentParser]:
    parser = argparse.ArgumentParser(prog="zyra")
    sub = parser.add_subparsers(dest="sub")
    register_fn(sub)
    # type: ignore[attr-defined]
    return dict(getattr(sub, "choices", {}))


def _compute_manifest() -> dict[str, Any]:
    import zyra.connectors.egress as egress
    import zyra.connectors.ingest as ingest
    import zyra.processing as processing
    import zyra.transform as transform
    import zyra.visualization as visualization

    manifest: dict[str, Any] = {}

    def _example_args(stage: str, tool: str) -> dict[str, Any] | None:
        ex: dict[tuple[str, str], dict[str, Any]] = {
            ("visualize", "heatmap"): {
                "input": "samples/demo.npy",
                "output": "/tmp/heatmap.png",
                "width": 800,
                "height": 400,
            },
            ("visualize", "contour"): {
                "input": "samples/demo.npy",
                "output": "/tmp/contour.png",
                "levels": 10,
                "filled": True,
            },
            ("visualize", "animate"): {
                "input": "samples/demo.npy",
                "output_dir": "/tmp/frames",
                "fps": 24,
                "to_video": "/tmp/out.mp4",
            },
            ("process", "convert-format"): {
                "file_or_url": "samples/demo.grib2",
                "format": "netcdf",
                "stdout": True,
            },
            ("process", "decode-grib2"): {
                "file_or_url": "samples/demo.grib2",
                "pattern": "TMP",
            },
            ("process", "extract-variable"): {
                "file_or_url": "samples/demo.grib2",
                "pattern": "TMP",
            },
            ("decimate", "local"): {
                "input": "-",
                "path": "/tmp/out.bin",
            },
            ("decimate", "post"): {
                "input": "-",
                "url": "https://example.com/ingest",
                "content_type": "application/octet-stream",
            },
            ("decimate", "s3"): {
                "input": "-",
                "url": "s3://bucket/path/out.bin",
            },
            ("acquire", "http"): {
                "url": "https://example.com/file.bin",
                "output": "/tmp/file.bin",
            },
            ("acquire", "s3"): {
                "url": "s3://bucket/key",
                "output": "/tmp/file.bin",
            },
            ("acquire", "ftp"): {
                "path": "ftp://host/path/file.bin",
                "output": "/tmp/file.bin",
            },
        }
        return ex.get((stage, tool))

    def add_stage(stage: str, register_fn) -> None:
        parsers = _parsers_from_register(register_fn)
        for name, parser in parsers.items():
            full = f"{stage} {name}"
            positionals, options = _extract_arg_schema(parser)
            # Prefer explicit parser description when provided
            desc = getattr(parser, "description", None) or f"zyra {full}"
            # Arg schema hint from domain models (if available)
            stage_name = stage
            model = resolve_model(stage_name, name)
            required: list[str] | None = None
            optional: list[str] | None = None
            if model is not None:
                try:
                    req: list[str] = []
                    opt: list[str] = []
                    for fname, finfo in getattr(model, "model_fields", {}).items():
                        # Pydantic v2: finfo.is_required()
                        if getattr(finfo, "is_required", lambda: False)():
                            req.append(fname)
                        else:
                            opt.append(fname)
                    required = sorted(req)
                    optional = sorted(opt)
                except Exception:
                    required = None
                    optional = None
            example = _example_args(stage, name)
            entry = {
                "description": desc,
                "doc": "",
                "epilog": "",
                "groups": [
                    {"title": "options", "options": sorted(list(options.keys()))}
                ],
                "options": options,
                "positionals": positionals,
                "domain": stage_name,
                "args_schema": (
                    {"required": required, "optional": optional}
                    if required is not None and optional is not None
                    else None
                ),
                "example_args": example,
            }
            manifest[full] = entry

    for stage, reg in (
        ("acquire", ingest.register_cli),
        ("process", processing.register_cli),
        ("visualize", visualization.register_cli),
        ("decimate", egress.register_cli),
        ("transform", transform.register_cli),
    ):
        add_stage(stage, reg)

    # Top-level run
    from zyra.pipeline_runner import register_cli_run as _register_run

    parsers = _parsers_from_register(_register_run)
    for name, parser in parsers.items():
        full = name  # e.g., "run"
        positionals, options = _extract_arg_schema(parser)
        desc = getattr(parser, "description", None) or f"zyra {full}"
        entry = {
            "description": desc,
            "doc": "",
            "epilog": "",
            "groups": [{"title": "options", "options": sorted(list(options.keys()))}],
            "options": options,
            "positionals": positionals,
        }
        manifest[full] = entry

    return manifest


def _cache_ttl_seconds() -> int:
    # env_int reads ZYRA_<KEY> and already returns an int with defaults
    return env_int("MANIFEST_CACHE_TTL", 300)


def get_manifest(force_refresh: bool = False) -> dict[str, Any]:
    global _CACHE, _CACHE_TS
    now = time.time()
    ttl = _cache_ttl_seconds()
    if force_refresh or _CACHE is None or _CACHE_TS is None or (now - _CACHE_TS) > ttl:
        _CACHE = _compute_manifest()
        _CACHE_TS = now
    return _CACHE


def refresh_manifest() -> dict[str, Any]:
    return get_manifest(force_refresh=True)


def list_commands(
    *,
    format: str = "json",
    stage: str | None = None,
    q: str | None = None,
    refresh: bool = False,
) -> dict[str, Any]:
    data = get_manifest(force_refresh=refresh)

    def _stage_ok(cmd: str) -> bool:
        if not stage:
            return True
        return cmd.split(" ", 1)[0] == stage

    def _q_ok(cmd: str, entry: dict[str, Any]) -> bool:
        if not q:
            return True
        hay = f"{cmd} {entry.get('description','')}".lower()
        return q.lower() in hay

    items = [(k, v) for k, v in sorted(data.items()) if _stage_ok(k) and _q_ok(k, v)]

    if format == "list":
        return {"commands": [k for k, _ in items]}
    if format == "summary":
        return {
            "commands": [
                {"name": k, "description": v.get("description", "")} for k, v in items
            ]
        }
    return {"commands": {k: v for k, v in items}}


def _example_for(cmd: str, info: dict[str, Any]) -> str:
    """Construct a basic example invocation for a command.

    This is intentionally simple and meant as a hint, not exhaustive. We try to
    include one positional (if present) and one common option flag with a
    reasonable placeholder based on type hints.
    """
    example = f"zyra {cmd}"

    # Include a positional placeholder if available (prefer required)
    try:
        pos_list = list(info.get("positionals") or [])
        chosen_pos = next((p for p in pos_list if p.get("required")), None)
        if chosen_pos is None and pos_list:
            chosen_pos = pos_list[0]
        if isinstance(chosen_pos, dict):
            name = str(chosen_pos.get("name") or "arg")
            example += f" <{name}>"
    except Exception:
        pass

    # Choose a representative option flag
    try:
        options = info.get("options") or {}
        if isinstance(options, dict) and options:
            # Prefer common long-form flags if available
            preferred = [
                "--input",
                "--inputs",
                "--output",
                "--output-dir",
                "--file",
                "--path",
                "--url",
            ]
            flags = list(options.keys())
            flag = next((f for f in preferred if f in flags), None)
            if flag is None:
                # Prefer any long flag, pick the longest for readability
                long_flags = [
                    f for f in flags if isinstance(f, str) and f.startswith("--")
                ]
                flag = max(long_flags, key=len) if long_flags else flags[0]

            meta = options.get(flag, {}) if isinstance(flag, str) else {}
            if isinstance(meta, dict):
                typ = str(meta.get("type") or "")
                path_arg = bool(meta.get("path_arg", False))
                if typ == "bool":
                    example += f" {flag}"
                else:
                    placeholder = "<value>"
                    lname = flag.lower() if isinstance(flag, str) else ""
                    if path_arg or any(k in lname for k in ("path", "file", "dir")):
                        placeholder = "<path>"
                    elif "url" in lname:
                        placeholder = "<url>"
                    example += f" {flag} {placeholder}"
    except Exception:
        pass

    return example


def get_command(
    *,
    command_name: str,
    details: str | None = None,
    fuzzy_cutoff: float | None = None,
    refresh: bool = False,
) -> dict[str, Any]:
    # Validate details parameter early to provide clear errors to API consumers
    if details is not None and details not in VALID_DETAILS:
        return {
            "error": "Invalid details parameter",
            "requested": details,
            "allowed": sorted(list(VALID_DETAILS)),
        }
    data = get_manifest(force_refresh=refresh)
    names = list(data.keys())

    if fuzzy_cutoff is None:
        # Read percentage and convert to 0.0–1.0 cutoff via helper
        fuzzy_cutoff = percentage_to_decimal(env_int("MANIFEST_FUZZY_CUTOFF", 50))

    match = difflib.get_close_matches(command_name, names, n=1, cutoff=fuzzy_cutoff)
    if not match:
        return {
            "error": f"No matching command found for '{command_name}'",
            "requested": command_name,
            "available": names,
        }

    cmd = match[0]
    info = data[cmd]
    if details == "options":
        return {"command": cmd, "options": info.get("options", {})}
    if details == "example":
        return {"command": cmd, "example": _example_for(cmd, info)}
    return {"command": cmd, "info": info}
