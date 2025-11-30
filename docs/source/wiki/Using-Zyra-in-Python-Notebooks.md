# Using Zyra in Python Notebooks

## Overview
- Run Zyra stages directly in notebooks with `create_session()`.
- Register custom tools inline; they are exposed to the planner via a capabilities overlay.
- Provenance is logged to SQLite; pipelines/CLI equivalents can be exported.
- Narrate/swarm works in notebooks with provider selection and debug output.

## Setup
- Install: `poetry install --with dev` (or pip equivalents in your env).
- Env vars:
  - `ZYRA_NOTEBOOK_DIR` (workspace), `ZYRA_NOTEBOOK_PROVENANCE` (provenance DB, defaults under workspace).
  - LLM: `GOOGLE_API_KEY` (Gemini), `OPENAI_API_KEY`, `OLLAMA_BASE_URL`. Fallback is `mock` if none set.
  - Verbose swarm logs: `ZYRA_VERBOSITY=debug`.

## Quick start
```python
from zyra.notebook import create_session
sess = create_session()  # uses ZYRA_NOTEBOOK_DIR or cwd

# Acquire/process example
data = sess.acquire.http(url="https://example.com/file.bin")

# Register an inline tool (with templates for planner)
def smooth(ns): ...
sess.process.register(
    "smooth",
    smooth,
    returns="object",
    args_template={"input": "frames_padded"},
    outputs_template={"output": "analysis.json"},
)

# Export
print(sess.to_pipeline())
print(sess.to_cli())
```

## Inline tool overlay (planner integration)
- Registration writes `notebook_capabilities_overlay.json` in the workspace.
- Planner loads this overlay (env `ZYRA_NOTEBOOK_OVERLAY` set by session/notebook cells).
- Inline suggestions are labeled (e.g., `[inline: notebook_register]`); consent prompts include the origin.
- Overlays include templates (args/outputs) and inline serialization metadata; replay currently warns/skips if inline code is absent.

## Interactive planner flow (from notebook)
- `sess.plan(...)` wraps `zyra plan` with prompts enabled in notebooks; provenance goes to the session DB.
- Inline planner demo cell:
  - Prompts for missing args (FTP path/pattern, etc.).
  - Runs value engine; prints accepted vs. remaining suggestions.
  - Ensures scan/pad/compose/local wiring; saves plan to `plan_session_inline.json`.
- Replay example: `poetry run zyra swarm --plan /app/data/drought_notebook/plan_session_inline.json --stage acquire,process,visualize,decimate`.

## Narrate/swarm in notebooks
- Provider selector defaults to Gemini (if creds) → OpenAI → Ollama → mock.
- Narrate cell builds frame/location bullets, sets a rubric, runs `sess.narrate.swarm`, and logs pack/provenance.
- Input preview and agent outputs live in `narrate_pack.yaml`; final narration prefers the edited output.

## Provenance
- Default DB: `${ZYRA_NOTEBOOK_DIR}/provenance.sqlite` (configurable via `ZYRA_NOTEBOOK_PROVENANCE`).
- Inspect via notebook cell (tables, last events) or `zyra swarm --dump-memory <db>`.

## Notebook walkthrough highlights (drought example)
- Registers a custom drought-frame analyzer (overlay makes it plannable).
- Planner intent mentions analyzing frames; inline planner suggests the analyzer and wires dependencies.
- Plan outputs: `plan_session_inline.json`, overlays, provenance DB, and narrate packs.

## Security/guardrails
- Inline tools must be serializable; overlays warn and skip inline replay if code isn’t available.
- Consent prompts label inline origins before suggesting user code.
