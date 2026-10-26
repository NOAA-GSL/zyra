# SPDX-License-Identifier: Apache-2.0
"""JSON Schema for ``zyra run`` configurations.

``zyra run`` accepts two document shapes:

* a **pipeline** — a ``stages:`` list executed in order, stdout piped to stdin
* a **workflow** — ``jobs:`` with ``needs:`` dependencies and ``on.schedule``
  cron triggers

This module builds a draft 2020-12 JSON Schema covering both, so editors, CI,
and downstream services can validate a config before it is run.

The schema is derived from the **committed** capabilities manifest under
``zyra/wizard/zyra_capabilities/`` rather than from live argparse
introspection. That keeps generation deterministic: optional extras (e.g.
``pydantic`` for ``narrate``) change what ``build_manifest()`` can see at
runtime, but not what is committed.

The generated artifact is packaged at
``zyra/assets/schemas/zyra-pipeline.schema.json`` and can be read with
:func:`load_schema` without regenerating it.
"""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any

from zyra.core.capabilities_loader import load_capabilities
from zyra.stage_utils import normalize_stage_name

SCHEMA_FILENAME = "zyra-pipeline.schema.json"
SCHEMA_ID = (
    "https://raw.githubusercontent.com/NOAA-GSL/zyra/main/"
    "src/zyra/assets/schemas/zyra-pipeline.schema.json"
)

#: Canonical stage name -> every alias accepted for ``stage:``.
#: Kept in sync with :func:`zyra.pipeline_runner._stage_group_alias` by
#: ``tests/test_pipeline_schema.py``.
STAGE_ALIASES: dict[str, tuple[str, ...]] = {
    "acquire": ("acquire", "acquisition", "import", "ingest"),
    "process": ("process", "processing", "transform"),
    "simulate": ("simulate",),
    "decide": ("decide", "optimize"),
    "visualize": ("visualize", "visualization", "render"),
    "narrate": ("narrate",),
    "verify": ("verify",),
    "decimate": ("decimate", "decimation", "export", "disseminate"),
}

#: (canonical stage, command) -> args consumed as positionals, in order.
#: Mirrors the positional table in
#: :func:`zyra.pipeline_runner._build_argv_for_stage`; a command absent here
#: cannot receive a positional from a pipeline stage, because every remaining
#: arg is emitted as ``--kebab-case``. Kept honest by
#: ``test_positionals_match_runner``.
STAGE_POSITIONALS: dict[tuple[str, str], tuple[str, ...]] = {
    ("acquire", "http"): ("url",),
    ("acquire", "ftp"): ("path",),
    ("process", "convert-format"): ("file_or_url", "format"),
    ("process", "decode-grib2"): ("file_or_url",),
    ("process", "extract-variable"): ("file_or_url", "pattern"),
    ("decimate", "local"): ("path",),
    ("decimate", "ftp"): ("path",),
    ("decimate", "post"): ("url",),
}


def capabilities_dir() -> Path:
    """Return the packaged capabilities manifest directory."""

    return Path(str(resources.files("zyra.wizard") / "zyra_capabilities"))


def schema_path() -> Path:
    """Return the packaged schema artifact path."""

    return Path(str(resources.files("zyra") / "assets" / "schemas" / SCHEMA_FILENAME))


def load_schema() -> dict[str, Any]:
    """Load the packaged schema artifact."""

    return json.loads(schema_path().read_text(encoding="utf-8"))


def commands_by_stage(
    capabilities: dict[str, Any] | None = None,
) -> dict[str, list[str]]:
    """Return ``{canonical_stage: [command, ...]}`` from the manifest.

    Alias groups (``import``/``render``/``export``/...) collapse into their
    canonical stage; non-stage top-level commands (``run``, ``search``) are
    ignored.
    """

    caps = (
        capabilities
        if capabilities is not None
        else load_capabilities(capabilities_dir())
    )
    out: dict[str, set[str]] = {stage: set() for stage in STAGE_ALIASES}
    for key in caps:
        if not isinstance(key, str) or " " not in key:
            continue
        group, command = key.split(" ", 1)
        stage = normalize_stage_name(group)
        if stage in out:
            out[stage].add(command)
    return {stage: sorted(names) for stage, names in out.items()}


