# Narrate (Swarm) – Module Overview

This module provides a minimal multi‑agent “swarm” for narration/reporting with:

- CLI: `zyra narrate swarm` with presets (`-P/--preset`) and YAML config merging
- Orchestrator: lightweight concurrency + rounds with per‑agent provenance
- Pack schema: Pydantic models for `NarrativePack` validation and JSON/YAML I/O

Quick start

- List presets: `poetry run zyra narrate swarm -P help`
- Run a preset to stdout (YAML):
  `poetry run zyra narrate swarm -P kids_policy_basic --provider mock --pack -`
- Tutorial notebook: see `examples/narration_swarm.ipynb` for an end-to-end walkthrough (mock provider by default).

Key behaviors

- Presets live under `zyra.assets/llm/presets/narrate/*.yaml` and can be merged
  with `--swarm-config` and CLI flags (CLI overrides print a warning).
- Audience variants are produced by an internal `audience_adapter` agent when
  `--audiences` is set (emits `<aud>_version` outputs).
- Provenance is recorded per agent run and included in the Narrative Pack under
  `provenance[]` with fields: `agent`, `model`, `started`, `prompt_ref`, and
  `duration_ms`.

Validation and JSON Schema

- Validate programmatically with Pydantic (v2):

  ```python
  from zyra.narrate.schemas import NarrativePack

  pack = NarrativePack.model_validate(data_dict)
  # or, for JSON
  pack = NarrativePack.model_validate_json(json_str)
  ```

- Export JSON Schema for tooling/docs:

  ```python
  from zyra.narrate.schemas import NarrativePack
  schema = NarrativePack.model_json_schema()  # dict
  ```

- Write JSON Schema to disk:

  ```python
  import json
  from zyra.narrate.schemas import NarrativePack

  with open("narrative_pack.schema.json", "w", encoding="utf-8") as f:
      json.dump(NarrativePack.model_json_schema(), f, indent=2)
  ```

- Invariants enforced include:
  - `version == 0` (for v0)
  - When `status.completed` is false → at least one critical agent appears in
    `failed_agents` (`summary`, `critic`, or `editor`).

Exit Codes

- 0: success (pack written; non‑critical failures allowed)
- 1: critical path failed (summary/critic/editor); pack is still written when `--pack` is specified
- 2: config/validation errors (bad inputs; errors include failing field paths)

Notes

- The default provider is mock‑friendly and works offline. When credentials are
  set for providers (OpenAI/Ollama), generation uses those clients.
- Prompt templates for common roles are packaged under
  `zyra.assets/llm/prompts/narrate/` and referenced in provenance via
  `prompt_ref`.

Running property-based tests (Hypothesis)

- Install dev dependencies: `poetry install --with dev`
- Run narrate-related tests only: `poetry run pytest -q -k narrate`
- Run property tests specifically (they skip if Hypothesis is unavailable):
  `poetry run pytest -q tests/narrate/test_narrative_pack_hypothesis.py`
