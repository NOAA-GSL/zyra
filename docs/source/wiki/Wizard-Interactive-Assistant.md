## Overview
The Wizard is an interactive and one‑shot assistant that turns natural‑language requests into runnable `zyra` CLI commands. It can preview suggested commands, ask for confirmation, and execute them in sequence.

- Command: `zyra wizard`
- Modes: interactive REPL or one‑shot via `--prompt`
- Providers: OpenAI, Ollama, or a network‑free mock

This implements the MVP for the interactive assistant. For current scope and status, see Roadmap-and-Tracking.md.

## Quick Start
- Interactive:
  - `zyra wizard`
- One‑shot:
  - `zyra wizard --prompt "Convert hrrr.grib2 to NetCDF." --dry-run`

## Options
- `--prompt TEXT`: One‑shot query; without it, starts interactive mode.
- `--provider {openai,ollama,mock}`: LLM backend (default: `openai`).
- `--model NAME`: Model name override for the selected provider.
- `--dry-run`: Show suggested commands but do not execute them.
- `-y, --yes`: Auto‑confirm execution without prompting.
- `--max-commands N`: Limit the number of commands to run.
- `--log`: Log prompts, replies, and command executions to `~/.zyra/wizard_logs/*.jsonl`.
- `--log-raw-llm`: Include the full raw LLM response in logs.
- `--show-raw`: Print the full raw LLM output to stdout before parsing.
- `--explain`: Show suggested commands with inline `#` comments preserved (preview only).
- `--test-llm`: Probe connectivity to the configured LLM provider and exit.
- `--edit`: Always open an editor to modify commands before run (edit‑before‑run).
- `--no-edit`: Never open the editor; run/cancel only.
- `--interactive`: Ask for missing required arguments in one‑shot mode.

## Providers & Environment
- OpenAI
  - Requires `OPENAI_API_KEY`.
  - Optional: `OPENAI_BASE_URL` (default: `https://api.openai.com/v1`).
  - If credentials/network are unavailable, Wizard falls back to a safe mock suggestion and does not crash.
- Ollama
  - Requires a local Ollama server (default base URL: `http://localhost:11434`).
  - Override with `OLLAMA_BASE_URL`.
- Mock (offline)
  - No network, returns simple deterministic suggestions for testing.

Additional env overrides:
- `ZYRA_LLM_PROVIDER`: default provider (`openai`, `ollama`, or `mock`).
- `ZYRA_LLM_MODEL`: default model name for the chosen provider.

## Configuration & Precedence
Wizard supports three levels of configuration. Highest priority wins:

1) CLI flags (per-invocation)
- `--provider openai|ollama|mock`
- `--model NAME`

2) Environment variables (good for CI/CD)
- `ZYRA_LLM_PROVIDER` (e.g., `mock` for reproducible tests)
- `ZYRA_LLM_MODEL`
- Provider-specific: `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OLLAMA_BASE_URL`

3) Config file (persistent defaults)
- Path: `~/.zyra_wizard.yaml`
- Keys:
  - `provider`: `openai`, `ollama`, or `mock`
  - `model`: model name string

Example `~/.zyra_wizard.yaml`:
```
provider: mock
model: mistral
```

Examples of precedence:
- Config sets `provider: openai`, but CI exports `ZYRA_LLM_PROVIDER=mock` → mock is used.
- Env sets `ZYRA_LLM_PROVIDER=openai`, user passes `--provider ollama` → ollama is used.

## How It Works
1. Wizard sends your prompt to the selected provider (or mock) with system guidance.
2. It extracts `zyra ...` commands (supports multiple fenced blocks, and bash prompts like `$ zyra...`). Inline `#` comments outside quotes are stripped.
3. Safety: only `zyra ...` lines are accepted for execution; any other lines are ignored.
4. In `--dry-run` mode, it prints the commands only (no session state changes). With execution, it asks for confirmation (unless `-y`) and runs commands sequentially using the internal CLI entrypoint.
5. Execution stops at the first non‑zero return code; that code is returned by `wizard`.

## Session Memory (Interactive)
Wizard maintains lightweight context across turns during interactive sessions:
- Tracks the last output file from suggested commands (via `--output`/`-o`).
- Shows suggested commands to the user before execution (unless `-y`).
- Feeds a short context header to the model on the next turn, e.g.:
  - `Last file: /path/to/previous_output.nc`
  - recent commands (up to 5).

This lets prompts like “make a heatmap” automatically refer to the prior result.

Notes:
- Session context is updated only when executing (non‑dry‑run) or during the interactive REPL as commands are run.
- Context is in‑memory for now; logs can be enabled with `--log`.

## Command History