def _stage_rules(by_stage: dict[str, list[str]]) -> list[dict[str, Any]]:
    """Constrain ``command`` to the commands valid for the given ``stage``."""

    rules: list[dict[str, Any]] = []
    for stage, commands in by_stage.items():
        aliases = list(STAGE_ALIASES[stage])
        # `stage: acquire` + `args.backend: http` selects the subcommand, so the
        # group name itself is a legal `command` value.
        allowed = sorted(set(commands) | set(aliases))
        rules.append(
            {
                "if": {
                    "properties": {"stage": {"enum": aliases}},
                    "required": ["stage"],
                },
                "then": {"properties": {"command": {"enum": allowed}}},
            }
        )
    return rules


def _positional_rules(capabilities: dict[str, Any]) -> list[dict[str, Any]]:
    """Require positional args that the runner maps and the CLI requires."""

    rules: list[dict[str, Any]] = []
    for (stage, command), names in sorted(STAGE_POSITIONALS.items()):
        meta = capabilities.get(f"{stage} {command}") or {}
        if not meta:
            # Alias-keyed manifests (e.g. `disseminate local`) still describe the
            # same command; fall back to the first alias that resolves.
            for alias in STAGE_ALIASES[stage]:
                meta = capabilities.get(f"{alias} {command}") or {}
                if meta:
                    break
        required = [
            p["name"]
            for p in (meta.get("positionals") or [])
            if p.get("required") and p.get("name") in names
        ]
        if not required:
            continue
        rules.append(
            {
                "if": {
                    "properties": {
                        "stage": {"enum": list(STAGE_ALIASES[stage])},
                        "command": {"const": command},
                    },
                    "required": ["stage", "command"],
                },
                "then": {
                    "properties": {"args": {"required": required}},
                    "required": ["args"],
                },
            }
        )
    return rules


