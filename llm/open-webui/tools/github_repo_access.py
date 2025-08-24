from __future__ import annotations

import base64
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

try:  # pragma: no cover - only needed in Open WebUI runtime
    from pydantic import BaseModel, Field  # type: ignore
except Exception:  # pragma: no cover
    BaseModel = object  # type: ignore[misc,assignment]

    def Field(*_a: object, **kw: object):  # type: ignore[func-returns-value]
        return kw.get("default")


# Tool-level Valves (shown in Open WebUI Tools UI)
VALVES = [
    {
        "name": "api_base",
        "label": "GitHub API Base",
        "type": "string",
        "value": "https://api.github.com",
        "help": "Base URL for GitHub API.",
    },
    {
        "name": "owner",
        "label": "Repo Owner",
        "type": "string",
        "value": "NOAA-GSL",
    },
    {
        "name": "repo",
        "label": "Repo Name",
        "type": "string",
        "value": "zyra",
    },
    {
        "name": "token",
        "label": "GitHub Token",
        "type": "string",
        "value": "",
        "secret": True,
        "help": "Optional token for higher rate limits or private data.",
        "required": False,
        "optional": True,
    },
    {
        "name": "timeout",
        "label": "HTTP Timeout (seconds)",
        "type": "number",
        "value": 6.0,
    },
    {
        "name": "connect_timeout",
        "label": "Connect Timeout (seconds)",
        "type": "number",
        "value": 3.0,
        "help": "Optional connect timeout; falls back to Timeout if unset.",
        "required": False,
        "optional": True,
    },
    {
        "name": "read_timeout",
        "label": "Read Timeout (seconds)",
        "type": "number",
        "value": 6.0,
        "help": "Optional read timeout; falls back to Timeout if unset.",
        "required": False,
        "optional": True,
    },
    {
        "name": "user_agent",
        "label": "User-Agent",
        "type": "string",
        "value": "zyra-openwebui-tool/1.0",
    },
    {
        "name": "local_root",
        "label": "Local Repo Root",
        "type": "string",
        "value": "",
        "help": "Optional local path to the repo root for offline fallback.",
        "required": False,
        "optional": True,
    },
    {
        "name": "prefer_local",
        "label": "Prefer Local Filesystem",
        "type": "boolean",
        "value": False,
        "help": "If true, try local filesystem before calling GitHub.",
    },
    {
        "name": "offline",
        "label": "Offline Mode",
        "type": "boolean",
        "value": False,
        "help": "If true, skip all GitHub API calls and use local filesystem only.",
    },
]


def _v(valves: Any, name: str, default: Any) -> Any:
    v = valves
    if v is None:
        return default
    # Dict-like (Tools valves dict injected by Open WebUI)
    if isinstance(v, dict):
        if name not in v:
            return default
        node = v[name]
        if isinstance(node, dict) and "value" in node:
            return node.get("value", default)
        return node
    # Model-like (pydantic Tools.Valves)
    try:
        return getattr(v, name, default)
    except Exception:
        return default


def _headers(valves: dict | None) -> dict[str, str]:
    headers = {
        "X-GitHub-Api-Version": "2022-11-28",
        "Accept": "application/vnd.github+json",
        "User-Agent": str(
            _v(valves, "user_agent", os.getenv("GITHUB_UA", "zyra-openwebui-tool/1.0"))
        ),
    }
    tok = str(_v(valves, "token", os.getenv("GITHUB_TOKEN", "") or "")).strip()
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    return headers


def _base(valves: dict | None) -> str:
    return str(
        _v(valves, "api_base", os.getenv("GITHUB_API_BASE", "https://api.github.com"))
    )


def _repo(valves: dict | None) -> tuple[str, str]:
    owner = str(_v(valves, "owner", os.getenv("GITHUB_OWNER", "NOAA-GSL")))
    repo = str(_v(valves, "repo", os.getenv("GITHUB_REPO", "zyra")))
    return owner, repo


def _has_token(valves: dict | None) -> bool:
    tok = str(_v(valves, "token", os.getenv("GITHUB_TOKEN", "") or "")).strip()
    return bool(tok)


