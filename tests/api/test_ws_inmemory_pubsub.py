# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json

from zyra.api.workers.jobs import _pub, _register_listener, _unregister_listener


def test_inmemory_pubsub_receives_messages() -> None:
    channel = "jobs.test.progress"
    q = _register_listener(channel)
    try:
        msg = {"progress": 0.25}
        _pub(channel, msg)
        # Queue is asyncio.Queue[str], but put_nowait already enqueued a JSON string
        text = q.get_nowait()
        data = json.loads(text)
        assert data.get("progress") == 0.25
    finally:
        _unregister_listener(channel, q)
