# SPDX-License-Identifier: Apache-2.0
"""Tests for the packaged ``zyra run`` JSON Schema.

Four things are checked:

1. the committed artifact matches what the generator produces (drift),
2. the alias table matches the runner's own stage normalization,
3. the positional table matches what the runner actually consumes positionally,
4. every sample config validates, and malformed configs are rejected.

(4) needs ``jsonschema``, which is not a declared dependency, so those tests
skip when it is unavailable. (1)-(3) always run.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from zyra.core.capabilities_loader import load_capabilities
from zyra.pipeline_runner import _build_argv_for_stage, _stage_group_alias
from zyra.pipeline_schema import (
    STAGE_ALIASES,
    STAGE_POSITIONALS,
    build_schema,
    capabilities_dir,
    render_schema,
    schema_path,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_DIRS = (REPO_ROOT / "samples" / "pipelines", REPO_ROOT / "samples" / "workflows")
SAMPLES = sorted(
    p
    for directory in SAMPLE_DIRS
    for p in directory.glob("*")
    if p.is_file() and p.suffix in {".yaml", ".yml", ".json"}
)

# Commands whose required positional the runner cannot express in a pipeline
# stage. Adding a command here should be a deliberate act: prefer teaching
# `_build_argv_for_stage` the mapping and adding it to STAGE_POSITIONALS.
KNOWN_UNMAPPED_POSITIONALS = {
    ("acquire", "thredds"): {"catalog_url"},
    ("acquire", "vimeo"): {"video_id"},
    ("process", "api-json"): {"file_or_url"},
    ("process", "audio-metadata"): {"input"},
    ("process", "audio-transcode"): {"input"},
    ("process", "video-transcode"): {"input"},
}


def test_schema_artifact_matches_generator() -> None:
    """The committed schema is current.

    Regenerate with: poetry run python scripts/generate_pipeline_schema.py
    """

    target = schema_path()
    assert target.exists(), f"Missing schema artifact: {target}"
    assert target.read_text(encoding="utf-8") == render_schema(), (
        "Schema artifact is stale. Run "
        "`poetry run python scripts/generate_pipeline_schema.py`."
    )


def test_schema_is_valid_json() -> None:
    data = json.loads(schema_path().read_text(encoding="utf-8"))
    assert data["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert data["$id"].endswith("zyra-pipeline.schema.json")


@pytest.mark.parametrize(
    ("canonical", "alias"),
    [(c, a) for c, aliases in STAGE_ALIASES.items() for a in aliases],
)
def test_stage_aliases_match_runner(canonical: str, alias: str) -> None:
    """STAGE_ALIASES agrees with the runner's own normalization."""

    assert _stage_group_alias(alias) == canonical


def test_every_manifest_stage_is_covered() -> None:
    """No stage in the manifest is missing from STAGE_ALIASES."""

    caps = load_capabilities(capabilities_dir())
    groups = {k.split(" ", 1)[0] for k in caps if isinstance(k, str) and " " in k}
    # `search` and `run` are top-level commands, not pipeline stages.
    stages = {_stage_group_alias(g) for g in groups} - {"search", "run"}
    assert stages <= set(
        STAGE_ALIASES
    ), f"Stages missing from STAGE_ALIASES: {sorted(stages - set(STAGE_ALIASES))}"


def _consumes_positionally(stage: str, command: str, arg: str) -> bool:
    """True when the runner emits ``arg``'s value as a bare argv element."""

    argv = _build_argv_for_stage(
        {"stage": stage, "command": command, "args": {arg: "PROBE"}}
    )
    flag = "--" + arg.replace("_", "-")
    return "PROBE" in argv and flag not in argv


def test_positionals_match_runner() -> None:
    """STAGE_POSITIONALS matches what the runner actually does.

    Also asserts that any command whose required positional the runner cannot
    map is a known gap, so a new one cannot appear silently.
    """

    caps = load_capabilities(capabilities_dir())
    unmapped: dict[tuple[str, str], set[str]] = {}

    for key, meta in caps.items():
        if not isinstance(key, str) or " " not in key:
            continue
        group, command = key.split(" ", 1)
        stage = _stage_group_alias(group)
        if stage not in STAGE_ALIASES:
            continue
        mapped = STAGE_POSITIONALS.get((stage, command), ())
        for positional in meta.get("positionals") or []:
            name = positional["name"]
            consumed = _consumes_positionally(group, command, name)
            assert consumed == (name in mapped), (
                f"{stage} {command}: arg {name!r} is "
                f"{'consumed' if consumed else 'not consumed'} positionally by the "
                f"runner but STAGE_POSITIONALS says otherwise"
            )
            if positional.get("required") and not consumed:
                unmapped.setdefault((stage, command), set()).add(name)

    assert unmapped == KNOWN_UNMAPPED_POSITIONALS, (
        "Set of commands with unmappable required positionals changed.\n"
        f"  now:      {sorted(unmapped.items())}\n"
        f"  expected: {sorted(KNOWN_UNMAPPED_POSITIONALS.items())}"
    )


