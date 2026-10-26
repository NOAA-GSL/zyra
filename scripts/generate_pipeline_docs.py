#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Generate the wiki's per-command args reference from the capabilities manifest.

Writes one page per stage plus an index, ready to paste into the wiki:

    CLI-Args-Reference.md
    Args-Acquire.md, Args-Process.md, ... (one per stage)

Companion to ``scripts/generate_pipeline_schema.py``; both read the same
committed manifest under ``zyra/wizard/zyra_capabilities/``, so the reference
and the schema cannot disagree about which commands exist.

Usage::

    poetry run python scripts/generate_pipeline_docs.py --out-dir ./wiki
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from zyra.core.capabilities_loader import load_capabilities  # noqa: E402
from zyra.pipeline_schema import (  # noqa: E402
    STAGE_ALIASES,
    STAGE_POSITIONALS,
    capabilities_dir,
)
from zyra.stage_utils import normalize_stage_name  # noqa: E402

STAGE_ORDER = [
    "acquire",
    "process",
    "simulate",
    "decide",
    "visualize",
    "narrate",
    "verify",
    "decimate",
]
STAGE_BLURB = {
    "acquire": "Fetch bytes from a remote or local source into the pipeline.",
    "process": "Decode, subset, convert, reproject, or enrich data and metadata.",
    "simulate": "Generate synthetic or sampled data.",
    "decide": "Choose parameters or optimize a plan.",
    "visualize": "Render frames, plots, animations, or composed video.",
    "narrate": "Generate text/narrative products.",
    "verify": "Evaluate outputs against expectations.",
    "decimate": "Write results out to local disk, FTP, S3, HTTP POST, or Vimeo.",
}
SKIP_FLAGS = {"--help"}


def commands_by_stage() -> dict[str, dict[str, dict[str, Any]]]:
    """Return ``{canonical_stage: {command: meta}}``.

    The manifest repeats every command under each alias group
    (``visualize animate`` and ``render animate``). Prefer the entry keyed by
    the canonical stage so help text quotes the canonical invocation.
    """

    caps = load_capabilities(capabilities_dir())
    out: dict[str, dict[str, dict[str, Any]]] = {s: {} for s in STAGE_ORDER}
    for key, meta in caps.items():
        if not isinstance(key, str) or " " not in key:
            continue
        group, command = key.split(" ", 1)
        stage = normalize_stage_name(group)
        if stage not in out:
            continue
        if group == stage or command not in out[stage]:
            out[stage][command] = meta
    return out


