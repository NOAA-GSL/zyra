# SPDX-License-Identifier: Apache-2.0
"""Minimal example MCP client for Zyra's /mcp JSON-RPC endpoint.

Usage:
  poetry run python scripts/mcp_client_example.py list
  poetry run python scripts/mcp_client_example.py call visualize heatmap '{"input":"samples/demo.npy","output":"/tmp/heatmap.png"}'

Environment:
  ZYRA_API_BASE (default http://localhost:8000)
  ZYRA_API_KEY  (optional; passed as X-API-Key header)
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request


def _headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    api_key = os.environ.get("ZYRA_API_KEY")
    header_name = os.environ.get("API_KEY_HEADER", "X-API-Key") or "X-API-Key"
    if api_key:
        headers[header_name] = api_key
    return headers


def _post(path: str, body: dict) -> dict:
    base = os.environ.get("ZYRA_API_BASE", "http://localhost:8000").rstrip("/")
    url = f"{base}{path}"
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=_headers(), method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:  # nosec B310
        payload = r.read().decode("utf-8")
    try:
        return json.loads(payload)
    except Exception as err:
        print(payload)
        raise SystemExit(2) from err


def rpc(method: str, params: dict | None = None, id_val: int = 1) -> dict:
    return _post(
        "/mcp",
        {"jsonrpc": "2.0", "method": method, "params": params or {}, "id": id_val},
    )


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    cmd = argv[1]
    if cmd == "list":
        res = rpc("listTools")
        print(json.dumps(res, indent=2))
        return 0
    if cmd == "status":
        res = rpc("statusReport")
        print(json.dumps(res, indent=2))
        return 0
    if cmd == "call":
        if len(argv) < 5:
            print(
                "Usage: mcp_client_example.py call <stage> <command> <args_json> [sync|async]"
            )
            return 2
        stage, command, args_json = argv[2], argv[3], argv[4]
        mode = argv[5] if len(argv) > 5 else "sync"
        try:
            args = json.loads(args_json)
        except Exception:
            print("Invalid args_json; must be JSON object")
            return 2
        res = rpc(
            "callTool", {"stage": stage, "command": command, "args": args, "mode": mode}
        )
        print(json.dumps(res, indent=2))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
