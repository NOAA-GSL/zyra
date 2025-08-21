from __future__ import annotations

import json

from zyra.api.workers import jobs as jb


def test_inmemory_ws_streams_progress_and_final_payload(monkeypatch) -> None:
    # Force in-memory mode
    monkeypatch.setenv("DATAVIZHUB_USE_REDIS", "0")
    job_id = jb.submit_job("process", "convert-format", {})
    channel = f"jobs.{job_id}.progress"
    q = jb._register_listener(channel)
    try:
        # Start job synchronously (will fail quickly due to missing args, but should stream)
        jb.start_job(job_id, "process", "convert-format", {})
        # Drain messages
        msgs = []
        while True:
            try:
                text = q.get_nowait()
            except Exception:
                break
            try:
                msgs.append(json.loads(text))
            except Exception:
                pass
        # Expect at least initial progress and final payload with exit_code
        assert any("progress" in m for m in msgs), msgs
        assert any("exit_code" in m for m in msgs), msgs
    finally:
        jb._unregister_listener(channel, q)
