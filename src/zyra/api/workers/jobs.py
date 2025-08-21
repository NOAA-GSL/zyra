from __future__ import annotations

import asyncio
import contextlib
import io
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Any

from zyra.api.workers.executor import (
    _args_dict_to_argv,
    resolve_upload_placeholders,
    write_manifest,
    zip_output_dir,
)


def is_redis_enabled() -> bool:
    """Enable Redis only when explicitly requested AND reachable.

    - Requires ZYRA_USE_REDIS (or legacy DATAVIZHUB_USE_REDIS) to be truthy (1/true/yes)
    - Requires `redis` and `rq` to be importable
    - Requires a fast PING to succeed (<= 0.25s connect timeout)
    Falls back to in-memory otherwise to keep tests and local runs robust.
    """
    from zyra.utils.env import env

    use_env = (env("USE_REDIS", "0") or "0").lower() in {
        "1",
        "true",
        "yes",
    }
    if not use_env:
        return False
    try:
        import redis  # type: ignore
        import rq  # noqa: F401  # type: ignore
    except Exception:
        return False
    try:
        url = redis_url()
        # Validate URL format defensively
        if not _is_valid_redis_url(url):
            return False
        client = redis.Redis.from_url(url, socket_connect_timeout=1.0)  # type: ignore[arg-type]
        client.ping()
        return True
    except Exception:
        return False


def redis_url() -> str:
    from zyra.utils.env import env

    # Allow non-prefixed REDIS_URL as an escape hatch, but prefer ZYRA_*/legacy order
    return env("REDIS_URL") or os.environ.get("REDIS_URL", "redis://localhost:6379/0")


def queue_name() -> str:
    from zyra.utils.env import env

    return env("QUEUE", "zyra") or "zyra"


_redis_client = None
_rq_queue = None

# In-memory pub/sub for WebSocket parity
# Store (queue, loop) to support thread-safe puts into the listener's event loop.
_SUBSCRIBERS: dict[
    str, list[tuple[asyncio.Queue[str], asyncio.AbstractEventLoop | None]]
] = {}
# In-memory last-message cache per channel for quick replay on new subscribers
_LAST_MESSAGES: dict[str, dict[str, Any]] = {}


def _register_listener(channel: str) -> asyncio.Queue[str]:
    """Register an in-memory subscriber queue for a pub/sub channel.

    Used by the WebSocket router in in-memory mode to stream job messages
    without Redis. Returns an asyncio.Queue that receives JSON strings.
    """
    q: asyncio.Queue[str] = asyncio.Queue()
    with contextlib.suppress(RuntimeError):
        loop = asyncio.get_running_loop()
    if "loop" not in locals():
        loop = None
    _SUBSCRIBERS.setdefault(channel, []).append((q, loop))
    return q


def _unregister_listener(channel: str, q: asyncio.Queue[str]) -> None:
    """Unregister a previously registered in-memory subscriber queue."""
    lst = _SUBSCRIBERS.get(channel)
    if not lst:
        return
    try:
        for i, (qq, _loop) in enumerate(list(lst)):
            if qq is q:
                lst.pop(i)
                break
    except ValueError:
        pass
    if not lst:
        _SUBSCRIBERS.pop(channel, None)


def _get_redis_and_queue():  # lazy init to avoid hard dependency
    global _redis_client, _rq_queue
    if _redis_client is None:
        from redis import Redis

        url = redis_url()
        if not _is_valid_redis_url(url):
            raise RuntimeError("Invalid Redis URL in environment")
        _redis_client = Redis.from_url(url)
    if _rq_queue is None:
        from rq import Queue

        _rq_queue = Queue(queue_name(), connection=_redis_client)
    return _redis_client, _rq_queue


def _pub(channel: str, message: dict[str, Any]) -> None:
    """Publish a message to a channel (Redis when enabled; in-memory otherwise).

    Messages are JSON-serialized dictionaries. In-memory subscribers receive
    the serialized string on their per-channel queues.
    """
    payload = json.dumps(message)
    if not is_redis_enabled():
        # Update last-message cache (shallow merge by keys)
        try:
            if isinstance(message, dict):
                last = _LAST_MESSAGES.get(channel) or {}
                last.update(message)
                _LAST_MESSAGES[channel] = last
        except Exception:
            pass
        # Broadcast to in-memory subscribers; respect listener loop if running
        for q, loop in list(_SUBSCRIBERS.get(channel, []) or []):
            try:
                if loop is not None and loop.is_running():
                    loop.call_soon_threadsafe(q.put_nowait, payload)
                else:
                    q.put_nowait(payload)
            except Exception:
                continue
        return
    r, _q = _get_redis_and_queue()
    with contextlib.suppress(Exception):
        # Best effort publish; do not crash job
        r.publish(channel, payload)


