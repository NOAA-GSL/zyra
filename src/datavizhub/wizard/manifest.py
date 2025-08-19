from __future__ import annotations

import argparse
import json
from typing import Any, Dict, List


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
    except Exception:  # pragma: no cover - optional extras might be missing
        pass

    # process
    try:
        from datavizhub import processing as _process_mod

        p_proc = sub.add_parser(
            "process", help="Processing commands (GRIB/NetCDF/GeoTIFF)"
        )
        proc_sub = p_proc.add_subparsers(dest="process_cmd", required=True)
        _process_mod.register_cli(proc_sub)
    except Exception:  # pragma: no cover
        pass

    # visualize
    try:
        from datavizhub import visualization as _visual_mod

        p_viz = sub.add_parser(
            "visualize", help="Visualization commands (static/interactive/animation)"
        )
        viz_sub = p_viz.add_subparsers(dest="visualize_cmd", required=True)
        _visual_mod.register_cli(viz_sub)
    except Exception:  # pragma: no cover - heavy deps may be missing
        pass

    # decimate
    try:
        from datavizhub.connectors import egress as _egress_mod

        p_decimate = sub.add_parser(
            "decimate", help="Write/egress data to destinations"
        )
        dec_sub = p_decimate.add_subparsers(dest="decimate_cmd", required=True)
        _egress_mod.register_cli(dec_sub)
    except Exception:  # pragma: no cover
        pass

    # transform
    try:
        import datavizhub.transform as _transform_mod

        p_tr = sub.add_parser("transform", help="Transform helpers (metadata, etc.)")
        tr_sub = p_tr.add_subparsers(dest="transform_cmd", required=True)
        _transform_mod.register_cli(tr_sub)
    except Exception:  # pragma: no cover
        pass

    # run
    try:
        from datavizhub.pipeline_runner import register_cli_run as _register_run

        _register_run(sub)
    except Exception:  # pragma: no cover
        pass


def _collect_options(p: argparse.ArgumentParser) -> Dict[str, str]:
    opts: Dict[str, str] = {}
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
                opts[opt] = (act.help or "").strip()
    return opts


def _traverse(parser: argparse.ArgumentParser, *, prefix: str = "") -> Dict[str, Any]:
    """Recursively traverse subparsers to build a manifest mapping."""
    manifest: Dict[str, Any] = {}
    # find subparsers actions
    sub_actions = [a for a in getattr(parser, "_actions", []) if a.__class__.__name__ == "_SubParsersAction"]  # type: ignore[attr-defined]
    if not sub_actions:
        # Leaf command: collect options and description
        name = prefix.strip()
        if name:  # skip root
            manifest[name] = {
                "description": (parser.description or parser.prog or "").strip(),
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


def build_manifest() -> Dict[str, Any]:
    parser = argparse.ArgumentParser(prog="datavizhub")
    sub = parser.add_subparsers(dest="cmd", required=True)
    _safe_register_all(sub)
    return _traverse(parser)


def save_manifest(path: str) -> None:
    data = build_manifest()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

