from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from datavizhub.api.workers.jobs import USE_REDIS, REDIS_URL, _register_listener, _unregister_listener
import os


router = APIRouter(tags=["ws"])


def _ws_should_send(text: str, allowed: set[str] | None) -> bool:
    """Return True when a JSON message contains at least one allowed key.

    This helper is used to filter WebSocket traffic server-side in both Redis
    and in-memory streaming modes.
    """
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
    await websocket.accept()
    expected = os.environ.get("DATAVIZHUB_API_KEY")
    if expected and api_key != expected:
        # Fail-fast: immediately close without sending a payload
        await websocket.close(code=1008)
        return
    allowed = None
    if stream:
        allowed = {s.strip().lower() for s in str(stream).split(',') if s.strip()}
    if not USE_REDIS:
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
        

    import redis.asyncio as aioredis  # type: ignore

    redis = aioredis.from_url(REDIS_URL)
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