Wizard keeps a command history you can browse and reuse.

- Persistent file: `~/.zyra/wizard_history` (JSONL)
  - One line per successful execution:
    ```json
    { "ts": "2025-08-20T12:34:56Z", "cmd": "zyra visualize heatmap --input x.nc --var temp" }
    ```
  - Corrupted lines are skipped on load with a warning.
  - Consecutive duplicates are deduplicated when loading.

- REPL helpers:
  - `:history [N]`: show history (optionally last N).
  - `!N` or `:retry N`: re-run the Nth command as-is.
  - `:edit N`: open the Nth command in the edit-before-run flow.
  - `:clear-history`: clear in-memory and persisted history.
  - `:save-history <file>`: export commands (one per line) for sharing.

Examples:
```
> :history 5
[1] zyra process subset --input a.nc --var t --output co.nc
[2] zyra visualize heatmap --input co.nc --var temp
> !2   # retry
> :edit 1   # edit before running
> :save-history history.txt
Saved 2 command(s) to /path/to/history.txt
```

## Usage Examples

- One‑shot (preview only):
  - `zyra wizard --provider mock --prompt "Convert hrrr.grib2 to NetCDF." --dry-run`

- One‑shot (execute with auto‑confirm, OpenAI):
  - `OPENAI_API_KEY=... zyra wizard --prompt "Subset HRRR to Colorado and make a heatmap." -y`

- Interactive (basic):
  - `zyra wizard`
  - Flow example:
    - `> subset HRRR to Colorado` → suggests `... --output co.nc`
    - `> make a heatmap` → suggests using `--input co.nc` automatically

- Config file (persistent defaults):
  - Create `~/.zyra_wizard.yaml`:
    ```yaml
    provider: mock
    model: mistral
    ```
  - Run one‑shot with defaults:
    - `zyra wizard --prompt "convert input.nc to GeoTIFF" --dry-run`

- Logging (JSONL events):
  - Minimal logging:
    - `zyra wizard --provider mock --prompt "convert" --dry-run --log`
  - Include raw LLM text:
    - `zyra wizard --provider mock --prompt "convert" --dry-run --log --log-raw-llm`

- Explain and Raw Output (preview aids):
  - Show raw model output first:
    - `zyra wizard --provider mock --prompt "convert" --dry-run --show-raw`
  - Preserve inline comments in preview (execution still strips them safely):
    - `zyra wizard --provider mock --prompt "subset then plot" --dry-run --explain`

### Sample JSONL Log
```json
{"schema_version":1,"session_id":"3f1c2a6b2bdf4e2f98d9a3a3d1e2c4ab","event_id":"2e7b1c3a4d5e6f708192a3b4c5d6e7f0","ts":"2025-08-19T18:25:43Z","type":"user_prompt","prompt":"convert","provider":"mock","model":null}
{"schema_version":1,"session_id":"3f1c2a6b2bdf4e2f98d9a3a3d1e2c4ab","event_id":"9a8b7c6d5e4f3a2b1c0d9e8f7a6b5c4d","ts":"2025-08-19T18:25:43Z","type":"dry_run","commands":["zyra process convert-format input.nc --format geotiff --output output.tif"],"provider":"mock","model":null}
{"schema_version":1,"session_id":"3f1c2a6b2bdf4e2f98d9a3a3d1e2c4ab","event_id":"0f1e2d3c4b5a69788776655443322110","ts":"2025-08-19T18:25:43Z","type":"result","returncode":0,"ok":true,"commands":["zyra process convert-format input.nc --format geotiff --output output.tif"],"provider":"mock","model":null}
```

## Logging
- Enable with `--log`. Logs are written to `~/.zyra/wizard_logs/YYYYMMDDTHHMMSSZ.jsonl`.
- Each line is JSON with structured events to aid debugging and replay:
  - Common fields on every event: `schema_version: 1`, `session_id`, and unique `event_id` (UUIDs) for correlation.
  - `user_prompt`: includes `provider` and `model` used.
  - `assistant_reply` (optional): includes raw LLM text when `--log-raw-llm` is set.
  - `dry_run`: records suggested `commands` without execution.
  - `exec`: per-command execution with `cmd`, `returncode`, `ok`, `provider`, `model`.
  - `result`: summary of the whole turn with `returncode`, `ok`, `commands`, `provider`, `model`.
- Toggle raw LLM capture with `--log-raw-llm` (off by default to reduce noise and avoid storing sensitive model output inadvertently).

## Capabilities Manifest
The Wizard can ground suggestions using a structured capabilities manifest that lists available commands and their options.

