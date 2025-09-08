from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import requests

Zyra_MCP_URL = "http://localhost:8000/mcp"

# Log file path inside Claude's log dir
LOG_DIR = Path(r"C:\Users\eric.j.hackathorn.NEAD.000\AppData\Roaming\Claude\logs")
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
