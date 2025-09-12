# SPDX-License-Identifier: Apache-2.0
"""Workflow runner (DAG + watch + cron export) used by ``zyra run``.

Features
--------
- Parse workflow YAML/JSON with ``on:`` triggers and ``jobs:`` DAG.
- Execute jobs serially or in parallel (``--max-workers``) with step piping.
- Watch mode with dataset-update triggers and simple cron schedule matching.
- Cron export for system crontab integration.

This module is imported lazily by ``zyra run`` when the provided config is
detected to be a workflow file (contains ``jobs`` and/or ``on``).
"""

from __future__ import annotations

import argparse
import io
import json
import shlex
import sys
import time
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from zyra.cli import main as cli_main
from zyra.utils.env import env, env_bool


class _StdInProxy:
    """Minimal binary stdin proxy exposing a .buffer attribute."""

    def __init__(self, buf: io.BytesIO) -> None:
        self.buffer = buf


class _StdOutProxy:
    """Minimal text stdout proxy that captures .buffer writes.

    Provides write/flush methods to satisfy typical text IO usage while
    preserving access to the underlying binary buffer via .buffer.
    """

    def __init__(self, buf: io.BytesIO) -> None:
        self.buffer = buf

    def write(self, s: str) -> int:  # type: ignore[override]
        # Text writes are ignored; binary writes go to .buffer
        return len(s or "")

    def flush(self) -> None:  # pragma: no cover - no-op
        return


def _load_yaml_or_json(path: str) -> dict[str, Any]:
    """Load a YAML or JSON workflow file into a mapping.

    Tries YAML first; falls back to JSON for parse errors. When PyYAML is not
    installed and the file extension suggests YAML, a helpful error is raised.
    """
    try:
        text = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise SystemExit(
            f"Workflow file not found: {path}. Use an absolute path or run from the project root."
        ) from exc
    try:
        import yaml  # type: ignore

        return yaml.safe_load(text)  # type: ignore[no-any-return]
    except ModuleNotFoundError:
        if str(path).lower().endswith((".yml", ".yaml")):
            raise SystemExit(
                "PyYAML is required to load workflow YAML files. Install it or provide a JSON workflow."
            ) from None
        return json.loads(text)
    except Exception:
        return json.loads(text)


@dataclass
class Job:
    """Single workflow job.

    Attributes
    ----------
    name: str
        Job identifier referenced by ``needs``.
    steps: list[object]
        Ordered steps. Each is either a shell-like argv string or a structured
        mapping (stage/command/args) expanded via the pipeline arg builder.
    needs: list[str]
        Optional dependencies that must succeed before the job runs.
    """

    name: str
    # Steps may be shell strings or argv vectors
    steps: list[object]
    needs: list[str] = field(default_factory=list)


def _expand_env_value(val: Any, *, strict: bool) -> Any:
    """Expand ${VAR} placeholders in a string using pipeline runner helper.

    Imported lazily to avoid pulling the full runner unless needed.
    """
    if not isinstance(val, str):
        return val
    from zyra.pipeline_runner import (
        _expand_env as _exp,
    )

    return _exp(val, strict=strict)


def _parse_workflow(doc: dict[str, Any]) -> tuple[list[str], dict[str, Job]]:
    """Extract cron schedules and jobs from a loaded workflow document."""
    schedules: list[str] = []
    on = _get_on_section(doc)
    if isinstance(on, dict):
        sched = on.get("schedule") or []
        if isinstance(sched, list):
            for item in sched:
                if isinstance(item, dict) and "cron" in item:
                    schedules.append(str(item["cron"]))
                elif isinstance(item, str):
                    schedules.append(item)

    jobs_raw = doc.get("jobs") or {}
    jobs: dict[str, Job] = {}
    if isinstance(jobs_raw, dict):
        for name, spec in jobs_raw.items():
            if not isinstance(spec, dict):
                continue
            needs_val = spec.get("needs")
            needs: list[str]
            if needs_val is None:
                needs = []
            elif isinstance(needs_val, list):
                needs = [str(x) for x in needs_val]
            else:
                needs = [str(needs_val)]
            steps_raw = spec.get("steps") or []
            steps: list[str] = []
            from zyra.pipeline_runner import _build_argv_for_stage as _build_stage_argv

            for st in steps_raw:
                if isinstance(st, str):
                    steps.append(st)
                elif isinstance(st, dict):
                    # Allow structured steps
                    # 1) {cmd: "process convert-format - netcdf --stdout"}
                    cmd = st.get("cmd")
                    if cmd:
                        steps.append(str(cmd))
                        continue
                    # 2) {stage: process, command: convert-format, args: {...}}
                    if "stage" in st or "command" in st:
                        try:
                            argv = [*_build_stage_argv(st)]
                            steps.append(argv)
                            continue
                        except Exception:
                            # Ignore malformed structured steps silently
                            pass
            jobs[name] = Job(name=name, steps=steps, needs=needs)
    return schedules, jobs