def test_positional_order_is_preserved() -> None:
    """Multi-positional commands emit their args in the declared order."""

    for (stage, command), names in STAGE_POSITIONALS.items():
        if len(names) < 2:
            continue
        args = {name: f"P{i}" for i, name in enumerate(names)}
        argv = _build_argv_for_stage({"stage": stage, "command": command, "args": args})
        expected = [f"P{i}" for i in range(len(names))]
        assert (
            argv[2 : 2 + len(names)] == expected
        ), f"{stage} {command}: positional order {argv[2:]} != {expected}"


# --------------------------------------------------------------------------
# Validation against real documents (requires jsonschema)
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def validator():
    jsonschema = pytest.importorskip("jsonschema")
    schema = build_schema()
    jsonschema.Draft202012Validator.check_schema(schema)
    return jsonschema.Draft202012Validator(schema)


def _load_doc(path: Path):
    import yaml

    return yaml.safe_load(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("path", SAMPLES, ids=lambda p: p.name)
def test_samples_validate(validator, path: Path) -> None:
    doc = _load_doc(path)
    if not isinstance(doc, dict) or not ({"stages", "jobs"} & set(doc)):
        pytest.skip(f"{path.name} is not a run config")
    errors = sorted(validator.iter_errors(doc), key=lambda e: list(e.path))
    assert not errors, "\n".join(
        f"/{'/'.join(str(p) for p in e.path)}: {e.message}" for e in errors[:5]
    )


MALFORMED = {
    "unknown stage": {"stages": [{"stage": "acquiree", "command": "http"}]},
    "command not valid for stage": {
        "stages": [{"stage": "acquire", "command": "heatmap", "args": {"url": "x"}}]
    },
    "missing required positional": {
        "stages": [{"stage": "acquire", "command": "http", "args": {"output": "-"}}]
    },
    "nested object arg": {
        "stages": [
            {"stage": "acquire", "command": "http", "args": {"url": "x", "o": {"a": 1}}}
        ]
    },
    "args is not a mapping": {
        "stages": [{"stage": "acquire", "command": "http", "args": ["url"]}]
    },
    "unknown stage key": {
        "stages": [
            {"stage": "acquire", "command": "http", "args": {"url": "x"}, "retries": 3}
        ]
    },
    "empty stages": {"stages": []},
    "neither stages nor jobs": {"name": "nothing"},
    "job without steps": {"jobs": {"a": {"needs": "b"}}},
    "unrecognized step shape": {"jobs": {"a": {"steps": [{"nope": 1}]}}},
}


@pytest.mark.parametrize("name", sorted(MALFORMED))
def test_rejects_malformed(validator, name: str) -> None:
    assert list(validator.iter_errors(MALFORMED[name])), f"{name} should not validate"


WELL_FORMED = {
    "backend selects subcommand": {
        "stages": [
            {
                "stage": "acquire",
                "command": "acquire",
                "args": {"backend": "http", "url": "x"},
            }
        ]
    },
    "alias stage with id": {
        "stages": [
            {
                "stage": "decimation",
                "command": "local",
                "id": "out",
                "args": {"path": "/tmp/x", "input": "-"},
            }
        ]
    },
    "workflow with string steps": {
        "on": {"schedule": [{"cron": "5 12 * * 4"}]},
        "jobs": {"a": {"steps": ["acquire http https://x --output -"]}},
    },
    "list-valued arg": {
        "stages": [
            {
                "stage": "visualize",
                "command": "sos",
                "args": {"inputs": ["a.nc", "b.nc"], "vmin": 0, "vmax": 50},
            }
        ]
    },
}


@pytest.mark.parametrize("name", sorted(WELL_FORMED))
def test_accepts_well_formed(validator, name: str) -> None:
    errors = list(validator.iter_errors(WELL_FORMED[name]))
    assert not errors, errors[0].message
