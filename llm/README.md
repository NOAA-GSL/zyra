LLM Content (Repo-only)

Purpose
- Repository-local content for LLM tooling that does not need to be packaged
  with the Python distribution. Suitable for ChatGPT Actions, Open WebUI tools,
  experiments, and deployment artifacts.

Layout
- `prompts/`: System and task prompts for human or tool use.
- `actions/`: ChatGPT Action definitions (`ai-plugin.json`, `openapi.yaml`).
- `open-webui/`: Local Python tools and examples (not imported by `zyra`).
- `examples/`: Snippets (curl payloads, screenshots, config examples).

Open WebUI Tool Settings (Valves)
- Tools in `llm/open-webui/tools/` (e.g., `zyra_cli_manifest.py`) expose configurable Valves in the Open WebUI UI
  under Workspace → Tools → <tool> → Settings.
- Common valves for `zyra_cli_manifest`:
  - `zyra_api_base`: Base URL for Zyra API (default `http://localhost:8000`). The tool calls `GET /commands` with
    query params.
  - `zyra_api_key`: Optional API key; may be left blank.
  - `api_key_header`: Header to send the API key (default `X-API-Key`).
  - `api_timeout` / `net_timeout`: Short timeouts (seconds) for API and other HTTP fetches.
  - `caps_url`: Optional direct URL to the packaged capabilities assets (either the legacy `zyra_capabilities.json` or the new `zyra_capabilities/zyra_capabilities_index.json`). Used if the API is unreachable. May be blank.
  - `offline`: If true, skip all network fetches.
- If Settings doesn’t reflect new fields or optional status after a code update, re‑save (or remove/re‑add) the tool
  and refresh the page — some builds cache the previous schema.

See also
- `llm/open-webui/README.md` for usage notes and paste‑ready tool workflow.

Configuration
- Set `ZYRA_LLM_DIR` to override the default external LLM directory.
- Default lookup path can be `llm/` when no env var is provided.

Conventions
- No secrets; prefer env vars and documented config.
- Keep prompts small, composable, and versioned via filenames.
- Use relative paths; avoid absolute paths.