def _topo_sort(jobs: dict[str, Job]) -> list[Job]:
    """Return jobs in dependency order (Kahn's algorithm).

    Raises SystemExit when a cycle or unknown dependency is found.
    """
    indeg: dict[str, int] = {k: 0 for k in jobs}
    adj: dict[str, set[str]] = {k: set() for k in jobs}
    for name, job in jobs.items():
        for dep in job.needs:
            if dep not in jobs:
                raise SystemExit(f"Unknown job in needs: {dep}")
            indeg[name] += 1
            adj[dep].add(name)
    # Kahn's algorithm
    queue: list[str] = [n for n, d in indeg.items() if d == 0]
    ordered: list[Job] = []
    while queue:
        n = queue.pop(0)
        ordered.append(jobs[n])
        for m in adj[n]:
            indeg[m] -= 1
            if indeg[m] == 0:
                queue.append(m)
    if len(ordered) != len(jobs):
        raise SystemExit("Cycle detected in job dependencies")
    return ordered


def _run_job(job: Job) -> int:
    """Run a job in-process with stdout→stdin piping between steps.

    Returns the job exit code (0 for success).
    """

    # Lightweight logging to stderr so step progress is visible even when
    # stdout is captured for piping between steps.
    verb = (env("VERBOSITY", "info") or "info").lower()

    def _log(msg: str) -> None:
        if verb != "quiet":
            with suppress(Exception):
                print(msg, file=sys.stderr)

    # Strict env expansion mode (mirrors pipeline runner behavior)
    strict_env = env_bool("STRICT_ENV", False)

    current: bytes | None = None
    total = len(job.steps)
    if total:
        _log(f"[job {job.name}] starting ({total} step{'s' if total != 1 else ''})")
    for i, step in enumerate(job.steps):
        if isinstance(step, str):
            # Expand ${VAR} placeholders before splitting
            step = str(_expand_env_value(step, strict=strict_env))
            argv = shlex.split(step)
        else:
            argv = [
                str(_expand_env_value(x, strict=strict_env))
                if isinstance(x, str)
                else str(x)
                for x in (step or [])
            ]
        if verb in {"info", "debug"}:
            _log(f"[job {job.name}] step {i+1}/{total}: {' '.join(argv)}")
        # Seed from env if the first step expects '-' and no stdin was provided
        if i == 0 and current is None and "-" in argv:
            try:
                default_stdin_path = env("DEFAULT_STDIN")
                if default_stdin_path:
                    current = Path(default_stdin_path).read_bytes()
            except Exception:
                pass
        # Run with stdin/stdout capture
        old_stdin, old_stdout = sys.stdin, sys.stdout
        buf_in = io.BytesIO(current or b"")
        buf_out = io.BytesIO()
        sys.stdin = _StdInProxy(buf_in)  # type: ignore[assignment]
        sys.stdout = _StdOutProxy(buf_out)  # type: ignore[assignment]
        try:
            rc = int(cli_main(argv) or 0)
        except SystemExit as exc:  # normalize
            rc = int(getattr(exc, "code", 2) or 2)
        except Exception:
            rc = 2
        finally:
            sys.stdin = old_stdin
            sys.stdout = old_stdout
        if rc != 0:
            _log(f"[job {job.name}] step {i+1} failed with exit code {rc}")
            return rc
        # Some steps may close sys.stdout.buffer; guard against closed BytesIO
        try:
            current = buf_out.getvalue()
        except (ValueError, AttributeError) as _exc:
            # Mirror API executor behavior: log a warning to aid debugging
            import logging as _logging

            _logging.getLogger(__name__).warning(
                "stdout buffer was closed by command; no bytes captured"
            )
            current = b""
        except Exception:
            # Defensive fallback without additional logging noise
            current = b""
    # Success
    if total:
        _log(f"[job {job.name}] completed successfully")
    return 0


