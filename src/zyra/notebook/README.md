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

## LLM provider selection (notebook UX target)

- Start notebook with a provider selector cell (default `ollama`; also `openai`, `google/gemini`; fallback `mock` when creds missing).
- Document required env vars: `OLLAMA_BASE_URL`, `OPENAI_API_KEY`, `GOOGLE_API_KEY` (or Vertex vars).
- Swarm narration cell should summarize upcoming expected 2 m temperature from the HRRR subset; allow provider override via cell param.

## HRRR workflow (target for walkthrough notebook)

1. Acquire a small HRRR 2 m temperature subset via HTTP/NCSS (tight bbox/time to keep a few MB).
2. Process (subset/convert as needed).
3. Visualize or export.
4. Inline `process.register` demo.
5. Provenance export + `to_pipeline` / `to_cli`.
6. Narrate/swarm cell describing expected temperature (provider selector, mock-safe).

## Defaults and paths

- Workspace: `ZYRA_NOTEBOOK_DIR` -> `/kaggle/working` (if exists) -> `cwd`.
- Provenance: `ZYRA_NOTEBOOK_PROVENANCE` or `${workdir}/provenance.sqlite`.

## Limitations (current scaffolding)

- Wrappers call underlying CLI handlers directly with argparse-style namespaces; richer return handling and signature shaping to follow.
- Inline tool export is supported via stored callable metadata; serialized export for CLI replay is pending.
