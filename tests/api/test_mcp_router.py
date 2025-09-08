from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from zyra.api.server import app, create_app


def _client_with_key(monkeypatch) -> TestClient:
    # Enable API key auth and return a TestClient with default header helper
    monkeypatch.setenv("DATAVIZHUB_API_KEY", "k")
    c = TestClient(app)
    return c


def test_mcp_requires_api_key(monkeypatch) -> None:
    monkeypatch.setenv("DATAVIZHUB_API_KEY", "k")
    client = TestClient(app)
    # Missing header
    r = client.post(
        "/v1/mcp", json={"jsonrpc": "2.0", "method": "statusReport", "id": 1}
    )
    assert r.status_code == 401
    # Wrong header
    r = client.post(
        "/v1/mcp",
        json={"jsonrpc": "2.0", "method": "statusReport", "id": 1},
        headers={"X-API-Key": "wrong"},
    )
    assert r.status_code == 401
    # Correct header
    r = client.post(
        "/v1/mcp",
        json={"jsonrpc": "2.0", "method": "statusReport", "id": 1},
        headers={"X-API-Key": "k"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("result", {}).get("status") == "ok"


def test_mcp_list_tools(monkeypatch) -> None:
    client = _client_with_key(monkeypatch)
    r = client.post(
        "/v1/mcp",
        json={"jsonrpc": "2.0", "method": "listTools", "id": 1},
        headers={"X-API-Key": "k"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("jsonrpc") == "2.0"
    result = body.get("result", {})
    # Now returns namespaced tools list shape
    tools = result.get("tools")
    assert isinstance(tools, list) and tools
    sample = tools[0]
    assert "name" in sample and "inputSchema" in sample
    assert isinstance(sample["inputSchema"], dict)


def test_mcp_http_discovery_get(monkeypatch) -> None:
    monkeypatch.setenv("DATAVIZHUB_API_KEY", "k")
    c = TestClient(app)
    r = c.get("/mcp", headers={"X-API-Key": "k"})
    assert r.status_code == 200
    js = r.json()
    assert js.get("mcp_version") == "0.1"
    assert js.get("name") == "zyra"
    caps = js.get("capabilities")
    assert isinstance(caps, dict)
    cmds = caps.get("commands")
    assert isinstance(cmds, list) and cmds
    assert all("name" in x and "parameters" in x for x in cmds)


def test_mcp_http_discovery_options(monkeypatch) -> None:
    monkeypatch.setenv("DATAVIZHUB_API_KEY", "k")
    c = TestClient(app)
    r = c.options("/mcp", headers={"X-API-Key": "k"})
    assert r.status_code == 200
    js = r.json()
    assert js.get("mcp_version") == "0.1"


def test_mcp_calltool_local_sync(tmp_path, monkeypatch) -> None:
    client = _client_with_key(monkeypatch)
    out_path = tmp_path / "ok.bin"
    payload = {
        "jsonrpc": "2.0",
        "method": "callTool",
        "params": {
            "stage": "decimate",
            "command": "local",
            "args": {"input": "-", "output": str(out_path)},
            "mode": "sync",
        },
        "id": 1,
    }
    r = client.post("/v1/mcp", json=payload, headers={"X-API-Key": "k"})
    assert r.status_code == 200
    js = r.json()
    res = js.get("result", {})
    assert res.get("status") == "ok"
    assert res.get("exit_code") in (0, None)  # minimal mapping returns exit_code
    assert out_path.exists()


def test_mcp_calltool_invalid_params(monkeypatch) -> None:
    client = _client_with_key(monkeypatch)
    r = client.post(
        "/v1/mcp",
        json={
            "jsonrpc": "2.0",
            "method": "callTool",
            "params": {"stage": "nope", "command": "also-nope", "args": {}},
            "id": 2,
        },
        headers={"X-API-Key": "k"},
    )
    assert r.status_code == 200
    js = r.json()
    assert "error" in js
    assert js["error"].get("code") == -32602


def test_mcp_calltool_async_job_lifecycle(tmp_path, monkeypatch) -> None:
    import time

    client = _client_with_key(monkeypatch)
    # Submit async job that will fail quickly (nonexistent input), to exercise lifecycle
    payload = {
        "jsonrpc": "2.0",
        "method": "callTool",
        "params": {
            "stage": "process",
            "command": "decode-grib2",
            "args": {"input": str(tmp_path / "missing.grib2")},
            "mode": "async",
        },
        "id": 3,
    }
    r = client.post("/v1/mcp", json=payload, headers={"X-API-Key": "k"})
    assert r.status_code == 200
    js = r.json()
    res = js.get("result", {})
    assert res.get("status") == "accepted"
    job_id = res.get("job_id")
    assert job_id
    # Poll the job until terminal state
    for _ in range(20):
        s = client.get(f"/v1/jobs/{job_id}", headers={"X-API-Key": "k"})
        assert s.status_code == 200
        body = s.json()
        if body.get("status") in {"succeeded", "failed", "canceled"}:
            assert "exit_code" in body
            break
        time.sleep(0.2)


def test_mcp_method_not_found(monkeypatch) -> None:
    client = _client_with_key(monkeypatch)
    r = client.post(
        "/v1/mcp",
        json={"jsonrpc": "2.0", "method": "nope", "id": 4},
        headers={"X-API-Key": "k"},
    )
    assert r.status_code == 200
    js = r.json()
    assert js.get("error", {}).get("code") == -32601


def test_mcp_invalid_jsonrpc_version(monkeypatch) -> None:
    client = _client_with_key(monkeypatch)
    r = client.post(
        "/v1/mcp",
        json={"jsonrpc": "1.0", "method": "statusReport", "id": 5},
        headers={"X-API-Key": "k"},
    )
    assert r.status_code == 200
    js = r.json()
    assert js.get("error", {}).get("code") == -32600


def test_mcp_calltool_sync_execution_error(tmp_path, monkeypatch) -> None:
    client = _client_with_key(monkeypatch)
    payload = {
        "jsonrpc": "2.0",
        "method": "callTool",
        "params": {
            "stage": "process",
            "command": "decode-grib2",
            "args": {"file_or_url": str(tmp_path / "missing.grib2")},
            "mode": "sync",
        },
        "id": 10,
    }
    r = client.post("/v1/mcp", json=payload, headers={"X-API-Key": "k"})
    assert r.status_code == 200
    js = r.json()
    assert "error" in js and js["error"].get("code") == -32000


def test_mcp_status_report_has_version(monkeypatch) -> None:
    client = _client_with_key(monkeypatch)
    r = client.post(
        "/v1/mcp",
        json={"jsonrpc": "2.0", "method": "statusReport", "id": 6},
        headers={"X-API-Key": "k"},
    )
    assert r.status_code == 200
    js = r.json()
    res = js.get("result", {})
    assert res.get("status") == "ok"
    assert isinstance(res.get("version"), str)


def test_mcp_progress_sse(monkeypatch, tmp_path) -> None:
    client = _client_with_key(monkeypatch)
    # Submit async job that will fail quickly
    payload = {
        "jsonrpc": "2.0",
        "method": "callTool",
        "params": {
            "stage": "process",
            "command": "decode-grib2",
            "args": {"file_or_url": str(tmp_path / "missing.grib2")},
            "mode": "async",
        },
        "id": 11,
    }
    r = client.post("/v1/mcp", json=payload, headers={"X-API-Key": "k"})
    assert r.status_code == 200
    job_id = r.json().get("result", {}).get("job_id")
    assert job_id
    # Stream SSE and collect a few events until terminal
    with client.stream(
        "GET", f"/v1/mcp/progress/{job_id}?interval_ms=50", headers={"X-API-Key": "k"}
    ) as resp:
        assert resp.status_code == 200
        buf = b""
        terminal = False
        for chunk in resp.iter_bytes():
            buf += chunk or b""
            # parse simple 'data: {...}\n\n'
            while b"\n\n" in buf:
                seg, buf = buf.split(b"\n\n", 1)
                if seg.startswith(b"data: "):
                    import json as _json

                    try:
                        ev = _json.loads(seg[6:].decode("utf-8"))
                    except Exception:
                        continue
                    if ev.get("status") in {"succeeded", "failed", "canceled"}:
                        terminal = True
                        break
            if terminal:
                break
    assert terminal


def test_mcp_initialize_handshake(monkeypatch) -> None:
    # Build a fresh app to ensure the latest MCP methods are mounted
    monkeypatch.setenv("DATAVIZHUB_API_KEY", "k")
    monkeypatch.setenv("ZYRA_ENABLE_MCP", "1")
    client = TestClient(create_app())
    r = client.post(
        "/v1/mcp",
        json={"jsonrpc": "2.0", "method": "initialize", "id": 12},
        headers={"X-API-Key": "k"},
    )
    assert r.status_code == 200
    js = r.json()
    res = js.get("result", {})
    assert isinstance(res.get("protocolVersion"), str) and res.get(
        "protocolVersion"
    ), f"initialize response: {js}"
    si = res.get("serverInfo", {})
    assert si.get("name") == "zyra"
    assert isinstance(si.get("version"), str)
    caps = res.get("capabilities", {})
    # MCP spec requires structured capabilities; tools should be an object
    tools_cap = caps.get("tools")
    assert isinstance(tools_cap, dict) and tools_cap.get("listChanged") is True


def test_mcp_tools_list_namespaced(monkeypatch) -> None:
    # Build a fresh app to ensure the latest MCP methods are mounted
    monkeypatch.setenv("DATAVIZHUB_API_KEY", "k")
    monkeypatch.setenv("ZYRA_ENABLE_MCP", "1")
    client = TestClient(create_app())
    r = client.post(
        "/v1/mcp",
        json={"jsonrpc": "2.0", "method": "tools/list", "id": 13, "params": {}},
        headers={"X-API-Key": "k"},
    )
    assert r.status_code == 200
    js = r.json()
    tools = js.get("result", {}).get("tools")
    assert isinstance(tools, list) and tools, f"tools/list response: {js}"
    t0 = tools[0]
    assert "name" in t0 and "inputSchema" in t0
    assert isinstance(t0["inputSchema"], dict)


def test_mcp_tools_call_namespaced_sync(tmp_path, monkeypatch) -> None:
    # Build a fresh app to ensure the latest MCP methods are mounted
    monkeypatch.setenv("DATAVIZHUB_API_KEY", "k")
    monkeypatch.setenv("ZYRA_ENABLE_MCP", "1")
    client = TestClient(create_app())
    out_path = tmp_path / "ok2.bin"
    payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": "decimate.local",
            "arguments": {"input": "-", "output": str(out_path)},
            "mode": "sync",
        },
        "id": 14,
    }
    r = client.post("/v1/mcp", json=payload, headers={"X-API-Key": "k"})
    assert r.status_code == 200
    js = r.json()
    res = js.get("result", {})
    assert res.get("status") in {"ok", "accepted"}
    if res.get("status") == "ok":
        assert out_path.exists()


@pytest.mark.mcp_ws
@pytest.mark.timeout(10)
def test_mcp_ws_initialize_and_notify(monkeypatch) -> None:
    monkeypatch.setenv("DATAVIZHUB_API_KEY", "k")
    client = TestClient(create_app())
    with client.websocket_connect("/v1/ws/mcp?api_key=k") as ws:
        init = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        ws.send_json(init)
        msg1 = ws.receive_json()
        assert msg1.get("id") == 1 and "result" in msg1
        # Next frame should be notifications/initialized
        msg2 = ws.receive_json()
        assert msg2.get("method") == "notifications/initialized"


@pytest.mark.mcp_ws
@pytest.mark.timeout(10)
def test_mcp_ws_tools_list_after_initialize(monkeypatch) -> None:
    monkeypatch.setenv("DATAVIZHUB_API_KEY", "k")
    client = TestClient(create_app())
    with client.websocket_connect("/v1/ws/mcp?api_key=k") as ws:
        ws.send_json({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        _ = ws.receive_json()  # init result
        _ = ws.receive_json()  # notifications/initialized
        ws.send_json({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        msg = ws.receive_json()
        tools = (msg or {}).get("result", {}).get("tools")
        assert isinstance(tools, list) and tools


def test_mcp_initialize_then_tools_list(monkeypatch) -> None:
    # Simulate a typical MCP client flow: initialize -> tools/list
    monkeypatch.setenv("DATAVIZHUB_API_KEY", "k")
    monkeypatch.setenv("ZYRA_ENABLE_MCP", "1")
    client = TestClient(create_app())

    # Step 1: initialize
    r1 = client.post(
        "/v1/mcp",
        json={"jsonrpc": "2.0", "method": "initialize", "id": 100},
        headers={"X-API-Key": "k"},
    )
    assert r1.status_code == 200
    init = r1.json().get("result", {})
    assert isinstance(init.get("protocolVersion"), str)
    tools_cap = (init.get("capabilities", {}) or {}).get("tools")
    assert isinstance(tools_cap, dict) and tools_cap.get("listChanged") is True

    # Step 2: tools/list
    r2 = client.post(
        "/v1/mcp",
        json={"jsonrpc": "2.0", "method": "tools/list", "id": 101, "params": {}},
        headers={"X-API-Key": "k"},
    )
    assert r2.status_code == 200
    tools = r2.json().get("result", {}).get("tools")
    assert isinstance(tools, list) and tools, f"tools/list response: {r2.json()}"


@pytest.mark.mcp_ws
@pytest.mark.timeout(10)
def test_mcp_ws_tools_call_async_progress(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DATAVIZHUB_API_KEY", "k")
    client = TestClient(create_app())
    with client.websocket_connect("/v1/ws/mcp?api_key=k") as ws:
        # Initialize
        ws.send_json({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        _ = ws.receive_json()  # init result
        _ = ws.receive_json()  # notifications/initialized

        # Kick off an async call that should fail quickly (missing file), just to exercise progress
        missing = str(tmp_path / "missing.grib2")
        ws.send_json(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "process.decode-grib2",
                    "arguments": {"file_or_url": missing},
                    "mode": "async",
                },
            }
        )
        resp = ws.receive_json()
        job_id = (resp or {}).get("result", {}).get("job_id")
        assert job_id, f"expected accepted job_id, got {resp}"

        progress_seen = False
        terminal = False
        for _ in range(40):
            msg = ws.receive_json()
            if (msg or {}).get("method") == "notifications/progress":
                params = (msg or {}).get("params", {})
                if params.get("job_id") == job_id:
                    progress_seen = progress_seen or (
                        "progress" in params or "stdout" in params or "stderr" in params
                    )
                    if params.get("status") in {"succeeded", "failed", "canceled"}:
                        terminal = True
                        break
        assert progress_seen, "expected at least one progress notification for the job"


def test_mcp_tools_call_search_query(monkeypatch) -> None:
    monkeypatch.setenv("DATAVIZHUB_API_KEY", "k")
    monkeypatch.setenv("ZYRA_ENABLE_MCP", "1")
    client = TestClient(create_app())
    r = client.post(
        "/v1/mcp",
        json={
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "search-query",
                "arguments": {"query": "earth", "limit": 5},
                "mode": "sync",
            },
            "id": 300,
        },
        headers={"X-API-Key": "k"},
    )
    assert r.status_code == 200
    js = r.json()
    items = (js or {}).get("result", {}).get("items")
    assert isinstance(items, list)


def test_mcp_initialize_then_tools_call_sync(tmp_path, monkeypatch) -> None:
    # Simulate initialize followed by a simple tools/call invocation
    monkeypatch.setenv("DATAVIZHUB_API_KEY", "k")
    monkeypatch.setenv("ZYRA_ENABLE_MCP", "1")
    client = TestClient(create_app())

    # Step 1: initialize
    r1 = client.post(
        "/v1/mcp",
        json={"jsonrpc": "2.0", "method": "initialize", "id": 200},
        headers={"X-API-Key": "k"},
    )
    assert r1.status_code == 200
    init = r1.json().get("result", {})
    assert isinstance(init.get("protocolVersion"), str)
    tools_cap = (init.get("capabilities", {}) or {}).get("tools")
    assert isinstance(tools_cap, dict) and tools_cap.get("listChanged") is True

    # Step 2: tools/call a simple local command
    out_path = tmp_path / "ok_flow.bin"
    payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": "decimate.local",
            "arguments": {"input": "-", "output": str(out_path)},
            "mode": "sync",
        },
        "id": 201,
    }
    r2 = client.post("/v1/mcp", json=payload, headers={"X-API-Key": "k"})
    assert r2.status_code == 200
    res = r2.json().get("result", {})
    assert res.get("status") in {"ok", "accepted"}
    if res.get("status") == "ok":
        assert out_path.exists()


def test_mcp_tools_call_namespaced_async_job_lifecycle(tmp_path, monkeypatch) -> None:
    import time

    client = _client_with_key(monkeypatch)
    payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": "process.decode-grib2",
            "arguments": {"file_or_url": str(tmp_path / "missing.grib2")},
            "mode": "async",
        },
        "id": 15,
    }
    r = client.post("/v1/mcp", json=payload, headers={"X-API-Key": "k"})
    assert r.status_code == 200
    js = r.json()
    res = js.get("result", {})
    assert res.get("status") == "accepted"
    job_id = res.get("job_id")
    assert job_id
    # Poll the job until terminal state
    for _ in range(20):
        s = client.get(f"/v1/jobs/{job_id}", headers={"X-API-Key": "k"})
        assert s.status_code == 200
        body = s.json()
        if body.get("status") in {"succeeded", "failed", "canceled"}:
            assert "exit_code" in body
            break
        time.sleep(0.2)


def test_mcp_disabled_hides_route(monkeypatch) -> None:
    # Disable via env flag and build a fresh app
    monkeypatch.setenv("ZYRA_ENABLE_MCP", "0")
    c = TestClient(create_app())
    r = c.post("/mcp", json={"jsonrpc": "2.0", "method": "statusReport", "id": 7})
    assert r.status_code == 404


def test_mcp_enabled_flag_allows_route(monkeypatch) -> None:
    # Explicitly enable and expect endpoint to be present
    monkeypatch.setenv("ZYRA_ENABLE_MCP", "1")
    monkeypatch.setenv("DATAVIZHUB_API_KEY", "k")
    c = TestClient(create_app())
    r = c.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "statusReport", "id": 8},
        headers={"X-API-Key": "k"},
    )
    assert r.status_code == 200


def test_mcp_request_size_limit_enforced(monkeypatch) -> None:
    # Set a tiny request-body limit to force a rejection
    monkeypatch.setenv("ZYRA_ENABLE_MCP", "1")
    monkeypatch.setenv("DATAVIZHUB_API_KEY", "k")
    monkeypatch.setenv("ZYRA_MCP_MAX_BODY_BYTES", "100")
    c = TestClient(create_app())
    big = "x" * 200
    payload = {
        "jsonrpc": "2.0",
        "method": "callTool",
        "params": {"stage": "decimate", "command": "local", "args": {"pad": big}},
        "id": 9,
    }
    r = c.post("/mcp", json=payload, headers={"X-API-Key": "k"})
    assert r.status_code == 200
    js = r.json()
    assert js.get("error", {}).get("code") == -32001
