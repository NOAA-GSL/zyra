Open WebUI Tools

Purpose
- Local Python tools for Open WebUI or similar UIs. These are not imported by
  the `zyra` package and can have their own lightweight dependencies.

Recommended Workflows
- Single-file (paste into Open WebUI):
  1) Open Open WebUI → Workspace → Tools → New Tool.
  2) Paste the contents of `llm/open-webui/tools/zyra_cli_manifest.py` into the editor.
  3) Save. Open WebUI discovers the top-level `class Tools` automatically.

- Local multi-file (point Open WebUI at a folder):
  - Use `llm/open-webui/tools/` as the tool directory. It exposes a top-level
    `tools.py` with `class Tools`, delegating to `zyra_cli_manifest.py`.

Tool: zyra_cli_manifest
- File: `llm/open-webui/tools/zyra_cli_manifest.py` (paste-ready, single file)
- Provides: `Tools.zyra_cli_manifest(command_name=None, format="json", details=None)`
  - `format="list"` → just command names
  - `format="summary"` → names + descriptions
  - `format="json"` (default) → raw manifest JSON
  - Per-command: `command_name="..."` with `details="options" | "example"`

Tool: github_repo_access
- File: `llm/open-webui/tools/github_repo_access.py`
- Provides methods for GitHub repo browsing via API (default public `https://api.github.com`):
  - `Tools.github_get_file_or_directory(path, ref=None)` → file (auto-decodes base64) or directory listing
  - `Tools.github_list_commits(sha=None, per_page=None, page=None)` → recent commits
  - `Tools.github_list_file_commits(path, sha=None)` → commits for a file or path
  - `Tools.github_list_pull_requests(state=None, per_page=None, page=None)` → PRs
  - `Tools.github_list_branches(per_page=None, page=None)` → branches
  - `Tools.github_list_discussions(per_page=None, page=None)` / `Tools.github_get_discussion(number)`
  - `Tools.github_list_issues(state=None, per_page=None, page=None)` / `Tools.github_get_issue(number)`
  - `Tools.github_search_code(query, path=None, language=None, extension=None, per_page=None, page=None)` → code search scoped to the repo
  - Valves: `api_base` (default https://api.github.com), `owner` (NOAA-GSL), `repo` (zyra), `token` (optional), `timeout` (4.0s), `user_agent` (string)

Examples
- List commands: `{ "format": "list" }`
- Options for a command: `{ "command_name": "acquire http", "details": "options" }`
- Runnable example: `{ "command_name": "visualize heatmap", "details": "example" }`

Dependencies
- Install in your Open WebUI environment: `pip install -r llm/open-webui/requirements.txt`
- Or minimally: `pip install requests`

Configuration (optional)
- `ZYRA_API_BASE`: base URL for the Zyra API. Defaults to `http://localhost:8000` implicitly; the tool will try
  calling `/commands` first with a short timeout and fall back if unreachable.
- `ZYRA_CAPABILITIES_URL`: optional URL to fetch the manifest JSON if you want to bypass the API and GitHub.
- `ZYRA_API_BASE`: base URL for the Zyra API. If set, the tool calls the `/commands` endpoint for list/summary/json
  and command details. Ideal when Open WebUI runs on the same machine or network as the API.
- `ZYRA_API_KEY`: API key for authenticated access (if your API enforces it).
- `API_KEY_HEADER`: header name for the API key (default `X-API-Key`).
- `ZYRA_NET_TIMEOUT`: network timeout in seconds for HTTP fetches (default 2.0 for capabilities).
- `ZYRA_API_TIMEOUT`: timeout for Zyra API calls (default 1.5s when using the implicit localhost default; overridable).
- `ZYRA_OFFLINE`: if set to `1`/`true`/`yes`, skip all network fetches and only use local sources.

Valves Tips
- Configure under: Workspace → Tools → zyra_cli_manifest → Settings.
- Optional fields (API Key, Capabilities URL) can be left blank; blanks are treated as unset.
- If Settings doesn’t reflect new fields or optional status after code updates:
  - Click Edit on the tool, re-save the code (or remove and re-add the tool), then refresh the page.
  - Some builds cache the previous schema until the tool reloads.

Related Prompts
- In-package prompt: `src/zyra/assets/llm/prompts/zyra_tools_system.md` documents using both zyra_cli_manifest and
  github_repo_access tools.

Conventions
- Keep tools self-contained with minimal dependencies.
- Prefer environment variables over hard-coded paths or secrets.
- Avoid committing credentials; use local `.env` only if necessary and do not commit it.