def build_schema(capabilities: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build the JSON Schema for ``zyra run`` configurations."""

    caps = (
        capabilities
        if capabilities is not None
        else load_capabilities(capabilities_dir())
    )
    by_stage = commands_by_stage(caps)
    all_aliases = sorted({a for aliases in STAGE_ALIASES.values() for a in aliases})

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": SCHEMA_ID,
        "title": "Zyra run configuration",
        "description": (
            "Validates any file accepted by `zyra run`: a pipeline config "
            "(`stages:`) or a workflow config (`jobs:` / `on:`). Generated from "
            "the committed capabilities manifest by "
            "scripts/generate_pipeline_schema.py."
        ),
        "type": "object",
        # Dispatch on the discriminating key rather than a bare oneOf, so
        # validators report the offending field instead of
        # "is not valid under any of the given schemas".
        "allOf": [
            {
                "anyOf": [{"required": ["stages"]}, {"required": ["jobs"]}],
                "$comment": (
                    "A config must define either 'stages' (pipeline) or 'jobs' "
                    "(workflow)."
                ),
            },
            {"if": {"required": ["stages"]}, "then": {"$ref": "#/$defs/pipeline"}},
            {"if": {"required": ["jobs"]}, "then": {"$ref": "#/$defs/workflow"}},
        ],
        "$defs": {
            "pipeline": {
                "type": "object",
                "title": "Pipeline config",
                "required": ["stages"],
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Human-readable label. Not used by the runner.",
                    },
                    "description": {"type": "string"},
                    "stages": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"$ref": "#/$defs/stage"},
                    },
                },
                "additionalProperties": True,
            },
            "stage": {
                "type": "object",
                "title": "Pipeline stage",
                "required": ["stage", "command"],
                "properties": {
                    "stage": {
                        "type": "string",
                        "enum": all_aliases,
                        "description": "Stage name or alias; normalized by _stage_group_alias().",
                    },
                    "command": {
                        "type": "string",
                        "description": "Subcommand within the stage.",
                    },
                    "id": {
                        "type": "string",
                        "description": "Optional label echoed by --print-argv-format=json.",
                    },
                    "args": {"$ref": "#/$defs/args"},
                },
                "additionalProperties": False,
                "allOf": _stage_rules(by_stage) + _positional_rules(caps),
            },
            "args": {
                "type": "object",
                "description": (
                    "Mapping of argument name to value. Keys become "
                    "`--kebab-case` flags unless the runner maps them to a "
                    "positional. Nested objects are not supported."
                ),
                "additionalProperties": {"$ref": "#/$defs/argValue"},
                "propertyNames": {"pattern": "^[A-Za-z_][A-Za-z0-9_-]*$"},
            },
            "argValue": {
                "oneOf": [
                    {"type": "string"},
                    {"type": "number"},
                    {"type": "boolean"},
                    {"type": "null"},
                    {
                        "type": "array",
                        "items": {"type": ["string", "number", "boolean"]},
                        "description": "Expanded to a multi-valued flag: `--inputs a b`.",
                    },
                ]
            },
            "workflow": {
                "type": "object",
                "title": "Workflow config",
                "description": (
                    "GitHub-Actions-shaped config with triggers and dependent jobs."
                ),
                "required": ["jobs"],
                "properties": {
                    "name": {"type": "string"},
                    "on": {"$ref": "#/$defs/on"},
                    "env": {
                        "type": "object",
                        "description": (
                            "Exported into the process environment before jobs "
                            "run, after ${VAR} expansion. Values that still look "
                            "unresolved are skipped rather than exported."
                        ),
                        "additionalProperties": {
                            "type": ["string", "number", "boolean"]
                        },
                    },
                    "jobs": {
                        "type": "object",
                        "minProperties": 1,
                        "additionalProperties": {"$ref": "#/$defs/job"},
                    },
                },
                "additionalProperties": True,
            },
            "on": {
                "type": "object",
                "description": (
                    "Trigger section. NOTE: PyYAML parses a bare `on:` key as "
                    'boolean true; Zyra accepts both. Quote it (`"on":`) for '
                    "portable validation."
                ),
                "properties": {
                    "schedule": {
                        "type": "array",
                        "items": {
                            "oneOf": [
                                {
                                    "type": "object",
                                    "required": ["cron"],
                                    "properties": {"cron": {"type": "string"}},
                                },
                                {"type": "string"},
                            ]
                        },
                    }
                },
                "additionalProperties": True,
            },
            "job": {
                "type": "object",
                "required": ["steps"],
                "properties": {
                    "needs": {
                        "oneOf": [
                            {"type": "string"},
                            {"type": "array", "items": {"type": "string"}},
                        ],
                        "description": (
                            "Job names that must succeed first. Cycles are rejected."
                        ),
                    },
                    "steps": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"$ref": "#/$defs/step"},
                    },
                },
                "additionalProperties": True,
            },
            "step": {
                "oneOf": [
                    {
                        "type": "string",
                        "description": (
                            "Shell-style argv, split with shlex: "
                            "`process convert-format - netcdf --stdout`."
                        ),
                    },
                    {
                        "type": "object",
                        "required": ["cmd"],
                        "properties": {"cmd": {"type": "string"}},
                        "additionalProperties": False,
                    },
                    {"$ref": "#/$defs/stage"},
                ]
            },
        },
    }


def render_schema(capabilities: dict[str, Any] | None = None) -> str:
    """Return the schema serialized exactly as the committed artifact."""

    return json.dumps(build_schema(capabilities), indent=2, sort_keys=False) + "\n"


__all__ = [
    "SCHEMA_FILENAME",
    "SCHEMA_ID",
    "STAGE_ALIASES",
    "STAGE_POSITIONALS",
    "build_schema",
    "capabilities_dir",
    "commands_by_stage",
    "load_schema",
    "render_schema",
    "schema_path",
]