def _run_job_subprocess(job: Job) -> int:
    """Run a job in a subprocess to enable safe parallelism across jobs.

    Each step is invoked as ``python -m zyra.cli <argv...>`` with the previous
    step's stdout fed to stdin. Returns the job's exit code.
    """
    import subprocess
    import sys as _sys

    verb = (env("VERBOSITY", "info") or "info").lower()

    def _log(msg: str) -> None:
        if verb != "quiet":
            with suppress(Exception):
                print(msg, file=_sys.stderr)

    strict_env = env_bool("STRICT_ENV", False)

    current: bytes | None = None
    total = len(job.steps)
    if total:
        _log(f"[job {job.name}] starting ({total} step{'s' if total != 1 else ''})")
    for i, step in enumerate(job.steps):
        if isinstance(step, str):
            step = str(_expand_env_value(step, strict=strict_env))
            argv = shlex.split(step)
        else:
            argv = [
                str(_expand_env_value(x, strict=strict_env))
                if isinstance(x, str)
                else str(x)
                for x in (step or [])
            ]
        # Seed stdin for the first step when DEFAULT_STDIN is configured and
        # no stdin was provided. This supports pipelines under parallel execution.
        if i == 0 and current is None:
            try:
                from zyra.utils.env import env as _env

                default_stdin_path = _env("DEFAULT_STDIN")
                if default_stdin_path:
                    from pathlib import Path as _P

                    current = _P(default_stdin_path).read_bytes()
            except Exception:
                pass
        cmd = [_sys.executable, "-m", "zyra.cli", *argv]
        if verb in {"info", "debug"}:
            _log(f"[job {job.name}] step {i+1}/{total}: {' '.join(argv)}")
        try:
            res = subprocess.run(
                cmd,
                input=current,
                capture_output=True,
                check=False,
            )
            if res.returncode != 0:
                err = (res.stderr or b"").decode("utf-8", errors="ignore").strip()
                if err:
                    _log(
                        f"[job {job.name}] step failed with exit code {int(res.returncode)}: {err}"
                    )
                else:
                    _log(
                        f"[job {job.name}] step failed with exit code {int(res.returncode)}"
                    )
                return int(res.returncode)
            current = res.stdout or b""
        except Exception:
            _log(f"[job {job.name}] step failed with unexpected error")
            return 2
    if total:
        _log(f"[job {job.name}] completed successfully")
    return 0


