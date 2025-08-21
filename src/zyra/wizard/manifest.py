from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
from typing import Any

# Top-level commands to exclude when building the capabilities manifest.
# These are internal helpers or would cause recursion/noise in the manifest.
EXCLUDED_ROOT_COMMANDS: set[str] = {"wizard", "generate-manifest"}


def _safe_add_group(
    sub: argparse._SubParsersAction,
    *,
    name: str,
    help_text: str,
    dest: str,
    import_path: str,
    register_attr: str = "register_cli",
) -> None:
    """Import module and register a command group safely.

    Creates the parser/subparsers, then calls module.<register_attr>(subparsers).
    Silently ignores ImportError/AttributeError to support optional extras.
    """
    try:
        mod = importlib.import_module(import_path)
        registrar = getattr(mod, register_attr)
        p = sub.add_parser(name, help=help_text)
        sp = p.add_subparsers(dest=dest, required=True)
        registrar(sp)
    except (ImportError, AttributeError):  # pragma: no cover - optional extras
        return


def _safe_call_register(
    sub: argparse._SubParsersAction, *, import_path: str, func_name: str
) -> None:
    """Import a module and call a registration function with subparsers.

    Used for commands that register directly on the root subparsers.
    """
    try:
        mod = importlib.import_module(import_path)
        registrar = getattr(mod, func_name)
        registrar(sub)
    except (ImportError, AttributeError):  # pragma: no cover
        return


def _safe_register_all(sub: argparse._SubParsersAction) -> None:
    """Register all top-level groups, skipping modules that fail to import.

    Matches the fallback branch in zyra.cli but wraps imports in try/except
    to avoid hard-failing when optional extras (e.g., cartopy) are missing.
    """
    # acquire
    _safe_add_group(
        sub,
        name="acquire",
        help_text="Acquire/ingest data from sources",
        dest="acquire_cmd",
        import_path="zyra.connectors.ingest",
    )

    # process
    _safe_add_group(
        sub,
        name="process",
        help_text="Processing commands (GRIB/NetCDF/GeoTIFF)",
        dest="process_cmd",
        import_path="zyra.processing",
    )

    # visualize
    # Use lightweight registrar to avoid importing heavy visualization root
    _safe_add_group(
        sub,
        name="visualize",
        help_text="Visualization commands (static/interactive/animation)",
        dest="visualize_cmd",
        import_path="zyra.visualization.cli_register",
    )

    # decimate
    _safe_add_group(
        sub,
        name="decimate",
        help_text="Write/egress data to destinations",
        dest="decimate_cmd",
        import_path="zyra.connectors.egress",
    )

    # transform
    _safe_add_group(
        sub,
        name="transform",
        help_text="Transform helpers (metadata, etc.)",
        dest="transform_cmd",
        import_path="zyra.transform",
    )

    # run
    _safe_call_register(
        sub, import_path="zyra.pipeline_runner", func_name="register_cli_run"
    )


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
                # Flag likely-sensitive fields (heuristic by name/help)
                name_l = " ".join(names).lower()
                help_l = help_text.lower()
                sensitive = any(
                    kw in name_l
                    for kw in (
                        "password",
                        "secret",
                        "token",
                        "api_key",
                        "apikey",
                        "access_key",
                        "client_secret",
                    )
                ) or any(
                    kw in help_l for kw in ("password", "secret", "token", "api key")
                )

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
                    if sensitive:
                        obj["sensitive"] = True
                    opts[opt] = obj
                else:
                    opts[opt] = help_text
    return opts


def _collect_positionals(p: argparse.ArgumentParser) -> list[dict[str, object]]:
    """Collect positional arguments in declaration order with basic metadata.

    Metadata includes: name, help, type (heuristic), required, choices, nargs.
    """
    items: list[dict[str, object]] = []
    for act in getattr(p, "_actions", []):  # type: ignore[attr-defined]
        if getattr(act, "option_strings", None):
            continue
        # Skip help or suppressed
        if getattr(act, "help", None) == argparse.SUPPRESS:
            continue
        # Name and help
        name = getattr(act, "dest", None) or getattr(act, "metavar", None) or "arg"
        help_text = (getattr(act, "help", None) or "").strip()
        # Infer type
        meta = getattr(act, "metavar", None)
        meta_s = str(meta).lower() if isinstance(meta, str) else ""
        t = getattr(act, "type", None)
        if any(k in meta_s for k in ("path", "file", "dir")):
            type_str = "path"
        elif t is int:
            type_str = "int"
        elif t is float:
            type_str = "float"
        elif t is str or t is None:
            type_str = "str"
        else:
            type_str = getattr(t, "__name__", None) or str(t)
        # Required heuristic: nargs of None or 1 implies required by default
        nargs = getattr(act, "nargs", None)
        required = True
        if nargs in ("?", "*"):
            required = False
        # Choices
        choices = list(getattr(act, "choices", []) or [])
        # Sensitive heuristic by name/help
        help_l = help_text.lower()
        name_l = str(name).lower()
        sensitive = any(
            kw in name_l for kw in ("password", "secret", "token", "api_key", "apikey")
        ) or any(kw in help_l for kw in ("password", "secret", "token", "api key"))

        entry: dict[str, object] = {
            "name": str(name),
            "help": help_text,
            "type": type_str,
            "required": required,
        }
        if choices:
            entry["choices"] = choices
        if nargs is not None:
            entry["nargs"] = nargs
        if sensitive:
            entry["sensitive"] = True
        items.append(entry)
    return items


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
                "positionals": _collect_positionals(parser),
            }
        return manifest

    for spa in sub_actions:  # type: ignore[misc]
        for name, subp in spa.choices.items():  # type: ignore[attr-defined]
            # Skip internal helpers and excluded commands at the root level
            if prefix == "" and name in EXCLUDED_ROOT_COMMANDS:
                continue
            manifest.update(_traverse(subp, prefix=f"{prefix} {name}"))
    return manifest


def build_manifest() -> dict[str, Any]:
    parser = argparse.ArgumentParser(prog="zyra")
    sub = parser.add_subparsers(dest="cmd", required=True)
    _safe_register_all(sub)
    return _traverse(parser)


def save_manifest(path: str) -> None:
    data = build_manifest()
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