- Generation:
  - `poetry run zyra generate-manifest` (writes canonical per-domain files under `src/zyra/wizard/zyra_capabilities/`).
  - Pass `--legacy-json` (default) to also refresh `src/zyra/wizard/zyra_capabilities.json` for older tools.
  - Use `-o /path/to/dir` or `-o /path/to/file.json` to override destinations.
  - Note: Regenerate whenever CLI commands or options change so assistants/tools stay in sync.
- Packaging: The manifest directory `src/zyra/wizard/zyra_capabilities/` (plus the optional legacy JSON when enabled) is bundled with the package.
- Usage in Wizard: On each turn, Wizard loads the manifest (if present), selects relevant entries by keyword match against the user prompt, and prepends a short context like:
  - `- Relevant commands:`
  - `  - visualize heatmap: Generate heatmap images. Options: --input, --var, --output`

This keeps prompts short, accurate, and focused on commands likely to be needed.

If the model suggests no runnable commands, the Wizard emits a minimal, safe default that
encourages interactive argument resolution (e.g., a heatmap or time‑series visualization
with placeholder arguments).

## Manifest Schema (Draft)
Consumers should support both legacy and enriched forms for backward compatibility.

- Top-level: object mapping full command strings to metadata.
- Command object:
  - `description`: short text
  - `options`: mapping of flag → value

Option entry formats
- Simple string (legacy):
  ```json
  "--flag": "help text"
  ```

- Rich object (enriched):
  ```json
  "--output": {
    "help": "Path to write output file",
    "path_arg": true,
    "type": "path",
    "choices": ["geotiff", "netcdf"],
    "required": false
  }
  ```

Field semantics
- `help`: human-readable help string.
- `path_arg` (bool): the next token is a filesystem path; Wizard uses this to enable file path completion.
- `type` (string): basic type of the argument; values may include `int`, `float`, `str`, `path`, or a callable/type name.
- `choices` (array): enum of acceptable values as exposed by argparse.
- `required` (bool): option must be provided (rare for short flags but included for completeness).

### Example: Before → After

Before (legacy):
```json
{
  "visualize heatmap": {
    "description": "zyra visualize heatmap",
    "options": {
      "--input": "Path to .nc or .npy input",
      "--output": "Output PNG path"
    }
  }
}
```

After (enriched):
```json
{
  "visualize heatmap": {
    "description": "zyra visualize heatmap",
    "options": {
      "--input": {"help": "Path to .nc or .npy input", "path_arg": true, "type": "path"},
      "--output": {"help": "Output PNG path", "path_arg": true, "type": "path"},
      "--cmap": {"help": "", "choices": ["viridis", "plasma", "inferno", "magma"], "type": "str", "default": "viridis"}
    }
  }
}
```

### How Wizard Uses `path_arg`
- The REPL completer detects options marked with `path_arg: true` and invokes a path completer for the next token.
- When `path_arg` is absent, Wizard falls back to a small heuristic set (e.g., `--input`, `--output`) to maintain compatibility with older manifests.

### Incremental Adoption
- Producers may emit a mix of string and object entries; consumers must handle both.
- Additional fields (`choices`, `type`, `required`) are optional and can be adopted as needed by clients and UIs.

### Groups and Defaults
- Each command may include `groups`: a list of `{ title, options[] }` reflecting argparse groups
  such as “Input Options” or “Output Options”.
- Enriched option entries may include `default`. Completers and UIs can display these
  in tooltips (e.g., `--cmap (default: viridis)`).

## Limitations (MVP)
- The LLM must output explicit `zyra` commands; Wizard does not synthesize flags/arguments on its own beyond parsing.
- Safety is basic (confirm or `--dry-run`). No sandbox or permission checks beyond what the underlying CLI performs.
 - None on persistence: config file is supported (`~/.zyra_wizard.yaml`).

## Roadmap
- Interactive session memory (retain context between prompts).
 - Config UX enhancements (validation, helpful errors).
- Enhanced parsing and validation of suggested commands.
- Expanded provider options and improved offline behavior.
- Command explanations and optimization suggestions.

## Troubleshooting
- “No zyra commands were suggested.”
  - Ask the model to output runnable commands in a fenced code block.
- Provider errors (network/credentials):
  - Wizard falls back to mock suggestions and continues; set `--provider mock` to avoid network entirely.
- Nothing happens on execute:
  - Try `--dry-run` to inspect commands; then run with `-y`.
Note on semantic dataset search
-------------------------------

Semantic dataset discovery now lives under the `search` command for a more natural fit:

- Use: `zyra search --semantic "your dataset request" --limit 10 --show-plan`.
- Wizard `--semantic` remains available for compatibility, but new workflows should prefer `zyra search --semantic`.