def cmd_run(ns: argparse.Namespace) -> int:
    """Execute a workflow using a serial or parallel DAG executor.

    Parameters
    ----------
    ns : argparse.Namespace
        Expects: ``workflow`` path, ``continue_on_error`` flag, and optional
        ``max_workers`` integer for parallelism.
    """
    import logging as _logging
    import os

    doc = _load_yaml_or_json(ns.workflow)
    # Apply top-level env from workflow: expand placeholders and export to process
    wf_env = doc.get("env") or {}
    if isinstance(wf_env, dict):
        try:
            from zyra.pipeline_runner import _expand_env as _exp

            for k, v in list(wf_env.items()):
                if not isinstance(k, str):
                    continue
                val = v
                if isinstance(v, str):
                    raw = v
                    val = _exp(v, strict=False)
                    # Skip overriding process env when the value still looks like
                    # an unresolved placeholder (e.g., "${VIMEO_API_KEY}")
                    if "${" in raw and val == raw:
                        _logging.getLogger(__name__).debug(
                            "Skipping unresolved env placeholder for %s: %s",
                            k,
                            raw,
                        )
                        continue
                os.environ[str(k)] = str(val)
        except Exception:
            # Non-fatal; continue without injecting env
            pass
    _, jobs = _parse_workflow(doc)
    if not jobs:
        raise SystemExit("workflow.yml missing 'jobs'")
    # Dry run: print argv plan and exit
    if getattr(ns, "dry_run", False):
        plan: list[dict[str, Any]] = []
        for name, job in jobs.items():
            step_argvs: list[list[str]] = []
            for st in job.steps:
                if isinstance(st, str):
                    step_argvs.append(shlex.split(st))
                else:
                    step_argvs.append([str(x) for x in (st or [])])
            plan.append({"job": name, "needs": list(job.needs), "steps": step_argvs})
        print(json.dumps({"workflow": ns.workflow, "plan": plan}))
        return 0
    # Parallelism configuration
    max_workers = int(getattr(ns, "max_workers", 0) or 0)
    if max_workers and max_workers > 1:
        # DAG execution with thread pool; run each job in a subprocess
        import concurrent.futures as _fut

        # Build dependency graph
        indeg: dict[str, int] = {k: 0 for k in jobs}
        children: dict[str, set[str]] = {k: set() for k in jobs}
        for name, job in jobs.items():
            for dep in job.needs:
                if dep not in jobs:
                    raise SystemExit(f"Unknown job in needs: {dep}")
                indeg[name] += 1
                children[dep].add(name)
        # Ready queue
        ready = [n for n, d in indeg.items() if d == 0]
        status: dict[str, str] = {n: "pending" for n in jobs}
        rc_map: dict[str, int] = {}
        running: dict[_fut.Future[int], str] = {}
        any_failure = False
        with _fut.ThreadPoolExecutor(max_workers=max_workers) as ex:
            # Submit up to cap
            def submit_ready():
                nonlocal ready
                while ready and len(running) < max_workers:
                    name = ready.pop(0)
                    # Skip if any dep failed; still mark as done with failure
                    deps = jobs[name].needs
                    if deps and any(rc_map.get(d, 0) != 0 for d in deps):
                        rc_map[name] = 1
                        status[name] = "done"
                        continue
                    status[name] = "running"
                    # Choose execution mode: subprocess (default) or thread (env override)
                    try:
                        from zyra.utils.env import env as _env

                        mode = (
                            _env("WORKFLOW_PARALLEL_MODE", "subprocess") or "subprocess"
                        ).lower()
                    except Exception:
                        mode = "subprocess"
                    if mode == "thread":
                        fut = ex.submit(_run_job, jobs[name])
                    else:
                        fut = ex.submit(_run_job_subprocess, jobs[name])
                    running[fut] = name

            submit_ready()
            while running:
                done, _ = _fut.wait(running.keys(), return_when=_fut.FIRST_COMPLETED)
                for fut in done:
                    name = running.pop(fut)
                    rc = int(fut.result() or 0)
                    rc_map[name] = rc
                    status[name] = "done"
                    if rc != 0:
                        any_failure = True
                    # Unlock children if all deps completed successfully
                    for ch in children[name]:
                        indeg[ch] -= 1
                        # Only enqueue when all deps are done and succeeded
                        if indeg[ch] == 0 and all(
                            rc_map.get(d, 0) == 0 for d in jobs[ch].needs
                        ):
                            ready.append(ch)
                    # Early stop scheduling new work if not continue_on_error
                    if any_failure and not getattr(ns, "continue_on_error", False):
                        # Drain remaining running futures and then break
                        for f in list(running.keys()):
                            f.result()
                        running.clear()
                        break
                submit_ready()
        overall = 0 if all(rc_map.get(k, 0) == 0 for k in jobs) else 1
        return overall
    # Serial execution fallback
    ordered = _topo_sort(jobs)
    name_to_rc: dict[str, int] = {}
    for job in ordered:
        if any(name_to_rc.get(d, 1) != 0 for d in job.needs):
            name_to_rc[job.name] = 1
            continue
        rc = _run_job(job)
        name_to_rc[job.name] = rc
        if rc != 0 and not ns.continue_on_error:
            break
    overall = 0 if all(v == 0 for v in name_to_rc.values()) else 1
    # Print a concise workflow summary to stderr
    try:
        import sys as _sys

        status = "succeeded" if overall == 0 else "failed"
        print(f"[workflow] {status}: {len(name_to_rc)} job(s)", file=_sys.stderr)
    except Exception:
        pass
    return overall