def esc(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().replace("|", "\\|")


def opt_row(flag: str, meta: Any) -> tuple[str, str, str, str, str]:
    key = flag.lstrip("-").replace("-", "_")
    if isinstance(meta, str):
        return key, flag, "str", "", esc(meta)
    typ = meta.get("type") or "str"
    default = meta.get("default", "")
    default = "" if default in (None, "") else f"`{default}`"
    help_text = esc(meta.get("help", ""))
    if meta.get("choices"):
        joined = ", ".join(f"`{c}`" for c in meta["choices"])
        help_text = (help_text + " " if help_text else "") + f"Choices: {joined}"
    return key, flag, typ, default, help_text


def command_section(stage: str, command: str, meta: dict[str, Any]) -> str:
    lines = [f"### `{stage} {command}`\n"]
    desc = esc(meta.get("description") or meta.get("doc") or "")
    if desc:
        lines.append(desc + "\n")

    positionals = meta.get("positionals") or []
    mapped = STAGE_POSITIONALS.get((stage, command), ())
    unmapped_required = [
        p["name"] for p in positionals if p.get("required") and p["name"] not in mapped
    ]
    if positionals:
        lines.append("**Positionals**\n")
        lines.append("| Arg key | Required | Type | Usable in a pipeline stage? |")
        lines.append("| --- | --- | --- | --- |")
        for p in positionals:
            typ = p.get("type") or "str"
            if p.get("choices"):
                typ += " (" + ", ".join(f"`{c}`" for c in p["choices"]) + ")"
            usable = "yes" if p["name"] in mapped else "**no — see note**"
            required = "yes" if p.get("required") else "no"
            lines.append(f"| `{p['name']}` | {required} | {typ} | {usable} |")
        lines.append("")
    if unmapped_required:
        names = ", ".join(f"`{n}`" for n in unmapped_required)
        lines.append(
            "> **Not pipeline-addressable.** The runner has no positional "
            f"mapping for this command, so {names} would be emitted as a "
            "`--flag` and rejected by argparse. Use this command from the CLI, "
            "or open an issue to add the mapping.\n"
        )

    rows = [
        opt_row(flag, m)
        for flag, m in (meta.get("options") or {}).items()
        if flag not in SKIP_FLAGS
    ]
    if rows:
        lines.append("**Options**\n")
        lines.append("| Arg key | CLI flag | Type | Default | Description |")
        lines.append("| --- | --- | --- | --- | --- |")
        for key, flag, typ, default, help_text in rows:
            lines.append(f"| `{key}` | `{flag}` | {typ} | {default} | {help_text} |")
        lines.append("")

    notes = []
    if meta.get("stdin_arg"):
        notes.append(f'reads stdin via `{meta["stdin_arg"]}: "-"`')
    if meta.get("output_arg"):
        notes.append(f'writes via `{meta["output_arg"]}`')
    if notes:
        lines.append("**Chaining:** " + "; ".join(notes) + ".\n")

    example = meta.get("example_args")
    if isinstance(example, dict) and example:
        lines.append("**Example stage**\n")
        lines.append("```yaml")
        lines.append(f"- stage: {stage}")
        lines.append(f"  command: {command}")
        lines.append("  args:")
        for key, value in example.items():
            if isinstance(value, bool):
                rendered = "true" if value else "false"
            elif isinstance(value, list):
                rendered = "[" + ", ".join(str(v) for v in value) + "]"
            elif isinstance(value, str):
                rendered = f'"{value}"'
            else:
                rendered = value
            lines.append(f"    {key}: {rendered}")
        lines.append("```\n")
    return "\n".join(lines)


def stage_page(stage: str, commands: dict[str, dict[str, Any]], version: str) -> str:
    aliases = [a for a in STAGE_ALIASES[stage] if a != stage]
    head = [
        f"# Args Reference — `{stage}`\n",
        f"{STAGE_BLURB[stage]}\n",
        (
            "Aliases accepted for `stage:` — "
            + ", ".join(f"`{a}`" for a in aliases)
            + ".\n"
        )
        if aliases
        else "",
        f"Generated from Zyra **{version}**. See [Pipeline Schema](Pipeline-Schema) "
        "for how `args` keys become CLI flags.\n",
        "**Commands:** "
        + " · ".join(f"[`{c}`](#{stage}-{c})" for c in sorted(commands))
        + "\n",
        "---\n",
    ]
    body = [command_section(stage, c, commands[c]) for c in sorted(commands)]
    return "\n".join(part for part in head if part) + "\n".join(body)


def index_page(by_stage: dict[str, dict[str, dict[str, Any]]], version: str) -> str:
    total = sum(len(v) for v in by_stage.values())
    lines = [
        "# CLI Args Reference\n",
        f"Per-command argument reference for every stage command in Zyra "
        f"**{version}**, generated from the committed capabilities manifest "
        "rather than written by hand.\n",
        f"{total} commands across {len(STAGE_ORDER)} stages. For the file format "
        "itself — top-level keys, how `args` become flags, env expansion, `--set` "
        "overrides — see [Pipeline Schema](Pipeline-Schema).\n",
        "| Stage | Aliases | Commands | Page |",
        "| --- | --- | --- | --- |",
    ]
    for stage in STAGE_ORDER:
        aliases = ", ".join(f"`{a}`" for a in STAGE_ALIASES[stage] if a != stage) or "—"
        names = ", ".join(f"`{c}`" for c in sorted(by_stage[stage]))
        page = f"Args-{stage.capitalize()}"
        lines.append(f"| `{stage}` | {aliases} | {names} | [{page}]({page}) |")
    lines += [
        "",
        "## Regenerating\n",
        "```bash",
        "poetry run python scripts/generate_pipeline_docs.py --out-dir ./wiki",
        "```\n",
        "## Known gaps\n",
        "These commands declare a **required positional** that "
        "`zyra.pipeline_runner._build_argv_for_stage` does not map, so they "
        "cannot be driven from a pipeline stage at all:\n",
    ]
    for stage in STAGE_ORDER:
        for command, meta in sorted(by_stage[stage].items()):
            mapped = STAGE_POSITIONALS.get((stage, command), ())
            missing = [
                p["name"]
                for p in (meta.get("positionals") or [])
                if p.get("required") and p["name"] not in mapped
            ]
            if missing:
                joined = ", ".join(f"`{m}`" for m in missing)
                lines.append(f"- `{stage} {command}` — {joined}")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", type=Path, default=Path("wiki"))
    ap.add_argument(
        "--version",
        default=None,
        help="Version label for the page headers (default: installed Zyra version)",
    )
    ns = ap.parse_args(argv)

    version = ns.version
    if version is None:
        from importlib.metadata import PackageNotFoundError, version as pkg_version

        try:
            version = pkg_version("zyra")
        except PackageNotFoundError:
            version = "unknown"

    by_stage = commands_by_stage()
    ns.out_dir.mkdir(parents=True, exist_ok=True)
    (ns.out_dir / "CLI-Args-Reference.md").write_text(
        index_page(by_stage, version), encoding="utf-8"
    )
    for stage in STAGE_ORDER:
        (ns.out_dir / f"Args-{stage.capitalize()}.md").write_text(
            stage_page(stage, by_stage[stage], version), encoding="utf-8"
        )
    print(f"Wrote {len(STAGE_ORDER) + 1} pages to {ns.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