def _timeouts(valves: dict | None) -> tuple[float, float]:
    """Return (connect_timeout, read_timeout)."""
    try:
        base = float(_v(valves, "timeout", os.getenv("GITHUB_TIMEOUT", 6.0)))
    except Exception:
        base = 6.0
    try:
        cto = float(
            _v(valves, "connect_timeout", os.getenv("GITHUB_CONNECT_TIMEOUT", base))
        )
    except Exception:
        cto = base
    try:
        rto = float(_v(valves, "read_timeout", os.getenv("GITHUB_READ_TIMEOUT", base)))
    except Exception:
        rto = base
    return (cto, rto)


def _local_root(valves: dict | None) -> str:
    """Resolve local repository root for offline access.

    Order of precedence:
    - Valve `local_root`
    - Env `GITHUB_LOCAL_ROOT`
    - Current working directory ("") if neither set
    """
    root = str(_v(valves, "local_root", os.getenv("GITHUB_LOCAL_ROOT", ""))).strip()
    return root


def _bool(valves: dict | None, name: str, env: str, default: bool = False) -> bool:
    raw = _v(valves, name, os.getenv(env, str(default)))
    if isinstance(raw, bool):
        return raw
    s = str(raw).strip().lower()
    return s in {"1", "true", "yes", "on"}


def _local_stat(path: Path) -> dict[str, Any] | None:
    try:
        st = path.stat()
        return {"size": int(st.st_size)}
    except Exception:
        return None


def _local_encode_file(abs_path: Path, rel_path: str) -> dict[str, Any]:
    try:
        with abs_path.open("rb") as f:
            blob = f.read()
        b64 = base64.b64encode(blob).decode("ascii")
        decoded: str | None = None
        try:
            decoded = blob.decode("utf-8")
        except Exception:
            decoded = None
        node: dict[str, Any] = {
            "name": Path(rel_path).name,
            "path": Path(rel_path).as_posix(),
            "type": "file",
            "encoding": "base64",
            "content": b64,
            "download_url": None,
        }
        if decoded is not None:
            node["decoded_text"] = decoded
        st = _local_stat(abs_path)
        if st:
            node.update(st)
        return node
    except Exception as e:
        return {"error": f"Failed to read local file {abs_path}: {e}"}


def _local_list_dir(abs_dir: Path, rel_dir: str) -> dict[str, Any]:
    try:
        entries = []
        for p in sorted(abs_dir.iterdir(), key=lambda p: p.name):
            name = p.name
            rel_path = (Path(rel_dir) / name) if rel_dir else Path(name)
            entry: dict[str, Any] = {
                "name": name,
                "path": rel_path.as_posix(),
                "type": "dir" if p.is_dir() else "file",
            }
            st = _local_stat(p)
            if st:
                entry.update(st)
            entries.append(entry)
        return {"entries": entries}
    except FileNotFoundError:
        return {"error": f"Local directory not found: {abs_dir}"}
    except Exception as e:
        return {"error": f"Failed to list local directory {abs_dir}: {e}"}


def _get(
    valves: dict | None, path: str, params: dict[str, Any] | None = None
) -> dict[str, Any]:
    url = f"{_base(valves).rstrip('/')}{path}"
    try:
        r = requests.get(
            url,
            params=params or {},
            headers=_headers(valves),
            timeout=_timeouts(valves),
        )
        r.raise_for_status()
        return r.json()
    except requests.HTTPError as e:  # include useful headers on rate-limits
        info: dict[str, Any] = {
            "error": f"HTTP {r.status_code} for {url}",
            "detail": str(e),
        }
        for h in ("X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset"):
            if h in r.headers:
                info[h] = r.headers[h]
        try:
            info["body"] = r.json()
        except Exception:
            info["body"] = r.text
        return info
    except Exception as e:
        return {"error": f"Request failed for {url}: {e}"}


@dataclass
class ContentResult:
    name: str | None = None
    path: str | None = None
    type: str | None = None
    sha: str | None = None
    size: int | None = None
    encoding: str | None = None
    content: str | None = None
    download_url: str | None = None
    decoded_text: str | None = None


def _decode_content(obj: Any) -> Any:
    """If given a GitHub contents file dict, return a copy with decoded_text.

    - For GitHub file JSON objects with base64 `content`, returns a shallow copy
      of the dict that includes `decoded_text` (UTF-8, errors replaced).
    - For non-dict inputs or dicts without base64 content, returns the input unchanged.
    """
    if not isinstance(obj, dict):
        return obj
    if obj.get("encoding") == "base64" and obj.get("content"):
        try:
            raw = base64.b64decode(str(obj["content"]).encode())
            text = raw.decode("utf-8", errors="replace")
            new_obj = dict(obj)
            new_obj["decoded_text"] = text
            return new_obj
        except Exception:
            return obj
    return obj


