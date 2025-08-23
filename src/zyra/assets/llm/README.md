LLM Assets (In-Package)

Purpose
- Versioned, distributable assets used by `zyra` at runtime.

Contents
- `prompts/`: System and task prompts (Markdown or YAML metadata + Markdown).
- `actions/`: Per-action folders for packaged definitions (e.g., ChatGPT Actions).
- `schemas/`: Shared JSON Schema or OpenAPI fragments.

Usage
- Access with `importlib.resources` to avoid absolute paths and support packaging:
  - Python: `from importlib import resources as ir; path = ir.files("zyra.assets").joinpath("llm/prompts/example_system.md")`

Conventions
- Prefer `.md` for prompt bodies; optional `.yaml` for metadata (name, version, tags).
- Keep filenames stable; treat content as part of the public CLI/API behavior.
- Do not embed secrets. Use environment variables or external configuration.

