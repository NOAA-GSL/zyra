GitHub Repo Access — NOAA/GSL Zyra (ChatGPT Action)

Purpose
- OpenAPI schema to enable ChatGPT (Actions) to anonymously query the public GitHub
  repository `NOAA-GSL/zyra` for contents, commits, branches, PRs, issues, and discussions.

Usage (ChatGPT Actions)
- In ChatGPT → Actions → Create, supply a URL to this `openapi.yaml` (host it from a raw URL
  in your fork or a static host). ChatGPT reads the schema and generates tool calls.
- This schema declares `bearerAuth`, but public GitHub endpoints work without tokens; rate limits
  may apply for anonymous access.

Endpoints Included
- `GET /repos/NOAA-GSL/zyra/contents/{path}` — file content or directory listing
- `GET /repos/NOAA-GSL/zyra/commits` and `/commits/{path}` — commits overall or per path
- `GET /repos/NOAA-GSL/zyra/branches` — list branches
- `GET /repos/NOAA-GSL/zyra/pulls` — list pull requests
- `GET /repos/NOAA-GSL/zyra/issues` and `/issues/{issue_number}` — list/get issues
- `GET /repos/NOAA-GSL/zyra/discussions` and `/discussions/{discussion_number}` — list/get discussions

Notes
- Source of truth: this folder (`llm/actions/github_repo_access/`). No packaged duplicate is kept to avoid drift.
- For higher rate limits or private access, configure the Action with an auth token.
