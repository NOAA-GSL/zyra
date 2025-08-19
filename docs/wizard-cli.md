# DataVizHub Wizard REPL

The Wizard is an interactive assistant that suggests and runs `datavizhub` CLI commands.

- Autocomplete: When `prompt_toolkit` is installed (via extra `wizard`), the REPL offers
  completions for command names, common options, and file paths for `--input/--output`.
- Edit-before-run: After suggestions, choose to run, edit, or cancel. Edited commands
  are re‑sanitized to keep only `datavizhub ...` lines and strip inline `#` comments.

Flags and env vars
- `--edit`: always open the editor before running.
- `--no-edit`: skip edit prompt and run/cancel only.
- `DATAVIZHUB_WIZARD_EDITOR_MODE`: `always`, `never`, or `prompt` (default).

Editor behavior
- If `prompt_toolkit` is available: inline multi‑line edit buffer.
- Else: `$VISUAL`/`$EDITOR` is used if set; otherwise a simple stdin multi‑line prompt.

Install
- `poetry install -E wizard` or `pip install 'datavizhub[wizard]'`.

