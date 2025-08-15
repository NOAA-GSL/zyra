from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional, List
import asyncio

import io
import sys
from datavizhub.api.workers.executor import (
    run_cli,
    _args_dict_to_argv,
    zip_output_dir,
    write_manifest,
    resolve_upload_placeholders,
)
import os
from pathlib import Path
import shutil


def is_redis_enabled() -> bool:
    return os.environ.get("DATAVIZHUB_USE_REDIS", "0").lower() in {"1", "true", "yes"}

def redis_url() -> str:
    return os.environ.get("DATAVIZHUB_REDIS_URL", os.environ.get("REDIS_URL", "redis://localhost:6379/0"))

REDIS_URL = redis_url()
QUEUE_NAME = os.environ.get("DATAVIZHUB_QUEUE", "datavizhub")


_redis_client = None
_rq_queue = None

# In-memory pub/sub for WebSocket parity
_SUBSCRIBERS: Dict[str, List[asyncio.Queue[str]]] = {}


def _register_listener(channel: str) -> asyncio.Queue[str]:
    """Register an in-memory subscriber queue for a pub/sub channel.

    Used by the WebSocket router in in-memory mode to stream job messages
    without Redis. Returns an asyncio.Queue that receives JSON strings.
    """
    q: asyncio.Queue[str] = asyncio.Queue()
    _SUBSCRIBERS.setdefault(channel, []).append(q)
    return q


def _unregister_listener(channel: str, q: asyncio.Queue[str]) -> None:
    """Unregister a previously registered in-memory subscriber queue."""
    lst = _SUBSCRIBERS.get(channel)
    if not lst:
        return
    try:
        lst.remove(q)
    except ValueError:
        pass
    if not lst:
        _SUBSCRIBERS.pop(channel, None)


def _get_redis_and_queue():  # lazy init to avoid hard dependency
    global _redis_client, _rq_queue
    if _redis_client is None:
        from redis import Redis

        _redis_client = Redis.from_url(REDIS_URL)
    if _rq_queue is None:
        from rq import Queue

        _rq_queue = Queue(QUEUE_NAME, connection=_redis_client)
    return _redis_client, _rq_queue


def _pub(channel: str, message: Dict[str, Any]) -> None:
    """Publish a message to a channel (Redis when enabled; in-memory otherwise).

    Messages are JSON-serialized dictionaries. In-memory subscribers receive
    the serialized string on their per-channel queues.
    """
    payload = json.dumps(message)
    if not is_redis_enabled():
        # Broadcast to in-memory subscribers
        for q in list(_SUBSCRIBERS.get(channel, []) or []):
            try:
                q.put_nowait(payload)
            except Exception:
                continue
        return
    r, _q = _get_redis_and_queue()
    try:
        r.publish(channel, payload)
    except Exception:
        # Best effort publish; do not crash job
        pass


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
        try:
            _pub(self._channel, {self._key: s})
        except Exception:
            pass
        return n


def run_cli_job(stage: str, command: str, args: Dict[str, Any], job_id: Optional[str] = None) -> Dict[str, Any]:
    """RQ worker entry: runs CLI and publishes a completion message.

    For future incremental streaming, replace capture buffers with a stream that
    calls _pub() on each write. For now, publish a final payload.
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
            from datavizhub.cli import main as cli_main

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

    payload: Dict[str, Any] = {
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
        results_root = Path(os.environ.get("DATAVIZHUB_RESULTS_DIR", "/tmp/datavizhub_results"))
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
            try:
                write_manifest(job_id)
            except Exception:
                pass
    except Exception:
        pass
    if channel:
        _pub(channel, payload)
    return payload


# In-memory fallback (used when USE_REDIS is false)
_JOBS: Dict[str, Dict[str, Any]] = {}


def submit_job(stage: str, command: str, args: Dict[str, Any]) -> str:
    if is_redis_enabled():
        r, q = _get_redis_and_queue()
        # Create a placeholder job id by enqueuing with meta; we need job id to publish channel messages
        job = q.enqueue(run_cli_job, stage, command, args)  # type: ignore[arg-type]
        return job.get_id()
    else:
        import uuid
        from datavizhub.api.workers.executor import start_job as _start

        job_id = uuid.uuid4().hex
        _JOBS[job_id] = {
            "status": "queued",
            "stdout": "",
            "stderr": "",
            "exit_code": None,
        }
        # For API symmetry, we only enqueue here; caller should start background task
        return job_id


def start_job(job_id: str, stage: str, command: str, args: Dict[str, Any]) -> None:
    if is_redis_enabled():
        # When using Redis/RQ, jobs are started by workers; nothing to do here
        return
    # In-memory execution: run inline and update this module's job store
    rec = _JOBS.get(job_id)
    if not rec:
        return
    rec["status"] = "running"
    args_resolved, resolved_paths, _unresolved = resolve_upload_placeholders(args)
    # Streaming execution with in-memory pub/sub
    channel = f"jobs.{job_id}.progress"
    _pub(channel, {"progress": 0.0})
    # Capture stdio with publishers (similar to Redis worker path)
    import io, sys
    class _LocalPubTee(io.StringIO):
        def __init__(self, key: str):
            super().__init__()
            self._key = key
        def write(self, s: str) -> int:  # type: ignore[override]
            if not s:
                return 0
            n = super().write(s)
            try:
                _pub(channel, {self._key: s})
            except Exception:
                pass
            return n
    out_buf = _LocalPubTee("stdout")
    err_buf = _LocalPubTee("stderr")
    old_out, old_err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = out_buf, err_buf
    code = 0
    try:
        try:
            from datavizhub.cli import main as cli_main
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
        results_root = Path(os.environ.get("DATAVIZHUB_RESULTS_DIR", "/tmp/datavizhub_results"))
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
        try:
            write_manifest(job_id)
        except Exception:
            pass
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


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
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
            "stdout": (result or {}).get("stdout") if isinstance(result, dict) else None,
            "stderr": (result or {}).get("stderr") if isinstance(result, dict) else None,
            "exit_code": (result or {}).get("exit_code") if isinstance(result, dict) else None,
            "output_file": (result or {}).get("output_file") if isinstance(result, dict) else None,
        }
    else:
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
        if rec.get("status") in {"queued"}:
            rec["status"] = "canceled"
            return True
        return False