def _get_last_message(channel: str) -> dict[str, Any] | None:
    """Return the last cached message dict for a channel (in-memory mode only)."""
    if is_redis_enabled():
        return None
    try:
        v = _LAST_MESSAGES.get(channel)
        return dict(v) if isinstance(v, dict) else None
    except Exception:
        return None


class _PubTee(io.StringIO):
    """A tee-like writer that appends written text to an internal buffer and
    publishes each chunk to Redis pub/sub as a JSON message under a given key
    (e.g., 'stdout' or 'stderr')."""

    def __init__(self, channel: str, key: str):
        super().__init__()
        self._channel = channel
        self._key = key

    def write(self, s: str) -> int:  # type: ignore[override]
        if not s:
            return 0
        n = super().write(s)
        with contextlib.suppress(Exception):
            _pub(self._channel, {self._key: s})
        return n


def run_cli_job(
    stage: str, command: str, args: dict[str, Any], job_id: str | None = None
) -> dict[str, Any]:
    """RQ worker entry: run the CLI and stream progress/logs.

    Behavior
    - Resolves uploaded ``file_id:`` placeholders for convenience.
    - Publishes an initial progress payload ``{"progress": 0.0}`` to the per-job
      channel ``jobs.{job_id}.progress`` when a job id is available.
    - Streams stdout/stderr incrementally by swapping ``sys.stdout``/``sys.stderr``
      for a tee writer (``_PubTee``) that both buffers and publishes each write
      as a JSON message (e.g., ``{"stdout": "..."}``). Works in both Redis and
      in-memory modes via ``_pub``.
    - On completion, publishes a final payload including ``stdout``, ``stderr``,
      ``exit_code``, and optionally ``output_file`` when artifacts are persisted
      into the results directory. A manifest is written on best effort.
    """
    if job_id is None:
        try:
            from rq import get_current_job

            _job = get_current_job()
            job_id = _job.id if _job else None
        except Exception:
            job_id = None
    channel = f"jobs.{job_id}.progress" if job_id else None
    if channel:
        _pub(channel, {"progress": 0.0})
    # Resolve uploads for visibility and run
    args_resolved, resolved_paths, _unresolved = resolve_upload_placeholders(args)
    # Build argv and run with streaming publishers if Redis is enabled
    argv = _args_dict_to_argv(stage, command, args_resolved)
    # Capture stdio with publishers
    stdout_buf = _PubTee(channel, "stdout") if channel else io.StringIO()
    stderr_buf = _PubTee(channel, "stderr") if channel else io.StringIO()
    old_out, old_err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = stdout_buf, stderr_buf
    try:
        code = 0
        try:
            from zyra.cli import main as cli_main

            code = cli_main(argv)
            if not isinstance(code, int):
                code = int(code) if code is not None else 0
        except SystemExit as exc:
            code = int(getattr(exc, "code", 1) or 0)
        except Exception as exc:  # pragma: no cover
            print(str(exc), file=sys.stderr)
            code = 1
    finally:
        sys.stdout, sys.stderr = old_out, old_err

    payload: dict[str, Any] = {
        "stdout": stdout_buf.getvalue(),
        "stderr": stderr_buf.getvalue(),
        "exit_code": code,
        "progress": 1.0,
    }
    if resolved_paths:
        payload["resolved_input_paths"] = resolved_paths
    # Persist output artifact if present
    try:
        # Results dir
        from zyra.utils.env import env

        results_root = Path(
            env("RESULTS_DIR", "/tmp/zyra_results") or "/tmp/zyra_results"
        )
        if job_id:
            results_dir = results_root / job_id
            results_dir.mkdir(parents=True, exist_ok=True)
            # Zip output_dir if present
            out_file = None
            if isinstance(args.get("output_dir"), str):
                z = zip_output_dir(job_id, args.get("output_dir"))
                if z:
                    out_file = z

            # Prefer explicit outputs
            candidates = []
            if isinstance(args.get("to_video"), str):
                candidates.append(args.get("to_video"))
            if isinstance(args.get("output"), str):
                candidates.append(args.get("output"))
            if isinstance(args.get("path"), str):
                candidates.append(args.get("path"))
            for p in candidates:
                try:
                    if p and Path(p).is_file():
                        src = Path(p)
                        dest = results_dir / src.name
                        if src.resolve() != dest.resolve():
                            shutil.copy2(src, dest)
                        out_file = str(dest)
                        break
                except Exception:
                    continue
            if not out_file and stdout_buf.getvalue():
                # Binary-safe: stdout_buf here is StringIO; also attach bytes from publishers via payload?
                # For Redis path we only have text; write as .txt
                dest = results_dir / "output.txt"
                dest.write_text(stdout_buf.getvalue(), encoding="utf-8")
                out_file = str(dest)
            if out_file:
                payload["output_file"] = out_file
            # Write manifest listing all artifacts
            with contextlib.suppress(Exception):
                write_manifest(job_id)
    except Exception:
        pass
    if channel:
        _pub(channel, payload)
    return payload


