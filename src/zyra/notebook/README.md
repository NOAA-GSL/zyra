# zyra.notebook (draft)

Notebook-friendly bridge for running Zyra stages inline, registering custom tools, logging provenance, and exporting reproducible pipelines.

## Quick start

```python
from zyra.notebook import create_session

# Optional: set env ZYRA_NOTEBOOK_DIR for workspace; defaults to /kaggle/working if present, else cwd.
sess = create_session()

# Acquire remote data (e.g., HTTP)
data = sess.acquire.http(url="https://example.com/file.bin")

# Register a custom tool
def smooth(ds):
    ...
sess.process.register("smooth", smooth, returns="object")
ds = sess.process.smooth(input=data)

# Export pipeline/CLI
pipeline = sess.to_pipeline()
cli_cmds = sess.to_cli()
```

## LLM provider selection (notebook cells)

- Provider selector cell sets `ZYRA_LLM_PROVIDER` and `LLM_MODEL`; defaults to Google Gemini Flash when creds exist, otherwise falls back to `mock` to stay runnable offline. Env vars: `GOOGLE_API_KEY`/Vertex vars, `OPENAI_API_KEY`, `OLLAMA_BASE_URL`.
- Verbosity: `ZYRA_VERBOSITY=debug` surfaces per-agent swarm logs in notebooks.
- Narrate cells honor `provider`/`model` overrides and will use mock when no creds are available.

## Provenance and export

- Workspace: `ZYRA_NOTEBOOK_DIR` -> `/kaggle/working` (if exists) -> `cwd`.
- Provenance DB: `ZYRA_NOTEBOOK_PROVENANCE` (defaults to `${workdir}/provenance.sqlite`). Inspect via the notebook “Inspect provenance SQLite logs” cell.
- Helpers: `sess.to_pipeline()` (stage/args JSON), `sess.to_cli()` (equivalent CLI strings). Narrate and planner calls can also log to provenance when `memory` is set (defaults to session DB).

## Interactive planner (notebook + inline)

- `sess.plan(...)` wraps `zyra plan`, with prompts enabled in notebooks; set `force_prompt=False` to disable.
- Inline planner cell (`plan_session_inline.json`) prompts for missing args, runs the value engine, and auto-inserts frame scan/pad steps and dependencies for compose/local.
- Value-engine suggestions are shown and can be accepted/rejected interactively; accepted suggestions are recorded in the manifest.

## Narrate/swarm (notebook cells)

- Narrate rerun cell builds frames/location bullets, sets a rubric, runs `sess.narrate.swarm`, and prints raw/edited outputs plus the pack/provenance.
- Input preview and agent outputs are surfaced in `narrate_pack.yaml`; final narration prefers the edited output.

## Limitations (current scaffolding)

- Wrappers call underlying CLI handlers directly with argparse-style namespaces; richer return handling and signature shaping to follow.
- Inline tool export is supported via stored callable metadata; serialized export for CLI replay is pending.
