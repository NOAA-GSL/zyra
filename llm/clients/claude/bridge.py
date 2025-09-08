from __future__ import annotations

import json
import os
import platform
import sys
from datetime import datetime
from pathlib import Path

import requests

Zyra_MCP_URL = os.environ.get("ZYRA_MCP_URL", "http://localhost:8000/mcp")


def _resolve_log_dir() -> Path:
    """Return a platform-appropriate Claude log directory.

    Resolution order (first available wins):
    - Env override: `CLAUDE_LOG_DIR` or `ZYRA_CLAUDE_LOG_DIR`
    - Windows: `%APPDATA%/Claude/logs`
    - macOS: `~/Library/Logs/Claude` (fallback: `~/Library/Application Support/Claude/logs`)
    - Linux/other: `$XDG_STATE_HOME/Claude/logs` → `$XDG_CACHE_HOME/Claude/logs` →
      `~/.local/state/Claude/logs` → `~/.config/Claude/logs`
    """
    for key in ("CLAUDE_LOG_DIR", "ZYRA_CLAUDE_LOG_DIR"):
        val = os.environ.get(key)
        if val:
            return Path(val).expanduser()

    system = platform.system().lower()
    if system.startswith("win"):
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "Claude" / "logs"
        return Path.home() / "AppData" / "Roaming" / "Claude" / "logs"

    if system == "darwin":
        p = Path.home() / "Library" / "Logs" / "Claude"
        if p.exists() or p.parent.exists():
            return p
        return Path.home() / "Library" / "Application Support" / "Claude" / "logs"

    xdg_state = os.environ.get("XDG_STATE_HOME")
    if xdg_state:
        return Path(xdg_state) / "Claude" / "logs"
    xdg_cache = os.environ.get("XDG_CACHE_HOME")
    if xdg_cache:
        return Path(xdg_cache) / "Claude" / "logs"
    home = Path.home()
    if (home / ".local").exists():
        return home / ".local" / "state" / "Claude" / "logs"
    return home / ".config" / "Claude" / "logs"


# Log file path inside Claude's log dir (configurable)
LOG_DIR = _resolve_log_dir()
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "zyra_bridge.log"


def log_message(prefix: str, data: dict | str):
    """Write timestamped log entries to file."""
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(f"{datetime.utcnow().isoformat()}Z [{prefix}] {json.dumps(data)}\n")


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            log_message("ERROR", {"raw": line, "msg": "Invalid JSON"})
            continue

        log_message("REQUEST", request)

        # Forward to Zyra MCP
        try:
            resp = requests.post(Zyra_MCP_URL, json=request, timeout=30)
            result = resp.json()
        except Exception as e:
            result = {
                "jsonrpc": "2.0",
                "id": request.get("id"),
                "error": {"code": -32000, "message": str(e)},
            }

        log_message("RESPONSE", result)

        # Return to Claude
        sys.stdout.write(json.dumps(result) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
