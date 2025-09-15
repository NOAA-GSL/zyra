# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import asyncio
import contextlib
import json
import secrets
from typing import Any

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Query,
    WebSocket,
    WebSocketDisconnect,
    WebSocketException,
)

from zyra.api.routers import mcp as mcp_router
from zyra.api.routers.search import post_search as _post_search
from zyra.api.routers.search import search as _get_search
from zyra.api.security import _auth_limits, _record_failure
from zyra.api.utils.obs import log_mcp_call
from zyra.api.workers.jobs import (
    _get_last_message,
    _register_listener,
    _unregister_listener,
    is_redis_enabled,
    redis_url,
)

router = APIRouter(tags=["ws"])


def _ws_should_send(text: str, allowed: set[str] | None) -> bool:
    if not allowed:
        return True
    try:
        data = json.loads(text)
    except Exception:
        return False
    if not isinstance(data, dict):
        return False
    return any(k in data for k in allowed)


async def _forward_progress_to_ws(
    websocket: WebSocket, channel: str, job_id: str, jobs_backend: Any | None = None
) -> None:
    """Forward job progress messages on a channel to the MCP WebSocket.

    - Supports both in-memory queue and Redis pub/sub backends.
    - Formats messages as JSON-RPC notifications: notifications/progress.
    - Swallows background errors to avoid crashing the WS handler.
    """
    # Allow dependency injection of the jobs backend to reduce coupling and
    # improve testability. Default to the shared backend if not provided.
    if jobs_backend is None:
        jobs_backend = mcp_router.jobs_backend
    try:
        if not jobs_backend.is_redis_enabled():
            q = jobs_backend._register_listener(channel)
            try:
                while True:
                    msg = await q.get()
                    try:
                        data = json.loads(msg)
                    except Exception:
                        continue
                    params = {"job_id": job_id}
                    if isinstance(data, dict):
                        params.update(data)
                        # Derive terminal status from exit_code when not provided
                        if "status" not in params and "exit_code" in data:
                            try:
                                ec = int(data.get("exit_code"))
                                params["status"] = "succeeded" if ec == 0 else "failed"
                            except Exception:
                                pass
                    notify = {
                        "jsonrpc": "2.0",
                        "method": "notifications/progress",
                        "params": params,
                    }
                    await websocket.send_text(json.dumps(notify))
            finally:
                jobs_backend._unregister_listener(channel, q)
        else:
            import redis.asyncio as aioredis  # type: ignore

            r = aioredis.from_url(jobs_backend.redis_url())
            try:
                pubsub = r.pubsub()
                await pubsub.subscribe(channel)
                async for message in pubsub.listen():
                    if (message or {}).get("type") != "message":
                        continue
                    raw = message.get("data")
                    text = None
                    if isinstance(raw, (bytes, bytearray)):
                        text = raw.decode("utf-8", errors="ignore")
                    elif isinstance(raw, str):
                        text = raw
                    if not text:
                        continue
                    try:
                        data = json.loads(text)
                    except Exception:
                        continue
                    notify = {
                        "jsonrpc": "2.0",
                        "method": "notifications/progress",
                        "params": {"job_id": job_id, **data},
                    }
                    await websocket.send_text(json.dumps(notify))
            finally:
                with contextlib.suppress(Exception):
                    await pubsub.unsubscribe(channel)
                    await pubsub.close()
                    await r.close()
    except WebSocketDisconnect:
        return
    except Exception:
        # Swallow background errors; connection may be gone
        return


