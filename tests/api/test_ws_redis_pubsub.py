# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
import os
import time

import pytest


@pytest.mark.redis
def test_redis_pubsub_roundtrip(monkeypatch):
    # Skip if redis or redis server is not available
    try:
        import redis  # type: ignore
    except Exception:
        pytest.skip("redis package not installed")

    from zyra.api.workers import jobs as jb

    # Force Redis mode; ensure cleanup via monkeypatch
    monkeypatch.setenv("DATAVIZHUB_USE_REDIS", "1")
    monkeypatch.setattr(jb, "USE_REDIS", True, raising=False)

    url = os.environ.get("DATAVIZHUB_REDIS_URL", "redis://localhost:6379/0")
    try:
        client = redis.Redis.from_url(url)
        client.ping()
    except Exception:
        pytest.skip(f"Redis not available at {url}")

    channel = "jobs.redis.test.progress"
    pubsub = client.pubsub()
    pubsub.subscribe(channel)
    try:
        # Publish via _pub()
        jb._pub(channel, {"progress": 0.42})
        deadline = time.time() + 2.0
        got = None
        while time.time() < deadline:
            msg = pubsub.get_message(timeout=0.2)
            if msg and msg.get("type") == "message":
                data = msg.get("data")
                if isinstance(data, (bytes, bytearray)):
                    data = data.decode("utf-8", "ignore")
                try:
                    js = json.loads(data)
                    got = js
                    break
                except Exception:
                    pass
        assert got and got.get("progress") == 0.42
    finally:
        pubsub.unsubscribe(channel)
        pubsub.close()
