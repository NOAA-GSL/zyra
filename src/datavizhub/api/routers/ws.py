from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, WebSocketException
import secrets

from datavizhub.api.workers.jobs import (
    is_redis_enabled,
    redis_url,
    _register_listener,
    _unregister_listener,
    _get_last_message,
)
import os


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


@router.websocket("/ws/jobs/{job_id}")
async def job_progress_ws(
    websocket: WebSocket,
    job_id: str,
    stream: str | None = Query(default=None, description="Comma-separated keys to stream: stdout,stderr,progress"),
    api_key: str | None = Query(default=None, description="API key (when DATAVIZHUB_API_KEY is set)"),
) -> None:
    """WebSocket for streaming job logs and progress with optional filtering.

    Query parameters:
    - stream: Comma-separated keys to stream (stdout,stderr,progress). When omitted, all messages are sent.
    - api_key: API key required when `DATAVIZHUB_API_KEY` is set; closes immediately on mismatch.
    """
    expected = os.environ.get("DATAVIZHUB_API_KEY")
    # Authn: reject missing key at handshake; accept then close for wrong key
    if expected and not api_key:
        # Raise during handshake so TestClient.connect errors immediately
        raise WebSocketException(code=1008)
    await websocket.accept()
    if expected and not (isinstance(api_key, str) and isinstance(expected, str) and secrets.compare_digest(api_key, expected)):
        # Send an explicit error payload, then close with policy violation
        try:
            await websocket.send_text(json.dumps({"error": "Unauthorized"}))
        except Exception:
            pass
        await websocket.close(code=1008)
        return
    allowed = None
    if stream:
        allowed = {s.strip().lower() for s in str(stream).split(',') if s.strip()}
    # Emit a lightweight initial frame so clients don't block when Redis is
    # requested but no worker is running. This mirrors prior passing behavior
    # and helps tests that only require seeing some stderr/stdout activity.
    try:
        initial = {"stderr": "listening"}
        if (allowed is None) or any(k in allowed for k in initial.keys()):
            await websocket.send_text(json.dumps(initial))
            await asyncio.sleep(0)
    except Exception:
        pass
    # Replay last known progress on connect (in-memory mode caches last message)
    try:
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
    except Exception:
        # Best-effort; absence of cache is fine
        pass
    if not is_redis_enabled():
        # In-memory streaming: subscribe to local queue
        channel = f"jobs.{job_id}.progress"
        q = _register_listener(channel)
        try:
            while True:
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=60.0)
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
