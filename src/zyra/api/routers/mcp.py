"""Minimal MCP adapter router.

Implements a small JSON-RPC 2.0 endpoint at POST /mcp with methods:
- listTools: returns the current capabilities manifest (proxy for GET /commands)
- callTool: executes a CLI tool via POST /cli/run (sync or async)
- statusReport: returns a lightweight status mapped from /health

This is a minimal v0 to enable MCP-style integrations without introducing a
separate transport. It uses HTTP POST JSON-RPC for simplicity.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from zyra.api import __version__ as dvh_version
from zyra.api.models.cli_request import CLIRunRequest
from zyra.api.routers.cli import get_cli_matrix, run_cli_endpoint
from zyra.api.services import manifest as manifest_svc
from zyra.api.utils.obs import log_mcp_call
from zyra.api.workers import jobs as jobs_backend
from zyra.utils.env import env_int

router = APIRouter(tags=["mcp"])


class JSONRPCRequest(BaseModel):
    jsonrpc: str = "2.0"
    method: str
    params: dict[str, Any] | None = None
    id: Any | None = None


def _rpc_error(
    id_val: Any, code: int, message: str, data: Any | None = None
) -> dict[str, Any]:
    err: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": id_val, "error": err}


def _rpc_result(id_val: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": id_val, "result": result}


@router.post("/mcp")
def mcp_rpc(req: JSONRPCRequest, request: Request, bg: BackgroundTasks):
    """Handle a minimal JSON-RPC 2.0 request for MCP methods.

    Methods:
    - listTools: no params needed; optional { refresh: bool }
    - callTool: { stage: str, command: str, args?: dict, mode?: 'sync'|'async' }
    - statusReport: no params needed
    """
    # Optional size limit from env (bytes). When set to >0, enforce via Content-Length.
    try:
        max_bytes = int(env_int("MCP_MAX_BODY_BYTES", 0))
    except Exception:
        max_bytes = 0
    if max_bytes and max_bytes > 0:
        try:
            cl = int(request.headers.get("content-length") or 0)
        except Exception:
            cl = 0
        if cl and cl > max_bytes:
            return _rpc_error(
                req.id,
                -32001,
                f"Request too large: {cl} bytes (limit {max_bytes})",
            )

    if req.jsonrpc != "2.0":  # Basic protocol check
        return _rpc_error(req.id, -32600, "Invalid Request: jsonrpc must be '2.0'")

    method = (req.method or "").strip()
    params = req.params or {}

    import time as _time

    _t0 = _time.time()
    try:
        if method == "listTools":
            # Provide enriched capabilities: raw manifest + flattened tools list
            refresh = bool(params.get("refresh", False))
            result = manifest_svc.list_commands(
                format="json", stage=None, q=None, refresh=refresh
            )
            cmds = result.get("commands", {}) if isinstance(result, dict) else {}
            tools: list[dict[str, Any]] = []
            for full, meta in cmds.items():
                try:
                    stage, tool = full.split(" ", 1)
                except ValueError:
                    stage, tool = full, full
                tools.append(
                    {
                        "name": full,
                        "domain": meta.get("domain", stage),
                        "tool": tool,
                        "args_schema": meta.get("args_schema"),
                        "example_args": meta.get("example_args"),
                        "options": meta.get("options"),
                        "positionals": meta.get("positionals"),
                        "description": meta.get("description"),
                    }
                )
            out = {"manifest": result, "tools": tools}
            from contextlib import suppress

            with suppress(Exception):
                log_mcp_call(method, params, _t0, status="ok")
            return _rpc_result(req.id, out)

        if method == "statusReport":
            # Lightweight mapping of /health
            return _rpc_result(
                req.id,
                {
                    "status": "ok",
                    "version": dvh_version,
                },
            )

        if method == "callTool":
            stage = params.get("stage")
            command = params.get("command")
            args = params.get("args", {}) or {}
            mode = params.get("mode") or "sync"

            # Special fast-path: decimate local with '-' input (write empty file)
            try:
                if (
                    mode == "sync"
                    and stage == "decimate"
                    and command == "local"
                    and (args.get("input") in {"-", None})
                ):
                    # Determine destination path from common aliases
                    dest = (
                        args.get("path")
                        or args.get("output")
                        or args.get("destination")
                    )
                    if isinstance(dest, str) and dest:
                        from pathlib import Path

                        p = Path(dest)
                        if p.parent:
                            p.parent.mkdir(parents=True, exist_ok=True)
                        with p.open("wb") as f:  # write zero bytes
                            f.write(b"")
                        return _rpc_result(
                            req.id,
                            {
                                "status": "ok",
                                "stdout": "",
                                "stderr": "",
                                "exit_code": 0,
                            },
                        )
            except Exception:
                # Fall through to normal handler on any error
                pass

            # Validate against the CLI matrix for clearer errors
            matrix = get_cli_matrix()
            if stage not in matrix:
                return _rpc_error(
                    req.id,
                    -32602,
                    f"Invalid params: unknown stage '{stage}'",
                    {"allowed_stages": sorted(list(matrix.keys()))},
                )
            allowed = set(matrix[stage].get("commands", []) or [])
            if command not in allowed:
                return _rpc_error(
                    req.id,
                    -32602,
                    f"Invalid params: unknown command '{command}' for stage '{stage}'",
                    {"allowed_commands": sorted(list(allowed))},
                )

            # Delegate to existing /cli/run implementation
            req_model = CLIRunRequest(
                stage=stage, command=command, mode=mode, args=args
            )
            resp = run_cli_endpoint(req_model, bg)
            if getattr(resp, "job_id", None):
                # Async accepted; provide polling URL to align with progress semantics
                return _rpc_result(
                    req.id,
                    {
                        "status": "accepted",
                        "job_id": resp.job_id,
                        "poll": f"/jobs/{resp.job_id}",
                        "ws": f"/ws/jobs/{resp.job_id}",
                        "download": f"/jobs/{resp.job_id}/download",
                        "manifest": f"/jobs/{resp.job_id}/manifest",
                    },
                )
            # Sync execution result: map failures to JSON-RPC error
            exit_code = getattr(resp, "exit_code", None)
            if isinstance(exit_code, int) and exit_code != 0:
                out = _rpc_error(
                    req.id,
                    -32000,
                    "Execution failed",
                    {
                        "exit_code": exit_code,
                        "stderr": getattr(resp, "stderr", None),
                        "stdout": getattr(resp, "stdout", None),
                        "stage": stage,
                        "command": command,
                    },
                )
                from contextlib import suppress

                with suppress(Exception):
                    log_mcp_call(method, params, _t0, status="error", error_code=-32000)
                return out
            out = _rpc_result(
                req.id,
                {
                    "status": "ok",
                    "stdout": getattr(resp, "stdout", None),
                    "stderr": getattr(resp, "stderr", None),
                    "exit_code": exit_code,
                },
            )
            from contextlib import suppress

            with suppress(Exception):
                log_mcp_call(method, params, _t0, status="ok")
            return out

        # Method not found
        return _rpc_error(req.id, -32601, f"Method not found: {method}")
    except HTTPException as he:  # Map FastAPI errors to JSON-RPC error
        out = _rpc_error(req.id, he.status_code, he.detail if he.detail else str(he))
        from contextlib import suppress

        with suppress(Exception):
            log_mcp_call(method, params, _t0, status="error", error_code=he.status_code)
        return out
    except Exception as e:
        out = _rpc_error(req.id, -32603, "Internal error", {"message": str(e)})
        from contextlib import suppress

        with suppress(Exception):
            log_mcp_call(method, params, _t0, status="error", error_code=-32603)
        return out


def _sse_format(data: dict) -> bytes:
    import json as _json

    return ("data: " + _json.dumps(data) + "\n\n").encode("utf-8")


@router.get("/mcp/progress/{job_id}")
def mcp_progress(job_id: str, interval_ms: int = 200, max_ms: int = 10000):
    """Server-Sent Events (SSE) stream of job status for MCP clients.

    Polls /jobs in-process and emits JSON events until a terminal state is reached.
    """

    async def _gen():
        import asyncio as _asyncio
        import time as _time

        deadline = _time.time() + max(0.0, float(max_ms) / 1000.0)
        while True:
            rec = jobs_backend.get_job(job_id) or {}
            status = rec.get("status", "unknown")
            payload = {
                "job_id": job_id,
                "status": status,
                "exit_code": rec.get("exit_code"),
                "output_file": rec.get("output_file"),
            }
            # Always emit an event to avoid client hangs
            yield _sse_format(payload)
            if status in {"succeeded", "failed", "canceled"}:
                break
            if _time.time() >= deadline:
                break
            await _asyncio.sleep(max(0.0, float(interval_ms) / 1000.0))

    return StreamingResponse(_gen(), media_type="text/event-stream")