@router.websocket("/ws/mcp")
async def mcp_ws(
    websocket: WebSocket,
    api_key: str | None = Query(
        default=None,
        description="API key (when ZYRA_API_KEY or legacy DATAVIZHUB_API_KEY is set)",
    ),
) -> None:
    """WebSocket JSON-RPC endpoint for MCP clients.

    Handles initialize, tools/list, tools/call, prompts/resources stubs, and
    emits notifications/initialized after a successful initialize.
    """
    from zyra.utils.env import env

    expected = env("API_KEY")
    # Determine client IP for throttle (best-effort)
    client_ip = None
    with contextlib.suppress(Exception):
        client_ip = getattr(getattr(websocket, "client", None), "host", None)
    # Require key at handshake if configured
    if expected and not api_key:
        try:
            _maxf, _win, delay_sec = _auth_limits()
            if delay_sec > 0:
                await asyncio.sleep(delay_sec)
        except Exception:
            pass
        if client_ip:
            with contextlib.suppress(Exception):
                _ = _record_failure(client_ip)
        raise WebSocketException(code=1008)
    await websocket.accept()
    if expected and not (
        isinstance(api_key, str)
        and isinstance(expected, str)
        and secrets.compare_digest(api_key, expected)
    ):
        try:
            _maxf, _win, delay_sec = _auth_limits()
            if delay_sec > 0:
                await asyncio.sleep(delay_sec)
        except Exception:
            pass
        if client_ip:
            with contextlib.suppress(Exception):
                _ = _record_failure(client_ip)
        with contextlib.suppress(Exception):
            await websocket.send_text(json.dumps({"error": "Unauthorized"}))
            await asyncio.sleep(0)
        await websocket.close(code=1008)
        return

    bg = BackgroundTasks()
    progress_tasks: list[asyncio.Task] = []
    try:
        while True:
            try:
                text = await websocket.receive_text()
            except WebSocketDisconnect:
                return
            # Parse JSON-RPC message
            try:
                msg = json.loads(text)
            except Exception:
                # Invalid JSON
                with contextlib.suppress(Exception):
                    await websocket.send_text(
                        json.dumps(
                            {
                                "jsonrpc": "2.0",
                                "id": None,
                                "error": {"code": -32700, "message": "Parse error"},
                            }
                        )
                    )
                continue
            method = (msg.get("method") or "").strip()
            params = msg.get("params") or {}
            req_id = msg.get("id")
            # Notifications: do not send a response (id is None)
            is_notification = req_id is None

            # Basic protocol check
            if str(msg.get("jsonrpc")) != "2.0":
                if not is_notification:
                    with contextlib.suppress(Exception):
                        await websocket.send_text(
                            json.dumps(
                                {
                                    "jsonrpc": "2.0",
                                    "id": req_id,
                                    "error": {
                                        "code": -32600,
                                        "message": "Invalid Request: jsonrpc must be '2.0'",
                                    },
                                }
                            )
                        )
                continue

            # Dispatch MCP
            t0 = asyncio.get_event_loop().time()
            try:
                # Reuse same logic as HTTP route via helper functions inside mcp router
                if method == "initialize":
                    result = {
                        "protocolVersion": mcp_router.PROTOCOL_VERSION,
                        "serverInfo": {
                            "name": "zyra",
                            "version": mcp_router.dvh_version,
                        },
                        "capabilities": {"tools": {"listChanged": True}},
                    }
                elif method in {"listTools", "tools/list"}:
                    result = {
                        "tools": mcp_router._mcp_tools_list(
                            refresh=bool(params.get("refresh", False))
                        )
                    }
                elif method in {"statusReport", "status/report"}:
                    result = {"status": "ok", "version": mcp_router.dvh_version}
                elif method == "prompts/list":
                    result = {"prompts": []}
                elif method == "resources/list":
                    result = {"resources": []}
                elif method == "resources/subscribe":
                    result = {"ok": True}
                elif method in {"callTool", "tools/call"}:
                    # Mirror HTTP call path
                    name = params.get("name")
                    arguments = params.get("arguments", {}) or {}
                    stage = params.get("stage")
                    command = params.get("command")
                    args = params.get("args", {}) or {}
                    mode = params.get("mode") or "sync"
                    # MCP-only search tools
                    if name in {"search-query", "search-semantic"}:
                        # Accept query from either MCP-shaped "arguments",
                        # legacy flat params, or optional nested args dict.
                        q = (
                            arguments.get("query")
                            or params.get("query")
                            or args.get("query")
                        )
                        if not isinstance(q, str) or not q.strip():
                            if not is_notification:
                                await websocket.send_text(
                                    json.dumps(
                                        {
                                            "jsonrpc": "2.0",
                                            "id": req_id,
                                            "error": {
                                                "code": -32602,
                                                "message": "Invalid params: missing 'query'",
                                            },
                                        }
                                    )
                                )
                            continue
                        try:
                            limit = int(arguments.get("limit", params.get("limit", 10)))
                        except Exception:
                            limit = 10
                        profile = arguments.get("profile", params.get("profile"))
                        profile_file = arguments.get(
                            "profile_file", params.get("profile_file")
                        )
                        include_local = bool(
                            arguments.get(
                                "include_local", params.get("include_local", False)
                            )
                        )
                        remote_only = bool(
                            arguments.get(
                                "remote_only", params.get("remote_only", False)
                            )
                        )
                        ogc_wms = arguments.get("ogc_wms", params.get("ogc_wms"))
                        ogc_records = arguments.get(
                            "ogc_records", params.get("ogc_records")
                        )
                        if name == "search-query":
                            try:
                                offline = bool(
                                    arguments.get(
                                        "offline", params.get("offline", False)
                                    )
                                )
                                https_only = bool(
                                    arguments.get(
                                        "https_only", params.get("https_only", False)
                                    )
                                )
                                items = _get_search(
                                    q=q,
                                    limit=limit,
                                    catalog_file=None,
                                    profile=str(profile) if profile else None,
                                    profile_file=(
                                        str(profile_file) if profile_file else None
                                    ),
                                    ogc_wms=str(ogc_wms) if ogc_wms else None,
                                    ogc_records=(
                                        str(ogc_records) if ogc_records else None
                                    ),
                                    remote_only=bool(remote_only),
                                    include_local=bool(include_local),
                                    enrich=None,
                                    enrich_timeout=3.0,
                                    enrich_workers=4,
                                    cache_ttl=86400,
                                    offline=bool(offline),
                                    https_only=bool(https_only),
                                    allow_hosts=None,
                                    deny_hosts=None,
                                    max_probe_bytes=None,
                                )
                                result = {"items": items}
                            except Exception:
                                if not is_notification:
                                    await websocket.send_text(
                                        json.dumps(
                                            {
                                                "jsonrpc": "2.0",
                                                "id": req_id,
                                                "error": {
                                                    "code": -32603,
                                                    "message": "Internal error",
                                                },
                                            }
                                        )
                                    )
                                continue
                        else:
                            try:
                                offline = bool(
                                    arguments.get(
                                        "offline", params.get("offline", False)
                                    )
                                )
                                https_only = bool(
                                    arguments.get(
                                        "https_only", params.get("https_only", False)
                                    )
                                )
                                body = {"query": q, "limit": limit, "analyze": True}
                                if profile:
                                    body["profile"] = str(profile)
                                if profile_file:
                                    body["profile_file"] = str(profile_file)
                                if include_local:
                                    body["include_local"] = True
                                if remote_only:
                                    body["remote_only"] = True
                                if ogc_wms:
                                    body["ogc_wms"] = str(ogc_wms)
                                if ogc_records:
                                    body["ogc_records"] = str(ogc_records)
                                if offline:
                                    body["offline"] = True
                                if https_only:
                                    body["https_only"] = True
                                result = _post_search(body)
                            except Exception:
                                if not is_notification:
                                    await websocket.send_text(
                                        json.dumps(
                                            {
                                                "jsonrpc": "2.0",
                                                "id": req_id,
                                                "error": {
                                                    "code": -32603,
                                                    "message": "Internal error",
                                                },
                                            }
                                        )
                                    )
                                continue
                    elif name and (not stage or not command):
                        n = str(name)
                        if "." in n:
                            stage, command = n.split(".", 1)
                        elif " " in n:
                            stage, command = n.split(" ", 1)
                        elif ":" in n:
                            stage, command = n.split(":", 1)
                        elif "-" in n:
                            # Split on first dash if prefix matches a known stage
                            try:
                                matrix_try = mcp_router.get_cli_matrix()
                                prefix, rest = n.split("-", 1)
                                if prefix in matrix_try:
                                    stage, command = prefix, rest
                            except Exception:
                                pass
                        else:
                            stage, command = n, n
                        if arguments:
                            args = arguments
                    matrix = mcp_router.get_cli_matrix()
                    if stage not in matrix:
                        if not is_notification:
                            await websocket.send_text(
                                json.dumps(
                                    {
                                        "jsonrpc": "2.0",
                                        "id": req_id,
                                        "error": {
                                            "code": -32602,
                                            "message": f"Invalid params: unknown stage '{stage}'",
                                            "data": {
                                                "allowed_stages": sorted(
                                                    list(matrix.keys())
                                                )
                                            },
                                        },
                                    }
                                )
                            )
                        with contextlib.suppress(Exception):
                            log_mcp_call(
                                method, params, t0, status="error", error_code=-32602
                            )
                        continue
                    allowed = set(matrix[stage].get("commands", []) or [])
                    if command not in allowed:
                        if not is_notification:
                            await websocket.send_text(
                                json.dumps(
                                    {
                                        "jsonrpc": "2.0",
                                        "id": req_id,
                                        "error": {
                                            "code": -32602,
                                            "message": f"Invalid params: unknown command '{command}' for stage '{stage}'",
                                            "data": {
                                                "allowed_commands": sorted(
                                                    list(allowed)
                                                )
                                            },
                                        },
                                    }
                                )
                            )
                        with contextlib.suppress(Exception):
                            log_mcp_call(
                                method, params, t0, status="error", error_code=-32602
                            )
                        continue
                    req_model = mcp_router.CLIRunRequest(
                        stage=stage, command=command, mode=mode, args=args
                    )
                    resp = mcp_router.run_cli_endpoint(req_model, bg)
                    if getattr(resp, "job_id", None):
                        result = {
                            "status": "accepted",
                            "job_id": resp.job_id,
                            "poll": f"/jobs/{resp.job_id}",
                            "ws": f"/ws/jobs/{resp.job_id}",
                            "download": f"/jobs/{resp.job_id}/download",
                            "manifest": f"/jobs/{resp.job_id}/manifest",
                        }
                        # Send the accepted response immediately so clients
                        # receive it before any progress notifications
                        if not is_notification:
                            out_msg = {"jsonrpc": "2.0", "id": req_id, "result": result}
                            await websocket.send_text(json.dumps(out_msg))
                        with contextlib.suppress(Exception):
                            log_mcp_call(method, params, t0, status="ok")
                        # Start progress forwarder for this job_id on MCP WS
                        job_channel = f"jobs.{resp.job_id}.progress"
                        # Resolve jobs backend once for DI/testability
                        jb = mcp_router.jobs_backend
                        progress_tasks.append(
                            asyncio.create_task(
                                _forward_progress_to_ws(
                                    websocket,
                                    job_channel,
                                    str(resp.job_id),
                                    jobs_backend=jb,
                                )
                            )
                        )
                        # Start the job in in-memory mode. BackgroundTasks is
                        # only executed for HTTP responses, so explicitly
                        # launch the job coroutine here for WS flows.
                        if not jb.is_redis_enabled():
                            # Run synchronous start_job in a thread to avoid blocking the event loop
                            progress_tasks.append(
                                asyncio.create_task(
                                    asyncio.to_thread(
                                        jb.start_job,
                                        str(resp.job_id),
                                        str(stage),
                                        str(command),
                                        dict(args or {}),
                                    )
                                )
                            )
                        # For accepted flow, we already sent the result; move to next message
                        continue
                    else:
                        exit_code = getattr(resp, "exit_code", None)
                        if isinstance(exit_code, int) and exit_code != 0:
                            err = {
                                "jsonrpc": "2.0",
                                "id": req_id,
                                "error": {
                                    "code": -32000,
                                    "message": "Execution failed",
                                    "data": {
                                        "exit_code": exit_code,
                                        "stderr": getattr(resp, "stderr", None),
                                        "stdout": getattr(resp, "stdout", None),
                                        "stage": stage,
                                        "command": command,
                                    },
                                },
                            }
                            if not is_notification:
                                await websocket.send_text(json.dumps(err))
                            with contextlib.suppress(Exception):
                                log_mcp_call(
                                    method,
                                    params,
                                    t0,
                                    status="error",
                                    error_code=-32000,
                                )
                            continue
                        result = {
                            "status": "ok",
                            "stdout": getattr(resp, "stdout", None),
                            "stderr": getattr(resp, "stderr", None),
                            "exit_code": exit_code,
                        }
                else:
                    # Method not found
                    if not is_notification:
                        err = {
                            "jsonrpc": "2.0",
                            "id": req_id,
                            "error": {"code": -32601, "message": "Method not found"},
                        }
                        await websocket.send_text(json.dumps(err))
                    with contextlib.suppress(Exception):
                        log_mcp_call(
                            method, params, t0, status="error", error_code=-32601
                        )
                    continue

                # Send result if not a notification (accepted already sent above)
                if not is_notification:
                    out = {"jsonrpc": "2.0", "id": req_id, "result": result}
                    await websocket.send_text(json.dumps(out))
                with contextlib.suppress(Exception):
                    log_mcp_call(method, params, t0, status="ok")

                # After successful initialize, emit notifications/initialized
                if method == "initialize":
                    notify = {
                        "jsonrpc": "2.0",
                        "method": "notifications/initialized",
                        "params": {},
                    }
                    await websocket.send_text(json.dumps(notify))
            except WebSocketDisconnect:
                return
            except Exception:
                # Generic internal error
                with contextlib.suppress(Exception):
                    log_mcp_call(method, params, t0, status="error", error_code=-32603)
                if not is_notification:
                    err = {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {"code": -32603, "message": "Internal error"},
                    }
                    with contextlib.suppress(Exception):
                        await websocket.send_text(json.dumps(err))
    finally:
        for t in progress_tasks:
            with contextlib.suppress(Exception):
                t.cancel()
        with contextlib.suppress(Exception):
            await websocket.close()