# In-memory fallback (used when USE_REDIS is false)
# NOTE: This job store is scoped to the API layer to integrate pub/sub streaming
# and Redis-compatible semantics when Redis is disabled. It is distinct from
# zyra.api.workers.executor._JOBS, which backs the low-level CLI execution
# helpers and some unit tests. Keeping the stores separate avoids tight coupling
# and circular imports. They serve different purposes but share similar shapes.
_JOBS: dict[str, dict[str, Any]] = {}


def _jobs_ttl_seconds() -> int:
    """TTL (seconds) for completed in-memory jobs before cleanup.

    Controlled via env ZYRA_JOBS_TTL_SECONDS (or legacy DATAVIZHUB_JOBS_TTL_SECONDS, default: 3600). Use 0 or a
    negative value to disable automatic cleanup. Mirrors executor-side policy.
    """
    try:
        from zyra.utils.env import env_int

        return env_int("JOBS_TTL_SECONDS", 3600)
    except Exception:
        return 3600


def _cleanup_jobs() -> None:
    ttl = _jobs_ttl_seconds()
    if ttl <= 0:
        return
    now = time.time()
    to_delete: list[str] = []
    for jid, rec in list(_JOBS.items()):
        try:
            status = rec.get("status")
            if status in {"succeeded", "failed", "canceled"}:
                ts_val = rec.get("updated_at") or rec.get("created_at")
                if ts_val is None:
                    # Initialize a timestamp to now to avoid premature deletion
                    rec["updated_at"] = now
                    continue
                ts = float(ts_val)
                if (now - ts) > ttl:
                    to_delete.append(jid)
        except Exception:
            continue
    for jid in to_delete:
        with contextlib.suppress(Exception):
            _JOBS.pop(jid, None)


