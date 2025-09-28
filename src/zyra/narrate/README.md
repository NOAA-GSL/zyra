# Narrate (Swarm) – Module Overview

This module provides a minimal multi‑agent “swarm” for narration/reporting with:

- CLI: `zyra narrate swarm` with presets (`-P/--preset`) and YAML config merging
- Orchestrator: lightweight concurrency + rounds with per‑agent provenance
- Pack schema: Pydantic models for `NarrativePack` validation and JSON/YAML I/O

Quick start

- List presets: `poetry run zyra narrate swarm -P help`
- Run a preset to stdout (YAML):
  `poetry run zyra narrate swarm -P kids_policy_basic --provider mock --pack -`
- Load a custom rubric:
  `poetry run zyra narrate swarm -P kids_policy_basic --rubric custom_rubric.yaml --pack -`
- Tutorial notebook: see `examples/narration_swarm.ipynb` for an end-to-end walkthrough (mock provider by default).

Key behaviors

- Presets live under `zyra.assets/llm/presets/narrate/*.yaml` and can be merged
  with `--swarm-config` and CLI flags (CLI overrides print a warning). CLI flags
  always take precedence over config/preset values.
- Audience variants are produced by an internal `audience_adapter` agent when
  `--audiences` is set (emits `<aud>_version` outputs).
- Provenance is recorded per agent run and included in the Narrative Pack under
  `provenance[]` with fields: `agent`, `model`, `started`, `prompt_ref`, and
  `duration_ms`.
- Critic safety rules come from a rubric. By default Zyra loads
  `zyra.assets/llm/rubrics/critic.yaml`; `--rubric <path>` lets callers inject a
  YAML list of rubric bullets. The resolved rubric path is echoed under
  `inputs.rubric` in the Narrative Pack.
- Flags such as `--strict-grounding`, `--critic-structured`, and
  `--attach-images` enable stricter review loops, structured critic notes, or
  multimodal prompts respectively. These options are also available through
  presets/YAML config and surfaced in the execution context.

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
- You can extend or replace agent prompts by supplying dictionaries in
  `--swarm-config` (or preset files). Each agent config supports keys such as
  `id`, `role`, `outputs`, `depends_on`, `params`, `prompt`, and `prompt_ref`.
  Prompts may be inline text, file paths, or packaged asset references. Invalid
  prompt/rubric paths cause the CLI to exit with status 2 and a clear message.
- The Narrative Pack `inputs` section records which preset and rubric were used
  so downstream consumers can reproduce the run or select matching presets.

Running property-based tests (Hypothesis)

- Install dev dependencies: `poetry install --with dev`
- Run narrate-related tests only: `poetry run pytest -q -k narrate`
- Run property tests specifically (they skip if Hypothesis is unavailable):
  `poetry run pytest -q tests/narrate/test_narrative_pack_hypothesis.py`
