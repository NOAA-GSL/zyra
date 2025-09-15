# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from fastapi.testclient import TestClient

from zyra.api.server import create_app


def test_mcp_api_fetch_valueerror_maps_to_jsonrpc_error_400(monkeypatch):
    # Enable MCP routes
    monkeypatch.setenv("ZYRA_ENABLE_MCP", "1")
    # Disable API key enforcement
    monkeypatch.delenv("ZYRA_API_KEY", raising=False)

    app = create_app()
    client = TestClient(app)

    payload = {
        "jsonrpc": "2.0",
        "id": "t1",
        "method": "callTool",
        "params": {
            "name": "api-fetch",
            "arguments": {"url": "http://127.0.0.1/"},  # blocked by HTTPS-only default
        },
    }
    r = client.post("/mcp", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body.get("jsonrpc") == "2.0"
    assert body.get("id") == "t1"
    err = body.get("error") or {}
    # ValueError should be mapped to JSON-RPC error.code 400
    assert err.get("code") == 400
    assert isinstance(err.get("message"), str) and err["message"]