def cmd_export_cron(ns: argparse.Namespace) -> int:
    """Print crontab entries for schedule triggers found in the workflow."""
    doc = _load_yaml_or_json(ns.workflow)
    schedules, _ = _parse_workflow(doc)
    # Print crontab lines targeting this workflow
    if schedules:
        for c in schedules:
            # Use the unified entrypoint (`zyra run <workflow>`) since there is no
            # separate top-level `workflow` CLI group registered.
            print(f"{c} zyra run {ns.workflow}")
        # Recommend adding logging guidance when none is specified
        try:
            import sys as _sys
            from pathlib import Path as _P

            wf_name = _P(ns.workflow).stem
            _sys.stderr.write(
                "# Tip: add logging, for example:\n"
                f"#   {c} zyra run {ns.workflow} --log-dir /var/log/zyra\n"
                f"# or redirect output: >> /var/log/zyra/{wf_name}.log 2>&1\n"
            )
        except Exception:
            pass
    else:
        try:
            import sys as _sys

            print(
                f"# No schedule triggers found in {ns.workflow} (nothing to export)",
                file=_sys.stderr,
            )
        except Exception:
            pass
    return 0


def _eval_dataset_updates(
    doc: dict[str, Any], state: dict[str, Any], *, run_on_first: bool
) -> tuple[bool, dict[str, Any]]:
    on = _get_on_section(doc)
    items = []
    if isinstance(on, dict):
        du = on.get("dataset-update") or []
        if isinstance(du, list):
            items = du
    changed = False
    new_state = dict(state)
    for it in items:
        if not isinstance(it, dict):
            continue
        path = it.get("path")
        url = it.get("url")
        check = str(it.get("check") or "timestamp")
        key = None
        val: Any = None
        try:
            if path:
                p = Path(str(path))
                stat = p.stat()
                key = f"path::{p}::{check}"
                if check == "size":
                    val = stat.st_size
                elif check == "hash":
                    import hashlib

                    h = hashlib.sha256()
                    with p.open("rb") as f:
                        for chunk in iter(lambda: f.read(1 << 20), b""):
                            h.update(chunk)
                    val = h.hexdigest()
                else:
                    val = int(stat.st_mtime)
            elif url:
                key = f"url::{url}::{check}"
                val = new_state.get(key)
        except FileNotFoundError:
            key = f"path::{path}::{check}"
            val = None
        if key is None:
            continue
        prev = new_state.get(key)
        if (prev is None and run_on_first) or (prev != val):
            changed = True
        new_state[key] = val
    return changed, new_state


def cmd_watch(ns: argparse.Namespace) -> int:
    """Evaluate workflow triggers and run when active (single or looped).

    When used with ``--watch-interval``, repeats evaluation until
    ``--watch-count`` iterations are completed. Dataset-update state is
    persisted when ``--state-file`` is provided. Schedule triggers are
    deduplicated to once per minute via an internal state key.
    """
    doc = _load_yaml_or_json(ns.workflow)
    schedules, _ = _parse_workflow(doc)
    state_path = Path(ns.state_file) if ns.state_file else None
    # Load state once
    state: dict[str, Any] = {}
    if state_path and state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:
            state = {}
    interval = float(getattr(ns, "watch_interval", 0.0) or 0.0)
    max_iter = int(getattr(ns, "watch_count", 0) or 0)
    i = 0
    while True:
        should_run_du, new_state = _eval_dataset_updates(
            doc, state, run_on_first=bool(ns.run_on_first)
        )
        # Compute schedule and dedup per minute
        now = datetime.now()
        minute_key = now.strftime("%Y-%m-%d %H:%M")
        should_run_sched = _schedule_matches_now(schedules, now=now)
        # If already ran this minute from a prior loop, suppress
        if should_run_sched and state.get("_last_schedule_minute") == minute_key:
            should_run_sched = False
        state = new_state
        if should_run_sched:
            state["_last_schedule_minute"] = minute_key
        # Persist latest state
        if state_path:
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        if should_run_du or should_run_sched:
            run_ns = argparse.Namespace(
                workflow=ns.workflow,
                continue_on_error=False,
                dry_run=getattr(ns, "dry_run", False),
            )
            rc = cmd_run(run_ns)
            if rc != 0:
                return rc
        else:
            # When --dry-run is set, emit a helpful message if no triggers are active
            if getattr(ns, "dry_run", False):
                try:
                    import sys as _sys

                    _sys.stderr.write(
                        "# No active workflow triggers (dataset-update/schedule) at this time\n"
                    )
                except Exception:
                    pass
        i += 1
        # Single poll: no interval provided
        if interval <= 0:
            break
        if max_iter and i >= max_iter:
            break
        try:
            time.sleep(max(0.0, interval))
        except Exception:
            break
    return 0


