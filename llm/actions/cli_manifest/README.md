Zyra CLI Manifest API (ChatGPT-friendly OpenAPI)

Purpose
- Minimal OpenAPI spec that exposes the Zyra CLI manifest (`zyra_capabilities.json`) directly from GitHub.
- Quick to import into ChatGPT Actions or similar tools to let an LLM inspect available CLI commands.

Usage (ChatGPT Actions)
- In ChatGPT → Actions → Create, supply a URL to this `openapi.yaml` (host from a raw URL in your fork or static hosting).
- Only the `/zyra_capabilities.json` endpoint is active (served by GitHub raw). The `/execute` endpoint is a placeholder and not hosted.

Notes
- Anonymous access works; GitHub raw applies rate limits. For higher limits or non-public use, host a copy of the manifest yourself.
- Source of truth for this Action lives here (`llm/actions/cli_manifest/`).