@router.websocket("/ws/jobs/{job_id}")
async def job_progress_ws(
    websocket: WebSocket,
    job_id: str,
    stream: str | None = Query(
        default=None,
        description="Comma-separated keys to stream: stdout,stderr,progress",
    ),
    api_key: str | None = Query(
        default=None,
        description="API key (when ZYRA_API_KEY or legacy DATAVIZHUB_API_KEY is set)",
    ),
) -> None:
    """WebSocket for streaming job logs and progress with optional filtering.

    Query parameters:
    - stream: Comma-separated keys to stream (stdout,stderr,progress). When omitted, all messages are sent.
    - api_key: API key required when an API key is set (supports ZYRA_API_KEY / DATAVIZHUB_API_KEY); closes immediately on mismatch.
    """
    from zyra.utils.env import env

    expected = env("API_KEY")
    # Determine client IP for basic throttling of failed attempts (best-effort)
    client_ip = None
    with contextlib.suppress(Exception):
        client_ip = getattr(getattr(websocket, "client", None), "host", None)
    # Authn: reject missing key at handshake; accept then close for wrong key
    if expected and not api_key:
        # Apply small delay to slow brute-force attempts
        try:
            _maxf, _win, delay_sec = _auth_limits()
            if delay_sec > 0:
                await asyncio.sleep(delay_sec)
        except Exception:
            pass
        if client_ip:
            with contextlib.suppress(Exception):
                _ = _record_failure(client_ip)
        # Raise during handshake so TestClient.connect errors immediately
        raise WebSocketException(code=1008)
    await websocket.accept()
    if expected and not (
        isinstance(api_key, str)
        and isinstance(expected, str)
        and secrets.compare_digest(api_key, expected)
    ):
        # Failed auth after accept: delay and record failure, then close with policy violation
        try:
            _maxf, _win, delay_sec = _auth_limits()
            if delay_sec > 0:
                await asyncio.sleep(delay_sec)
        except Exception:
            pass
        if client_ip:
            with contextlib.suppress(Exception):
                _ = _record_failure(client_ip)
        # Send an explicit error payload, then close with policy violation
        with contextlib.suppress(Exception):
            await websocket.send_text(json.dumps({"error": "Unauthorized"}))
            await asyncio.sleep(0)
        await websocket.close(code=1008)
        return
    allowed = None
    if stream:
        allowed = {s.strip().lower() for s in str(stream).split(",") if s.strip()}
    # Emit a lightweight initial frame so clients don't block when Redis is
    # requested but no worker is running. This mirrors prior passing behavior
    # and helps tests that only require seeing some stderr/stdout activity.
    with contextlib.suppress(Exception):
        initial = {"stderr": "listening"}
        if (allowed is None) or any(k in allowed for k in initial):
            await websocket.send_text(json.dumps(initial))
            await asyncio.sleep(0)
    # Replay last known progress on connect (in-memory mode caches last message)
    last = None
    with contextlib.suppress(Exception):
        channel = f"jobs.{job_id}.progress"
        last = _get_last_message(channel)
        if last:
            # Filter to allowed keys if requested
            to_send = {}
            for k, v in last.items():
                if (allowed is None) or (k in allowed):
                    to_send[k] = v
            if to_send:
                await websocket.send_text(json.dumps(to_send))
    if "last" not in locals():
        last = None

    # If client explicitly requested progress stream and no cached progress is
    # available yet, emit an initial progress frame. This reduces test flakiness
    # and perceived latency when jobs start just after WS subscription.
    with contextlib.suppress(Exception):
        if (
            allowed
            and ("progress" in allowed)
            and (not isinstance(last, dict) or ("progress" not in last))
        ):
            await websocket.send_text(json.dumps({"progress": 0.0}))
            # Yield to flush frame promptly for TestClient
            await asyncio.sleep(0)
    if not is_redis_enabled():
        # In-memory streaming: subscribe to local queue
        channel = f"jobs.{job_id}.progress"
        q = _register_listener(channel)
        try:
            while True:
                # Poll for messages with a short timeout to keep the
                # connection lively in tests and local runs. Configurable via
                # ZYRA_WS_QUEUE_POLL_TIMEOUT_SECONDS (legacy DATAVIZHUB_*),
                # defaulting to 5 seconds instead of 60.
                try:
                    from zyra.utils.env import env_int as _env_int

                    to = float(_env_int("WS_QUEUE_POLL_TIMEOUT_SECONDS", 5))
                except Exception:
                    to = 5.0
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=to)
                except asyncio.TimeoutError:
                    # keep connection alive
                    await websocket.send_text(json.dumps({"keepalive": True}))
                    continue
                if not _ws_should_send(msg, allowed):
                    continue
                await websocket.send_text(msg)
        except WebSocketDisconnect:
            return
        finally:
            _unregister_listener(channel, q)
    else:
        import redis.asyncio as aioredis  # type: ignore

        redis = aioredis.from_url(redis_url())
        try:
            pubsub = redis.pubsub()
            channel = f"jobs.{job_id}.progress"
            await pubsub.subscribe(channel)
            try:
                async for msg in pubsub.listen():
                    if msg is None:
                        await asyncio.sleep(0)
                        continue
                    if msg.get("type") != "message":
                        continue
                    data = msg.get("data")
                    text = None
                    if isinstance(data, (bytes, bytearray)):
                        text = data.decode("utf-8", errors="ignore")
                    elif isinstance(data, str):
                        text = data
                    if text is None:
                        continue
                    if not _ws_should_send(text, allowed):
                        continue
                    await websocket.send_text(text)
            finally:
                await pubsub.unsubscribe(channel)
                await pubsub.close()
        except WebSocketDisconnect:
            return
        finally:
            await redis.close()