def _parse_field(token: str, min_v: int, max_v: int) -> set[int]:
    """Parse a single cron field into a set of integers.

    Supports: '*', 'n', 'a-b', '*/n', 'a-b/n', comma-separated lists.
    """
    values: set[int] = set()
    for part in token.split(","):
        part = part.strip()
        if part == "*":
            values.update(range(min_v, max_v + 1))
            continue
        step = 1
        if "/" in part:
            base, step_s = part.split("/", 1)
            try:
                step = max(1, int(step_s))
            except Exception:
                step = 1
        else:
            base = part
        if base == "*":
            rng = range(min_v, max_v + 1)
        elif "-" in base:
            a, b = base.split("-", 1)
            try:
                start = int(a)
                end = int(b)
            except Exception:
                continue
            start = max(min_v, start)
            end = min(max_v, end)
            rng = range(start, end + 1)
        else:
            try:
                v = int(base)
            except Exception:
                continue
            v = max(min_v, min(max_v, v))
            rng = range(v, v + 1)
        for x in rng:
            if (x - min_v) % step == 0:
                values.add(x)
    return values


def _schedule_matches_now(crons: list[str], *, now: datetime | None = None) -> bool:
    if not crons:
        return False
    dt = now or datetime.now()
    minute = dt.minute
    hour = dt.hour
    dom = dt.day
    mon = dt.month
    dow = (dt.weekday() + 1) % 7  # Convert Monday=0 -> 1..6, Sunday=0
    for c in crons:
        parts = str(c).split()
        if len(parts) != 5:
            continue
        mset = _parse_field(parts[0], 0, 59)
        hset = _parse_field(parts[1], 0, 23)
        dset = _parse_field(parts[2], 1, 31)
        moset = _parse_field(parts[3], 1, 12)
        wset = _parse_field(parts[4], 0, 6)
        # Cron semantics for DOM/DOW are a bit special (OR). We accept AND when both are not '*'.
        dom_match = dom in dset
        dow_match = dow in wset
        if (
            minute in mset
            and hour in hset
            and mon in moset
            and (dom_match or dow_match)
        ):
            return True
    return False


def register_cli(subparsers: Any) -> None:
    p = subparsers.add_parser("workflow", help="Run DAG workflows with scheduling")
    wsub = p.add_subparsers(dest="wf_cmd", required=True)

    rn = wsub.add_parser("run", help="Run workflow.yml (DAG; serial executor)")
    rn.add_argument("workflow", help="Path to workflow.yml/.json")
    rn.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue executing jobs when a job fails",
    )
    rn.set_defaults(func=cmd_run)

    ec = wsub.add_parser(
        "export-cron", help="Print crontab lines for schedule triggers"
    )
    ec.add_argument("workflow", help="Path to workflow.yml/.json")
    ec.set_defaults(func=cmd_export_cron)

    wt = wsub.add_parser("watch", help="Evaluate triggers and run when active")
    wt.add_argument("workflow", help="Path to workflow.yml/.json")
    wt.add_argument("--state-file", help="Path to persist trigger state (JSON)")
    wt.add_argument(
        "--run-on-first",
        action="store_true",
        help="Trigger a run when no prior state exists",
    )
    wt.set_defaults(func=cmd_watch)


def _get_on_section(doc: dict[str, Any]) -> dict[str, Any]:
    """Return the 'on' section, accounting for YAML 1.1 quirk where 'on' parses as True.

    Some YAML loaders (PyYAML 1.1 semantics) treat the bare key 'on' as a boolean True.
    Support both forms: doc['on'] and doc[True].
    """
    on = doc.get("on")
    if isinstance(on, dict):
        return on
    on_true = doc.get(True)
    if isinstance(on_true, dict):
        return on_true
    return {}
