from __future__ import annotations

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
    r = client.post("/mcp", json={"jsonrpc": "2.0", "method": "statusReport", "id": 1})
    assert r.status_code == 401
    # Wrong header
    r = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "statusReport", "id": 1},
        headers={"X-API-Key": "wrong"},
    )
    assert r.status_code == 401
    # Correct header
    r = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "statusReport", "id": 1},
        headers={"X-API-Key": "k"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("result", {}).get("status") == "ok"


def test_mcp_list_tools(monkeypatch) -> None:
    client = _client_with_key(monkeypatch)
    r = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "listTools", "id": 1},
        headers={"X-API-Key": "k"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("jsonrpc") == "2.0"
    result = body.get("result", {})
    # MCP discovery shape
    assert result.get("mcp_version") == "0.1"
    assert result.get("name") == "zyra"
    caps = result.get("capabilities")
    assert isinstance(caps, dict)
    cmds = caps.get("commands")
    assert isinstance(cmds, list) and cmds
    sample = cmds[0]
    assert "name" in sample and "parameters" in sample
    assert isinstance(sample["parameters"], dict)
    assert sample["parameters"].get("type") == "object"


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
    r = client.post("/mcp", json=payload, headers={"X-API-Key": "k"})
    assert r.status_code == 200
    js = r.json()
    res = js.get("result", {})
    assert res.get("status") == "ok"
    assert res.get("exit_code") in (0, None)  # minimal mapping returns exit_code
    assert out_path.exists()


def test_mcp_calltool_invalid_params(monkeypatch) -> None:
    client = _client_with_key(monkeypatch)
    r = client.post(
        "/mcp",
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
    r = client.post("/mcp", json=payload, headers={"X-API-Key": "k"})
    assert r.status_code == 200
    js = r.json()
    res = js.get("result", {})
    assert res.get("status") == "accepted"
    job_id = res.get("job_id")
    assert job_id
    # Poll the job until terminal state
    for _ in range(20):
        s = client.get(f"/jobs/{job_id}", headers={"X-API-Key": "k"})
        assert s.status_code == 200
        body = s.json()
        if body.get("status") in {"succeeded", "failed", "canceled"}:
            assert "exit_code" in body
            break
        time.sleep(0.2)


def test_mcp_method_not_found(monkeypatch) -> None:
    client = _client_with_key(monkeypatch)
    r = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "nope", "id": 4},
        headers={"X-API-Key": "k"},
    )
    assert r.status_code == 200
    js = r.json()
    assert js.get("error", {}).get("code") == -32601


def test_mcp_invalid_jsonrpc_version(monkeypatch) -> None:
    client = _client_with_key(monkeypatch)
    r = client.post(
        "/mcp",
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
    r = client.post("/mcp", json=payload, headers={"X-API-Key": "k"})
    assert r.status_code == 200
    js = r.json()
    assert "error" in js and js["error"].get("code") == -32000


def test_mcp_status_report_has_version(monkeypatch) -> None:
    client = _client_with_key(monkeypatch)
    r = client.post(
        "/mcp",
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
    r = client.post("/mcp", json=payload, headers={"X-API-Key": "k"})
    assert r.status_code == 200
    job_id = r.json().get("result", {}).get("job_id")
    assert job_id
    # Stream SSE and collect a few events until terminal
    with client.stream(
        "GET", f"/mcp/progress/{job_id}?interval_ms=50", headers={"X-API-Key": "k"}
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
