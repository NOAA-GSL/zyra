Zyra CLI Manifest API (ChatGPT-friendly OpenAPI)

Purpose
- Minimal OpenAPI spec that exposes the Zyra CLI capabilities directory (starting from `zyra_capabilities/zyra_capabilities_index.json`) directly from GitHub.
- Quick to import into ChatGPT Actions or similar tools to let an LLM inspect available CLI commands.

Usage (ChatGPT Actions)
- In ChatGPT → Actions → Create, supply a URL to this `openapi.yaml` (host from a raw URL in your fork or static hosting).
- Endpoints (one per canonical domain):
  - `/zyra_capabilities/acquire.json` → acquire/import
  - `/zyra_capabilities/process.json` → process/transform
  - `/zyra_capabilities/visualize.json` → visualize/render
  - `/zyra_capabilities/disseminate.json` → disseminate/export/decimate
  - `/zyra_capabilities/transform.json` → transform helpers
  - `/zyra_capabilities/search.json` → dataset search
  - `/zyra_capabilities/run.json` → workflow runner
  - `/zyra_capabilities/simulate.json` → simulate
  - `/zyra_capabilities/decide.json` → decide/optimize
  - `/zyra_capabilities/narrate.json` → narrate/reporting
  - `/zyra_capabilities/verify.json` → verify/evaluate
- Each endpoint already includes the CLI aliases for that stage (e.g., `import` lives inside `acquire.json`, `render` inside `visualize.json`). See `zyra_capabilities_index.json` for the alias map if you need to reason about them explicitly.
- The `/execute` endpoint is a placeholder and not hosted.

Notes
- Anonymous access works; GitHub raw applies rate limits. For higher limits or non-public use, host a copy of the manifest yourself.
- Source of truth for this Action lives here (`llm/actions/cli_manifest/`).
