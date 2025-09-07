"""MCP adapter router.

Exposes a minimal JSON-RPC 2.0 interface and progress streaming for MCP clients:

- ``POST /mcp`` (JSON-RPC)
  - ``listTools``: returns the enriched capabilities manifest and a flattened tools list
    (includes domain, args_schema, example_args, options, positionals, description).
  - ``callTool``: dispatches to ``/cli/run`` (sync or async). Sync failures map to
    JSON-RPC error ``-32000`` with details in ``error.data``.
  - ``statusReport``: returns ``{ status: 'ok', version }`` mapped from ``/health``.

- ``GET /mcp/progress/{job_id}`` (SSE)
  - Emits JSON events (``data: {...}\n\n``) with ``job_id``, ``status``, ``exit_code``, ``output_file``
    until terminal status or ``max_ms`` timeout.

Notes
- Request body size limits can be enforced via ``ZYRA_MCP_MAX_BODY_BYTES``.
- Structured logs for MCP calls are emitted via the ``zyra.api.mcp`` logger.
"""
from __future__ import annotations

import logging
from contextlib import suppress
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
    """Handle a JSON-RPC 2.0 request for MCP methods.

    Methods:
    - listTools: optional { refresh: bool } — returns ``result.manifest`` and ``result.tools``.
    - callTool: { stage: str, command: str, args?: dict, mode?: 'sync'|'async' }.
      Sync failures return JSON-RPC error ``-32000``.
    - statusReport: returns MCP-ready service status and version.

    Design:
    - Avoid tool-specific fast paths; always delegate to the canonical CLI
      execution path (``/cli/run``) so behavior remains consistent and future
      changes to commands are reflected uniformly without bespoke logic here.
    """
    # Optional size limit from env (bytes). When set to >0, enforce via Content-Length.
    try:
        max_bytes = int(env_int("MCP_MAX_BODY_BYTES", 0))
    except (ValueError, TypeError):
        max_bytes = 0
    except Exception as exc:  # pragma: no cover - unexpected config/state
        # Log unexpected exceptions rather than silently masking all errors
        with suppress(Exception):
            logging.getLogger("zyra.api.mcp").warning(
                "Failed to parse MCP_MAX_BODY_BYTES: %s", exc
            )
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
            # Return spec-compatible MCP discovery payload
            refresh = bool(params.get("refresh", False))
            out = _mcp_discovery_payload(refresh=refresh)
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

        # Method not found (avoid echoing arbitrary method names verbatim)
        return _rpc_error(req.id, -32601, "Method not found")
    except HTTPException as he:  # Map FastAPI errors to JSON-RPC error
        # Do not leak internal exception details to clients
        code = int(getattr(he, "status_code", 500) or 500)
        msg = "Invalid request" if 400 <= code < 500 else "Server error"
        out = _rpc_error(req.id, code, msg)
        from contextlib import suppress

        with suppress(Exception):
            log_mcp_call(method, params, _t0, status="error", error_code=he.status_code)
        return out
    except Exception:
        # Log internally; return generic error to clients without details
        out = _rpc_error(req.id, -32603, "Internal error")
        from contextlib import suppress

        with suppress(Exception):
            log_mcp_call(method, params, _t0, status="error", error_code=-32603)
        return out


def _sse_format(data: dict) -> bytes:
    import json as _json

    return ("data: " + _json.dumps(data) + "\n\n").encode("utf-8")


def _json_type(t: str | None) -> str | None:
    if not t:
        return None
    t = t.lower()
    if t in {"str", "string"}:
        return "string"
    if t in {"int", "integer"}:
        return "integer"
    if t in {"float", "number"}:
        return "number"
    if t in {"bool", "boolean"}:
        return "boolean"
    return None


def _mcp_discovery_payload(refresh: bool = False) -> dict[str, Any]:
    """Return a spec-compatible MCP discovery payload.

    Structure:
    {
      "mcp_version": "0.1",
      "name": "zyra",
      "description": "...",
      "capabilities": { "commands": [ { name, description, parameters } ] }
    }
    """
    result = manifest_svc.list_commands(
        format="json", stage=None, q=None, refresh=refresh
    )
    cmds = result.get("commands", {}) if isinstance(result, dict) else {}
    commands: list[dict[str, Any]] = []
    for full, meta in cmds.items():
        # Build name as stage.tool (e.g., "process.decode-grib2")
        try:
            stage, tool = full.split(" ", 1)
        except ValueError:
            stage, tool = full, full
        name = f"{stage}.{tool}"

        # Build JSON Schema parameters from options + positionals
        properties: dict[str, Any] = {}
        required: list[str] = []

        # Positionals: add as required named properties
        for pos in meta.get("positionals") or []:
            if not isinstance(pos, dict):
                continue
            pname = str(pos.get("name") or "arg").strip()
            if not pname:
                continue
            ptype = _json_type(str(pos.get("type") or ""))
            schema: dict[str, Any] = {}
            if ptype:
                schema["type"] = ptype
            if pos.get("choices"):
                schema["enum"] = list(pos.get("choices"))
            if pos.get("help"):
                schema["description"] = pos.get("help")
            properties[pname] = schema or {"type": "string"}
            if bool(pos.get("required", False)):
                required.append(pname)

        # Options: prefer long flags ("--flag"), convert to property names
        opts = meta.get("options") or {}
        seen: set[str] = set()
        for flag, o in opts.items():
            if not isinstance(flag, str) or not flag.startswith("--"):
                continue
            prop = flag.lstrip("-").replace("-", "_")
            if prop in seen:
                continue
            seen.add(prop)
            if not isinstance(o, dict):
                properties[prop] = {"type": "string"}
                continue
            jtype = _json_type(str(o.get("type") or ""))
            schema: dict[str, Any] = {}
            if jtype:
                schema["type"] = jtype
            if o.get("help"):
                schema["description"] = o.get("help")
            if o.get("choices"):
                from contextlib import suppress as _suppress

                with _suppress(Exception):
                    schema["enum"] = list(o.get("choices"))
            # We don't currently track required options; leave optional
            properties[prop] = schema or {"type": "string"}
            from contextlib import suppress as _suppress

            with _suppress(Exception):
                if bool(o.get("required")):
                    required.append(prop)

        parameters: dict[str, Any] = {
            "type": "object",
            "properties": properties,
        }
        if required:
            parameters["required"] = sorted(required)

        commands.append(
            {
                "name": name,
                "description": meta.get("description", f"zyra {full}"),
                "parameters": parameters,
            }
        )

    return {
        "mcp_version": "0.1",
        "name": "zyra",
        "description": "Zyra MCP server for domain-specific data visualization",
        "capabilities": {"commands": commands},
    }


@router.get("/mcp")
def mcp_capabilities(refresh: bool = False) -> dict[str, Any]:
    """HTTP discovery endpoint for MCP clients (Cursor/Claude/VS Code)."""
    return _mcp_discovery_payload(refresh=refresh)


@router.options("/mcp")
def mcp_capabilities_options(refresh: bool = False) -> dict[str, Any]:
    """OPTIONS variant returning the same MCP discovery payload."""
    return _mcp_discovery_payload(refresh=refresh)


@router.get("/mcp/progress/{job_id}")
def mcp_progress(job_id: str, interval_ms: int = 200, max_ms: int = 10000):
    """Server-Sent Events (SSE) stream of job status for MCP clients.

    Emits JSON events on each tick with ``job_id``, ``status``, ``exit_code``,
    and ``output_file`` until terminal status (``succeeded``|``failed``|``canceled``)
    or ``max_ms`` timeout.
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