class Tools:
    # Open WebUI injects `valves` (dict) into instances at runtime
    valves: dict | None = None

    # Valves schema for Tools UI (pydantic model)
    class Valves(BaseModel):  # type: ignore[misc]
        api_base: str = Field(
            default="https://api.github.com",
            description="Base URL for GitHub API.",
        )
        owner: str = Field(
            default="NOAA-GSL",
            description="GitHub repository owner.",
        )
        repo: str = Field(
            default="zyra",
            description="GitHub repository name.",
        )
        token: str = Field(
            default="",
            description="Optional GitHub token for higher rate limits/private data.",
        )
        timeout: float = Field(
            default=6.0,
            description="HTTP timeout in seconds (both connect/read if not overridden).",
        )
        connect_timeout: float = Field(
            default=3.0,
            description="Optional connect timeout in seconds.",
        )
        read_timeout: float = Field(
            default=6.0,
            description="Optional read timeout in seconds.",
        )
        user_agent: str = Field(
            default="zyra-openwebui-tool/1.0",
            description="User-Agent header value.",
        )
        local_root: str = Field(
            default="",
            description="Optional local repo root for offline fallback.",
        )
        prefer_local: bool = Field(
            default=False,
            description="Try local filesystem before GitHub API.",
        )
        offline: bool = Field(
            default=False,
            description="Skip network; use local filesystem only.",
        )

    def __init__(self, valves: dict | None = None) -> None:
        # Use injected valves if provided; else seed with schema defaults
        self.valves = valves if valves is not None else self.Valves()  # type: ignore[call-arg]
        # Some Open WebUI builds expect this flag to show source context
        self.citation = True

    # Contents or directory listing
    def github_get_file_or_directory(
        self,
        path: str,
        ref: str | None = None,
        owner: str | None = None,
        repo: str | None = None,
        prefer_local: bool | None = None,
        offline: bool | None = None,
    ) -> str:
        """Return a string summary for a file or directory.

        Matches Open WebUI single-file tool expectations (string output with
        embedded JSON). Supports optional owner/repo override and local/offline
        fallback.
        """
        # Resolve owner/repo and local/offline preferences
        d_owner, d_repo = _repo(self.valves)
        owner = owner or d_owner
        repo = repo or d_repo
        prefer_local_eff = _bool(
            self.valves, "prefer_local", "GITHUB_PREFER_LOCAL", False
        )
        if prefer_local is not None:
            prefer_local_eff = bool(prefer_local)
        offline_eff = _bool(self.valves, "offline", "GITHUB_OFFLINE", False)
        if offline is not None:
            offline_eff = bool(offline)
        local_root = _local_root(self.valves)
        rel_path = path.lstrip("/")

        def _try_local() -> dict[str, Any] | None:
            base = Path(local_root) if local_root else None
            rel = Path(rel_path)
            abs_path = (base / rel) if base else rel
            if abs_path.exists():
                if abs_path.is_dir():
                    return _local_list_dir(abs_path, rel_path)
                return _local_encode_file(abs_path, rel_path)
            # Also consider current working directory if local_root provided but not found
            if base is not None:
                abs_path2 = rel
                if abs_path2.exists():
                    if abs_path2.is_dir():
                        return _local_list_dir(abs_path2, rel_path)
                    return _local_encode_file(abs_path2, rel_path)
            return None

        # If offline or prefer_local, try local first and format as string
        if offline_eff or prefer_local_eff:
            local = _try_local()
            if local is not None:
                if "entries" in local:  # dir listing
                    return (
                        f"Show a directory listing for {owner}/{repo}:{path} with this data:\n\n"
                        + json.dumps(local)
                    )
                # file node
                name = local.get("name")
                fpath = local.get("path")
                size = local.get("size")
                preview = local.get("decoded_text")
                preview = preview[:8000] if isinstance(preview, str) else None
                return (
                    f"Show the file {owner}/{repo}:{path} with this data:\n\n"
                    + json.dumps(
                        {
                            "name": name,
                            "path": fpath,
                            "size": size,
                            "preview_utf8": preview,
                        }
                    )
                )
            if offline_eff:
                return f"Offline mode: local path not found for '{path}'"

        # Fallback to GitHub API
        # Normalize ref: treat None/""/"null"/"none" as unset to use default branch
        ref_in = (
            (ref or "").strip()
            if isinstance(ref, str) or ref is None
            else str(ref).strip()
        )
        if not ref_in or ref_in.lower() in {"null", "none"}:
            ref_in = None

        data = _get(
            self.valves,
            f"/repos/{owner}/{repo}/contents/{path}",
            params={"ref": ref_in} if ref_in else None,
        )
        # Handle HTTP error structure (including timeouts or DNS failures)
        if isinstance(data, dict) and "error" in data:
            code = data.get("error", "error")
            return f"Failed to fetch {owner}/{repo}:{path}: {code}"

        # Directory listing
        if isinstance(data, list):
            entries = []
            for item in data:
                entries.append(
                    {
                        "name": item.get("name"),
                        "path": item.get("path"),
                        "type": item.get("type"),
                        "size": item.get("size"),
                    }
                )
            return (
                f"Show a directory listing for {owner}/{repo}:{path} with this data:\n\n"
                + json.dumps({"entries": entries})
            )

        # Single file
        if isinstance(data, dict):
            data = _decode_content(data)
            name = data.get("name")
            fpath = data.get("path")
            size = data.get("size")
            preview = data.get("decoded_text")
            if isinstance(preview, str):
                preview = preview[:8000]
            else:
                if data.get("encoding") == "base64" and data.get("content"):
                    try:
                        raw = base64.b64decode(str(data["content"]).encode())
                        preview = raw.decode("utf-8", errors="replace")[:8000]
                    except Exception:
                        preview = None
                else:
                    preview = None

            return (
                f"Show the file {owner}/{repo}:{path} with this data:\n\n"
                + json.dumps(
                    {
                        "name": name,
                        "path": fpath,
                        "size": size,
                        "preview_utf8": preview,
                    }
                )
            )

        # Fallback
        try:
            snippet = json.dumps(data)[:2000]
        except Exception:
            snippet = str(data)[:2000]
        return f"Unexpected response for {owner}/{repo}:{path}: {snippet}"

    # Recent commits in the repository
    def github_list_commits(
        self,
        sha: str | None = None,
        per_page: int | None = None,
        page: int | None = None,
        owner: str | None = None,
        repo: str | None = None,
    ) -> str:
        d_owner, d_repo = _repo(self.valves)
        owner = owner or d_owner
        repo = repo or d_repo
        params = {"sha": sha, "per_page": per_page, "page": page}
        params = {k: v for k, v in params.items() if v is not None}
        res = _get(self.valves, f"/repos/{owner}/{repo}/commits", params=params)
        try:
            payload = json.dumps(res)
        except Exception:
            payload = str(res)
        return f"Show recent commits for {owner}/{repo} with this data:\n\n" + payload

    # Commit history for a specific file or directory
    def github_list_file_commits(
        self,
        path: str,
        sha: str | None = None,
        owner: str | None = None,
        repo: str | None = None,
    ) -> str:
        d_owner, d_repo = _repo(self.valves)
        owner = owner or d_owner
        repo = repo or d_repo
        params = {"sha": sha} if sha else None
        res = _get(self.valves, f"/repos/{owner}/{repo}/commits/{path}", params=params)
        try:
            payload = json.dumps(res)
        except Exception:
            payload = str(res)
        return (
            f"Show commit history for {owner}/{repo}:{path} with this data:\n\n"
            + payload
        )

    # Pull requests
    def github_list_pull_requests(
        self,
        state: str | None = None,
        per_page: int | None = None,
        page: int | None = None,
        owner: str | None = None,
        repo: str | None = None,
    ) -> str:
        d_owner, d_repo = _repo(self.valves)
        owner = owner or d_owner
        repo = repo or d_repo
        params = {"state": state, "per_page": per_page, "page": page}
        params = {k: v for k, v in params.items() if v is not None}
        res = _get(self.valves, f"/repos/{owner}/{repo}/pulls", params=params)
        try:
            payload = json.dumps(res)
        except Exception:
            payload = str(res)
        return (
            f"Show the pull requests for {owner}/{repo} with this data:\n\n" + payload
        )

    # Branches
    def github_list_branches(
        self,
        per_page: int | None = None,
        page: int | None = None,
        owner: str | None = None,
        repo: str | None = None,
    ) -> str:
        d_owner, d_repo = _repo(self.valves)
        owner = owner or d_owner
        repo = repo or d_repo
        params = {"per_page": per_page, "page": page}
        params = {k: v for k, v in params.items() if v is not None}
        res = _get(self.valves, f"/repos/{owner}/{repo}/branches", params=params)
        try:
            payload = json.dumps(res)
        except Exception:
            payload = str(res)
        return f"Show the branches for {owner}/{repo} with this data:\n\n" + payload

    # Discussions (GitHub Discussions API)
    def github_list_discussions(
        self,
        per_page: int | None = None,
        page: int | None = None,
        owner: str | None = None,
        repo: str | None = None,
    ) -> str:
        d_owner, d_repo = _repo(self.valves)
        owner = owner or d_owner
        repo = repo or d_repo
        params = {"per_page": per_page, "page": page}
        params = {k: v for k, v in params.items() if v is not None}
        res = _get(self.valves, f"/repos/{owner}/{repo}/discussions", params=params)
        try:
            payload = json.dumps(res)
        except Exception:
            payload = str(res)
        return f"Show the discussions for {owner}/{repo} with this data:\n\n" + payload

    def github_get_discussion(
        self, discussion_number: int, owner: str | None = None, repo: str | None = None
    ) -> str:
        d_owner, d_repo = _repo(self.valves)
        owner = owner or d_owner
        repo = repo or d_repo
        res = _get(
            self.valves, f"/repos/{owner}/{repo}/discussions/{discussion_number}"
        )
        try:
            payload = json.dumps(res)
        except Exception:
            payload = str(res)
        return (
            f"Show discussion {discussion_number} for {owner}/{repo} with this data:\n\n"
            + payload
        )

    # Issues
    def github_list_issues(
        self,
        state: str | None = None,
        per_page: int | None = None,
        page: int | None = None,
        owner: str | None = None,
        repo: str | None = None,
    ) -> str:
        d_owner, d_repo = _repo(self.valves)
        owner = owner or d_owner
        repo = repo or d_repo
        params = {"state": state, "per_page": per_page, "page": page}
        params = {k: v for k, v in params.items() if v is not None}
        res = _get(self.valves, f"/repos/{owner}/{repo}/issues", params=params)
        try:
            payload = json.dumps(res)
        except Exception:
            payload = str(res)
        return f"Show the issues for {owner}/{repo} with this data:\n\n" + payload

    def github_get_issue(
        self, issue_number: int, owner: str | None = None, repo: str | None = None
    ) -> str:
        d_owner, d_repo = _repo(self.valves)
        owner = owner or d_owner
        repo = repo or d_repo
        res = _get(self.valves, f"/repos/{owner}/{repo}/issues/{issue_number}")
        try:
            payload = json.dumps(res)
        except Exception:
            payload = str(res)
        return (
            f"Show issue {issue_number} for {owner}/{repo} with this data:\n\n"
            + payload
        )

    # Code search within the repository (GitHub Code Search v3)
    def github_search_code(
        self,
        query: str | None = None,
        path: str | None = None,
        language: str | None = None,
        extension: str | None = None,
        per_page: int | None = None,
        page: int | None = None,
        # Aliases/overrides for flexibility in Open WebUI payloads
        search_code: str | None = None,
        owner: str | None = None,
        repo: str | None = None,
    ) -> str:
        """Search code in the configured repo.

        - query: search terms (e.g., "wizard prompts").
        - path/language/extension: optional qualifiers to scope results.
        - per_page/page: pagination controls.
        """
        d_owner, d_repo = _repo(self.valves)
        owner = owner or d_owner
        repo = repo or d_repo

        # Allow alias `search_code` when `query` isn't provided
        if query is None and search_code is not None:
            query = search_code
        if query is None:
            return "Query is required for code search."

        # If a token is present, use GitHub Code Search API directly
        if _has_token(self.valves):
            terms = [str(query).strip(), f"repo:{owner}/{repo}"]
            if path:
                terms.append(f"path:{path}")
            if language:
                terms.append(f"language:{language}")
            if extension:
                terms.append(f"extension:{extension}")
            q = " ".join([t for t in terms if t])
            params: dict[str, Any] = {"q": q}
            if per_page is not None:
                params["per_page"] = per_page
            if page is not None:
                params["page"] = page
            # Endpoint: GET /search/code?q=
            url_path = "/search/code"
            res = _get(self.valves, url_path, params=params)
            # Friendly guidance when GitHub requires auth for code search
            if isinstance(res, dict):
                msg = (
                    str(res.get("error", "")) + " " + str(res.get("message", ""))
                ).lower()
                if "requires authentication" in msg or "must be authenticated" in msg:
                    hint = (
                        "GitHub code search requires authentication. Set a token in the tool's 'token' valve "
                        "or export GITHUB_TOKEN. Public search works with an unscoped token."
                    )
                    try:
                        payload = json.dumps({"error": res, "hint": hint})
                    except Exception:
                        payload = f"{res} | {hint}"
                    return (
                        f"Show code search results for query '{query}' in {owner}/{repo} with this data:\n\n"
                        + payload
                    )
            try:
                payload = json.dumps(res)
            except Exception:
                payload = str(res)
            return (
                f"Show code search results for query '{query}' in {owner}/{repo} with this data:\n\n"
                + payload
            )

        # No token: perform a light, client-side search using the Git Trees + Contents APIs
        # 1) determine default branch
        meta = _get(self.valves, f"/repos/{owner}/{repo}")
        branch = None
        if isinstance(meta, dict):
            branch = meta.get("default_branch")
        if not branch:
            branch = "main"

        # 2) list files via trees API (recursive)
        tree = _get(
            self.valves,
            f"/repos/{owner}/{repo}/git/trees/{branch}",
            params={"recursive": 1},
        )
        files: list[str] = []
        if isinstance(tree, dict) and isinstance(tree.get("tree"), list):
            for node in tree["tree"]:
                if node.get("type") == "blob" and isinstance(node.get("path"), str):
                    files.append(node["path"])

        # 3) apply simple filters
        def ext_match(p: str, ext: str | None) -> bool:
            if not ext:
                return True
            e = ext.lstrip(".").lower()
            return p.lower().endswith("." + e)

        # simple language → extension map for common cases
        lang_exts = {
            "python": ["py"],
            "javascript": ["js"],
            "typescript": ["ts"],
            "go": ["go"],
            "rust": ["rs"],
            "java": ["java"],
            "c++": ["cpp", "hpp", "cc", "hh"],
            "c": ["c", "h"],
        }
        lang = (language or "").strip().lower()
        lang_ext = lang_exts.get(lang)

        filtered: list[str] = []
        path_q = (path or "").strip()
        for p in files:
            if path_q and path_q not in p:
                continue
            if extension and not ext_match(p, extension):
                continue
            if lang_ext and not any(p.lower().endswith("." + e) for e in lang_ext):
                continue
            filtered.append(p)

        # 4) fetch and scan a limited number of files for the query string
        max_scan = int(per_page or 10) * 4  # scan up to 4x requested results
        max_scan = max(10, min(max_scan, 200))
        results = []
        qre = re.compile(re.escape(query), re.IGNORECASE)
        for p in filtered[:max_scan]:
            obj = _get(
                self.valves,
                f"/repos/{owner}/{repo}/contents/{p}",
                params={"ref": branch},
            )
            if not isinstance(obj, dict):
                continue
            if obj.get("encoding") == "base64" and obj.get("content"):
                try:
                    raw = base64.b64decode(str(obj["content"]).encode())
                    text = raw.decode("utf-8", errors="replace")
                except Exception:
                    continue
                m = qre.search(text)
                if m:
                    # build a short snippet around the first match
                    start = max(0, m.start() - 60)
                    end = min(len(text), m.end() + 60)
                    snippet = text[start:end]
                    results.append(
                        {
                            "name": obj.get("name"),
                            "path": obj.get("path", p),
                            "size": obj.get("size"),
                            "html_url": obj.get("html_url"),
                            "snippet": snippet,
                        }
                    )
            if len(results) >= int(per_page or 10):
                break

        try:
            payload = json.dumps({"items": results})
        except Exception:
            payload = str({"items": results})
        return (
            f"Show code search results for query '{query}' in {owner}/{repo} with this data:\n\n"
            + payload
        )

    # Simple execution sanity method for Open WebUI
    def ping(self) -> str:
        return "pong"