def submit_job(stage: str, command: str, args: dict[str, Any]) -> str:
    if is_redis_enabled():
        r, q = _get_redis_and_queue()
        # Create a placeholder job id by enqueuing with meta; we need job id to publish channel messages
        job = q.enqueue(run_cli_job, stage, command, args)  # type: ignore[arg-type]
        return job.get_id()
    else:
        import uuid

        _cleanup_jobs()
        job_id = uuid.uuid4().hex
        _JOBS[job_id] = {
            "status": "queued",
            "stdout": "",
            "stderr": "",
            "exit_code": None,
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        # For API symmetry, we only enqueue here; caller should start background task
        return job_id


def start_job(job_id: str, stage: str, command: str, args: dict[str, Any]) -> None:
    if is_redis_enabled():
        # When using Redis/RQ, jobs are started by workers; nothing to do here
        return
    # In-memory execution: run inline and update this module's job store
    rec = _JOBS.get(job_id)
    if not rec:
        return
    rec["status"] = "running"
    rec["updated_at"] = time.time()
    args_resolved, resolved_paths, _unresolved = resolve_upload_placeholders(args)
    # Streaming execution with in-memory pub/sub
    channel = f"jobs.{job_id}.progress"
    _pub(channel, {"progress": 0.0})
    # Capture stdio with publishers (similar to Redis worker path)
    import io
    import sys

    class _LocalPubTee(io.StringIO):
        def __init__(self, key: str):
            super().__init__()
            self._key = key

        def write(self, s: str) -> int:  # type: ignore[override]
            if not s:
                return 0
            n = super().write(s)
            with contextlib.suppress(Exception):
                _pub(channel, {self._key: s})
            return n

    out_buf = _LocalPubTee("stdout")
    err_buf = _LocalPubTee("stderr")
    old_out, old_err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = out_buf, err_buf
    code = 0
    try:
        try:
            from zyra.cli import main as cli_main

            code = cli_main(_args_dict_to_argv(stage, command, args_resolved))  # type: ignore[arg-type]
            if not isinstance(code, int):
                code = int(code) if code is not None else 0
        except SystemExit as exc:
            code = int(getattr(exc, "code", 1) or 0)
        except Exception as exc:  # pragma: no cover
            print(str(exc), file=sys.stderr)
            code = 1
    finally:
        sys.stdout, sys.stderr = old_out, old_err
    rec["stdout"] = out_buf.getvalue()
    rec["stderr"] = err_buf.getvalue()
    rec["exit_code"] = code
    # Persist output artifact similar to Redis path
    try:
        from zyra.utils.env import env

        results_root = Path(
            env("RESULTS_DIR", "/tmp/zyra_results") or "/tmp/zyra_results"
        )
        results_dir = results_root / job_id
        results_dir.mkdir(parents=True, exist_ok=True)
        out_file = None
        # Zip output_dir first if present
        if isinstance(args.get("output_dir"), str):
            z = zip_output_dir(job_id, args.get("output_dir"))
            if z:
                out_file = z
        candidates = []
        if isinstance(args.get("to_video"), str):
            candidates.append(args.get("to_video"))
        if isinstance(args.get("output"), str):
            candidates.append(args.get("output"))
        if isinstance(args.get("path"), str):
            candidates.append(args.get("path"))
        for p in candidates:
            try:
                if p and Path(p).is_file():
                    src = Path(p)
                    dest = results_dir / src.name
                    if src.resolve() != dest.resolve():
                        shutil.copy2(src, dest)
                    out_file = str(dest)
                    break
            except Exception:
                continue
        if not out_file and rec.get("stdout"):
            # Persist textual stdout as a file for convenience
            dest = results_dir / "output.txt"
            dest.write_text(rec.get("stdout", ""), encoding="utf-8")
            out_file = str(dest)
        rec["output_file"] = out_file
        if resolved_paths:
            rec["resolved_input_paths"] = resolved_paths
        # Write manifest listing all artifacts
        with contextlib.suppress(Exception):
            write_manifest(job_id)
    except Exception:
        rec["output_file"] = None
    payload = {
        "stdout": rec["stdout"],
        "stderr": rec["stderr"],
        "exit_code": rec["exit_code"],
        "progress": 1.0,
    }
    if rec.get("output_file"):
        payload["output_file"] = rec["output_file"]
    _pub(channel, payload)
    rec["status"] = "succeeded" if code == 0 else "failed"
    rec["updated_at"] = time.time()
    _cleanup_jobs()


def get_job(job_id: str) -> dict[str, Any] | None:
    if is_redis_enabled():
        from rq.job import Job

        r, _q = _get_redis_and_queue()
        job = Job.fetch(job_id, connection=r)
        # Derive a simple status and attach result if available
        status_map = {
            "queued": "queued",
            "started": "running",
            "deferred": "queued",
            "finished": "succeeded",
            "failed": "failed",
            "canceled": "canceled",
        }
        status = status_map.get(job.get_status(refresh=False), "queued")
        result = job.result if status == "succeeded" else None
        return {
            "status": status,
            "stdout": (result or {}).get("stdout")
            if isinstance(result, dict)
            else None,
            "stderr": (result or {}).get("stderr")
            if isinstance(result, dict)
            else None,
            "exit_code": (result or {}).get("exit_code")
            if isinstance(result, dict)
            else None,
            "output_file": (result or {}).get("output_file")
            if isinstance(result, dict)
            else None,
        }
    else:
        _cleanup_jobs()
        return _JOBS.get(job_id)


def cancel_job(job_id: str) -> bool:
    if is_redis_enabled():
        from rq.job import Job

        r, _q = _get_redis_and_queue()
        try:
            job = Job.fetch(job_id, connection=r)
            job.cancel()
            return True
        except Exception:
            return False
    else:
        rec = _JOBS.get(job_id)
        if not rec:
            return False
        if rec.get("status") == "queued":
            rec["status"] = "canceled"
            rec["updated_at"] = time.time()
            return True
        return False


def _is_valid_redis_url(url: str) -> bool:
    """Conservative validation for redis://host[:port][/db] to avoid unsafe values from env."""
    try:
        return bool(re.fullmatch(r"redis://[A-Za-z0-9._-]+(?::\d{1,5})?(?:/\d+)?", url))
    except Exception:
        return False
