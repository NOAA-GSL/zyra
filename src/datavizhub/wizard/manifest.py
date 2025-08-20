from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _safe_register_all(sub: argparse._SubParsersAction) -> None:
    """Register all top-level groups, skipping modules that fail to import.

    Matches the fallback branch in datavizhub.cli but wraps imports in try/except
    to avoid hard-failing when optional extras (e.g., cartopy) are missing.
    """
    # acquire
    try:
        from datavizhub.connectors import ingest as _ingest_mod

        p_acq = sub.add_parser("acquire", help="Acquire/ingest data from sources")
        acq_sub = p_acq.add_subparsers(dest="acquire_cmd", required=True)
        _ingest_mod.register_cli(acq_sub)
    except (
        ImportError,
        AttributeError,
    ):  # pragma: no cover - optional extras might be missing
        pass

    # process
    try:
        from datavizhub import processing as _process_mod

        p_proc = sub.add_parser(
            "process", help="Processing commands (GRIB/NetCDF/GeoTIFF)"
        )
        proc_sub = p_proc.add_subparsers(dest="process_cmd", required=True)
        _process_mod.register_cli(proc_sub)
    except (ImportError, AttributeError):  # pragma: no cover
        pass

    # visualize
    try:
        # Use lightweight registrar to avoid importing heavy visualization root
        from datavizhub.visualization import cli_register as _viz_cli

        p_viz = sub.add_parser(
            "visualize", help="Visualization commands (static/interactive/animation)"
        )
        viz_sub = p_viz.add_subparsers(dest="visualize_cmd", required=True)
        _viz_cli.register_cli(viz_sub)
    except (
        ImportError,
        AttributeError,
    ):  # pragma: no cover - heavy deps may be missing
        pass

    # decimate
    try:
        from datavizhub.connectors import egress as _egress_mod

        p_decimate = sub.add_parser(
            "decimate", help="Write/egress data to destinations"
        )
        dec_sub = p_decimate.add_subparsers(dest="decimate_cmd", required=True)
        _egress_mod.register_cli(dec_sub)
    except (ImportError, AttributeError):  # pragma: no cover
        pass

    # transform
    try:
        import datavizhub.transform as _transform_mod

        p_tr = sub.add_parser("transform", help="Transform helpers (metadata, etc.)")
        tr_sub = p_tr.add_subparsers(dest="transform_cmd", required=True)
        _transform_mod.register_cli(tr_sub)
    except (ImportError, AttributeError):  # pragma: no cover
        pass

    # run
    try:
        from datavizhub.pipeline_runner import register_cli_run as _register_run

        _register_run(sub)
    except (ImportError, AttributeError):  # pragma: no cover
        pass


def _collect_options(p: argparse.ArgumentParser) -> dict[str, object]:
    """Collect option help and tag path-like args.

    Backward-compat: values are strings unless a path-like is detected, in which case
    the value is an object: {"help": str, "path_arg": true}.
    """
    opts: dict[str, object] = {}
    for act in getattr(p, "_actions", []):  # type: ignore[attr-defined]
        if act.option_strings:
            # choose the long option if available, else the first one
            opt = None
            for s in act.option_strings:
                if s.startswith("--"):
                    opt = s
                    break
            if opt is None and act.option_strings:
                opt = act.option_strings[0]
            if opt:
                help_text = (act.help or "").strip()
                # Heuristic to detect path-like options
                names = set(act.option_strings)
                name_hint = any(
                    n.startswith(
                        (
                            "--input",
                            "--output",
                            "--output-dir",
                            "--frames",
                            "--frames-dir",
                            "--input-file",
                            "--manifest",
                        )
                    )
                    or n in {"-i", "-o"}
                    for n in names
                )
                meta = getattr(act, "metavar", None)
                meta_hint = False
                if isinstance(meta, str):
                    ml = meta.lower()
                    meta_hint = any(k in ml for k in ("path", "file", "dir"))
                is_path = bool(name_hint or meta_hint)
                # Additional metadata
                choices = list(getattr(act, "choices", []) or [])
                required = bool(getattr(act, "required", False))
                # Map argparse type to a simple string
                t = getattr(act, "type", None)
                type_str: str | None = None
                if is_path:
                    type_str = "path"
                elif t is int:
                    type_str = "int"
                elif t is float:
                    type_str = "float"
                elif t is str or t is None:
                    type_str = "str"
                else:
                    # Fallback to the name of the callable/type if available
                    type_str = getattr(t, "__name__", None) or str(t)

                # Default value (avoid argparse.SUPPRESS sentinel)
                default_val = getattr(act, "default", None)
                if default_val == argparse.SUPPRESS:  # type: ignore[attr-defined]
                    default_val = None
                # Emit object only if we have metadata beyond plain help (for backward compat)
                if (
                    is_path
                    or choices
                    or required
                    or type_str not in (None, "str")
                    or default_val is not None
                ):
                    obj: dict[str, object] = {"help": help_text}
                    if is_path:
                        obj["path_arg"] = True
                    if choices:
                        obj["choices"] = choices
                    if type_str:
                        obj["type"] = type_str
                    if required:
                        obj["required"] = True
                    if default_val is not None:
                        obj["default"] = default_val
                    opts[opt] = obj
                else:
                    opts[opt] = help_text
    return opts


def _traverse(parser: argparse.ArgumentParser, *, prefix: str = "") -> dict[str, Any]:
    """Recursively traverse subparsers to build a manifest mapping."""
    manifest: dict[str, Any] = {}
    # find subparsers actions
    sub_actions = [
        a
        for a in getattr(parser, "_actions", [])
        if a.__class__.__name__ == "_SubParsersAction"
    ]  # type: ignore[attr-defined]
    if not sub_actions:
        # Leaf command: collect options, description, doc, epilog, and groups
        name = prefix.strip()
        if name:  # skip root
            # Option groups: preserve group titles and option flags
            groups: list[dict[str, Any]] = []
            for grp in getattr(parser, "_action_groups", []):  # type: ignore[attr-defined]
                opts: list[str] = []
                for act in getattr(grp, "_group_actions", []):  # type: ignore[attr-defined]
                    if getattr(act, "option_strings", None):
                        # choose the long option if available, else the first one
                        long = None
                        for s in act.option_strings:
                            if s.startswith("--"):
                                long = s
                                break
                        opts.append(long or act.option_strings[0])
                if opts:
                    groups.append({"title": getattr(grp, "title", ""), "options": opts})
            manifest[name] = {
                "description": (parser.description or parser.prog or "").strip(),
                "doc": (parser.description or "") or "",
                "epilog": (getattr(parser, "epilog", None) or ""),
                "groups": groups,
                "options": _collect_options(parser),
            }
        return manifest

    for spa in sub_actions:  # type: ignore[misc]
        for name, subp in spa.choices.items():  # type: ignore[attr-defined]
            # Skip wizard and manifest generator to avoid recursion/noise
            if prefix == "" and name in {"wizard", "generate-manifest"}:
                continue
            manifest.update(_traverse(subp, prefix=f"{prefix} {name}"))
    return manifest


def build_manifest() -> dict[str, Any]:
    parser = argparse.ArgumentParser(prog="datavizhub")
    sub = parser.add_subparsers(dest="cmd", required=True)
    _safe_register_all(sub)
    return _traverse(parser)


def save_manifest(path: str) -> None:
    data = build_manifest()
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
