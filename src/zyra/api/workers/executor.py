from __future__ import annotations

import contextlib
import io
import logging
import os
import re
import shutil
import sys
import time
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from zyra.api.routers import files as files_router
from zyra.cli import main as cli_main


def _normalize_args(stage: str, command: str, args: dict[str, Any]) -> dict[str, Any]:
    """Normalize friendly API arg names to strict CLI arg names.

    Applies a per-(stage,command) mapping plus general synonyms before argv generation.
    Does not mutate the incoming dict.
    """
    # Global synonyms applied broadly
    global_synonyms = {
        "file": "file_or_url",
        "src": "input",
        # destination-like aliases prefer output by default
        "destination": "output",
        "dest": "output",
        "target": "output",
    }

    # Per-command mappings for friendlier API names
    per_cmd: dict[tuple[str, str], dict[str, str]] = {
        ("process", "decode-grib2"): {
            "input": "file_or_url",
            "pattern": "pattern",
        },
        ("process", "extract-variable"): {
            "input": "file_or_url",
            "pattern": "pattern",
            "var": "pattern",
            "regex": "pattern",
        },
        ("process", "convert-format"): {
            "input": "file_or_url",
            "output": "output",
            "output_path": "output",
            "destination": "output",
            "files": "inputs",
        },
        ("acquire", "http"): {
            "input": "url",
            "output": "output",
            "destination": "output",
        },
        ("acquire", "ftp"): {
            "input": "path",
            "output": "output",
            "destination": "output",
        },
        ("acquire", "s3"): {
            "input": "url",
            "s3_url": "url",
            "bucket_name": "bucket",
            "object_key": "key",
            "output": "output",
            "destination": "output",
        },
        ("decimate", "local"): {
            "input": "input",
            "output": "path",
            "output_path": "path",
            "destination": "path",
            "dest": "path",
        },
        ("decimate", "s3"): {
            "input": "input",
            "s3_url": "url",
            "bucket_name": "bucket",
            "object_key": "key",
        },
        ("decimate", "ftp"): {
            "input": "input",
            "output": "path",
            "destination": "path",
        },
        ("decimate", "post"): {
            "input": "input",
        },
        # Visualization commands use named flags already
    }

    out = dict(args)
    # Apply global synonyms first (e.g., src->input, dest->output)
    for src, dst in global_synonyms.items():
        if src in out and dst not in out:
            out[dst] = out[src]
    # Then apply per-command mappings (e.g., input->file_or_url)
    for src, dst in per_cmd.get((stage, command), {}).items():
        if src in out and dst not in out:
            out[dst] = out[src]
            with contextlib.suppress(Exception):
                del out[src]
    return out


def _to_kebab(s: str) -> str:
    return s.replace("_", "-")


def resolve_upload_placeholders(
    a: dict[str, Any],
) -> tuple[dict[str, Any], list[str], list[str]]:
    """Resolve file_id placeholders in args.

    Returns (resolved_args, resolved_paths, unresolved_ids).
    Safeguards ensure resolved paths are within the upload directory to avoid
    symlink/path traversal escaping.
    """
    out = dict(a)
    resolved_paths: list[str] = []
    unresolved: list[str] = []

    def _lookup_uploaded_path(fid: str) -> str | None:
        try:
            base = files_router.UPLOAD_DIR.resolve()
        except Exception:
            base = files_router.UPLOAD_DIR
        try:
            for p in files_router.UPLOAD_DIR.glob(f"{fid}_*"):
                try:
                    rp = p.resolve()
                except Exception:
                    # Could not resolve candidate path; skip
                    logging.debug(
                        "Security: failed to resolve uploaded path candidate: %s",
                        str(p),
                    )
                    continue
                # Ensure the resolved path is within the uploads base
                try:
                    _ = rp.relative_to(base)
                except Exception:
                    # Reject paths escaping the uploads base (symlink/traversal)
                    logging.warning(
                        "Security: rejecting uploaded path outside base: path=%s base=%s",
                        str(rp),
                        str(base),
                    )
                    continue
                if rp.is_file():
                    return str(rp)
        except Exception:
            return None
        return None

    # Explicit args.file_id
    fid = out.pop("file_id", None)
    if isinstance(fid, str):
        p = _lookup_uploaded_path(fid)
        if p:
            resolved_paths.append(p)
            # Default to 'input' when no other input-like keys
            if not any(
                k in out for k in ("input", "file_or_url", "file", "path", "url")
            ):
                out["input"] = p
        else:
            unresolved.append(fid)

    # Replace placeholders in common keys and scan lists
    for key, val in list(out.items()):
        if isinstance(val, str) and val.startswith("file_id:"):
            fid2 = val.split(":", 1)[1]
            p = _lookup_uploaded_path(fid2)
            if p:
                out[key] = p
                resolved_paths.append(p)
            else:
                unresolved.append(fid2)
        elif isinstance(val, list):
            new_list: list[Any] = []
            for item in val:
                if isinstance(item, str) and item.startswith("file_id:"):
                    fid3 = item.split(":", 1)[1]
                    p = _lookup_uploaded_path(fid3)
                    if p:
                        new_list.append(p)
                        resolved_paths.append(p)
                    else:
                        unresolved.append(fid3)
                        new_list.append(item)
                else:
                    new_list.append(item)
            out[key] = new_list

    return out, resolved_paths, unresolved


def _args_dict_to_argv(stage: str, command: str, args: dict[str, Any]) -> list[str]:
    """Transform an args dict into CLI argv list (excluding program name).

    Heuristic mapping:
    - Recognizes common positional parameters for processing commands.
    - For other keys, emits "--long-name value" or flag for booleans.
    - Supports optional "_positional": ["...", "..."] to force positional ordering.
    - Supports user-provided "argv" to bypass mapping entirely.
    """
    # Allow explicit argv passthrough when provided
    if isinstance(args.get("argv"), list) and all(
        isinstance(x, str) for x in args["argv"]
    ):
        return args["argv"]

    # Resolve uploaded file_id references into absolute paths
    args, _resolved_paths, _unresolved = resolve_upload_placeholders(args)

    argv: list[str] = [stage, command]

    # Normalize friendly names to strict CLI names
    norm_args = _normalize_args(stage, command, args)

    # Special-case: top-level 'run' command expects positional config path
    if stage == "run":
        cfg = norm_args.pop("config", None)
        if cfg is not None:
            argv = ["run"]  # ignore provided command; CLI only has 'run'
            argv.append(str(cfg))

    # Known positional layouts per command for better UX
    positional_map: dict[tuple[str, str], list[str]] = {
        ("process", "decode-grib2"): ["file_or_url"],
        ("process", "extract-variable"): ["file_or_url", "pattern"],
        ("process", "convert-format"): ["file_or_url", "format"],
        ("acquire", "http"): ["url"],
        ("acquire", "ftp"): ["path"],
        ("decimate", "local"): [],  # uses --input and positional path
    }

    # Forced positional override if provided
    forced_positional = norm_args.pop("_positional", None)
    if isinstance(forced_positional, list):
        argv.extend([str(x) for x in forced_positional])

    # Apply known positional parameters
    pos_keys = positional_map.get((stage, command), [])
    for key in pos_keys:
        if key in norm_args:
            argv.append(str(norm_args.pop(key)))

    # Special-cases for connectors
    if stage == "decimate" and command == "local":
        # Requires --input and positional destination path
        path = norm_args.pop("path", None)
        if path:
            # ensure --input is added first if provided
            input_val = norm_args.pop("input", None)
            if input_val is not None:
                argv.extend(["--input", str(input_val)])
            argv.append(str(path))

    # Remaining keys become long flags
    for key, value in norm_args.items():
        if value is None:
            continue
        flag = f"--{_to_kebab(key)}"
        if isinstance(value, bool):
            if value:
                argv.append(flag)
            continue
        if isinstance(value, (list, tuple)):
            for item in value:
                argv.extend([flag, str(item)])
            continue
        argv.extend([flag, str(value)])

    return argv


@dataclass
class RunResult:
    stdout: str
    stderr: str
    exit_code: int
    argv: list[str] = field(default_factory=list)
    stdout_bytes: bytes = b""
    stderr_bytes: bytes = b""


class _StdCapture:
    """Binary-safe capture shim for sys.stdout/stderr.

    Intended usage
    - Swap into ``sys.stdout``/``sys.stderr`` while running a function that
      writes text. The ``write()`` method encodes to UTF-8 and appends to an
      internal ``BytesIO`` buffer so both text and the original bytes can be
      retrieved.
    - Access captured bytes via ``getvalue()`` or the ``buffer`` property.

    Notes
    - Only a small subset of the text stream interface is implemented
      (``write()``, ``flush()``, and ``buffer``); this is sufficient for our
      CLI capture use cases in ``run_cli``.
    - This class is not a full ``io.TextIOBase`` replacement and is intended
      for internal use.
    """

    def __init__(self) -> None:
        self._buf = io.BytesIO()

    @property
    def buffer(self) -> io.BytesIO:
        return self._buf

    def write(self, s: str) -> int:  # type: ignore[override]
        if not isinstance(s, str):
            s = str(s)
        b = s.encode("utf-8", errors="ignore")
        self._buf.write(b)
        return len(s)

    def flush(self) -> None:  # pragma: no cover - no-op
        return

    def getvalue(self) -> bytes:
        return self._buf.getvalue()


def _guess_bytes_name_and_mime(data: bytes) -> tuple[str, str]:
    """Best-effort filename and MIME detection from a bytes prefix.

    Returns a tuple (filename, media_type). Falls back to ``output.bin`` and
    ``application/octet-stream`` when unknown.
    """
    # Simple signature-based detection
    try:
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            return ("output.png", "image/png")
        if data.startswith(b"GRIB"):
            return ("output.grib2", "application/octet-stream")
        if data.startswith(b"CDF") or data.startswith(b"\x89HDF\r\n\x1a\n"):
            return ("output.nc", "application/x-netcdf")
        if len(data) > 12 and data[4:8] == b"ftyp":
            return ("output.mp4", "video/mp4")
        if data.startswith(b"PK\x03\x04"):
            return ("output.zip", "application/zip")
        # fallback generic
        return ("output.bin", "application/octet-stream")
    except Exception:
        return ("output.bin", "application/octet-stream")


def run_cli(stage: str, command: str, args: dict[str, Any]) -> RunResult:
    """Run the CLI synchronously in-process and capture output and exit code."""
    argv = _args_dict_to_argv(stage, command, args)
    # Capture stdio (binary-safe)
    stdout_cap = _StdCapture()
    stderr_cap = _StdCapture()
    old_out, old_err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = stdout_cap, stderr_cap
    try:
        code = 0
        try:
            code = cli_main(argv)
            if not isinstance(code, int):
                # Defensive: CLI returns int per contract; coerce otherwise
                code = int(code) if code is not None else 0
        except SystemExit as exc:
            # Many CLI funcs raise SystemExit; extract code
            code = int(getattr(exc, "code", 1) or 0)
        except Exception as exc:  # pragma: no cover
            print(str(exc), file=sys.stderr)
            code = 1
        out_b = stdout_cap.getvalue()
        err_b = stderr_cap.getvalue()
        return RunResult(
            stdout=out_b.decode("utf-8", errors="ignore"),
            stderr=err_b.decode("utf-8", errors="ignore"),
            exit_code=code,
            argv=argv,
            stdout_bytes=out_b,
            stderr_bytes=err_b,
        )
    finally:
        # Restore stdio
        sys.stdout, sys.stderr = old_out, old_err


# In-memory job store (simple, non-persistent)
_JOBS: dict[str, dict[str, Any]] = {}


def _jobs_ttl_seconds() -> int:
    """TTL (seconds) for completed in-memory jobs before cleanup.

    Set via env ZYRA_JOBS_TTL_SECONDS (or legacy DATAVIZHUB_JOBS_TTL_SECONDS, default: 3600). Use 0 or a
    negative value to disable automatic cleanup.
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
    _cleanup_jobs()
    job_id = uuid.uuid4().hex
    _JOBS[job_id] = {
        "status": "queued",
        "stdout": "",
        "stderr": "",
        "exit_code": None,
        "argv": None,
        "output_file": None,
        "created_at": time.time(),
        "updated_at": time.time(),
    }
    return job_id


def start_job(job_id: str, stage: str, command: str, args: dict[str, Any]) -> None:
    rec = _JOBS.get(job_id)
    if not rec:
        return
    rec["status"] = "running"
    rec["updated_at"] = time.time()
    res = run_cli(stage, command, args)
    rec["stdout"] = res.stdout
    rec["stderr"] = res.stderr
    rec["exit_code"] = res.exit_code
    rec["argv"] = res.argv
    # Persist output artifact when possible
    try:
        out_file = _maybe_copy_output(args, res, job_id)
        rec["output_file"] = out_file
    except Exception:
        rec["output_file"] = None
    rec["status"] = "succeeded" if res.exit_code == 0 else "failed"
    rec["updated_at"] = time.time()
    _cleanup_jobs()


def get_job(job_id: str) -> dict[str, Any] | None:
    _cleanup_jobs()
    return _JOBS.get(job_id)


def cancel_job(job_id: str) -> bool:
    """Cooperatively cancel a queued in-memory job.

    - Returns True when a job exists and its status was 'queued' and is now
      marked as 'canceled'.
    - Returns False for missing jobs or when already running/finished.
    """
    rec = _JOBS.get(job_id)
    if not rec:
        return False
    if rec.get("status") == "queued":
        rec["status"] = "canceled"
        return True
    return False


_SAFE_JOB_ID_RE = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


def _ensure_results_dir(job_id: str) -> Path:
    """Return the results dir for a job, creating it lazily.

    Computes the root from ``ZYRA_RESULTS_DIR`` (legacy ``DATAVIZHUB_RESULTS_DIR``) at call time to avoid
    module-level side effects and ensure the directory exists.
    """
    # Validate job_id as a single safe segment
    if not isinstance(job_id, str) or not job_id:
        raise ValueError("invalid job_id")
    if (
        Path(job_id).is_absolute()
        or job_id != Path(job_id).name
        or not _SAFE_JOB_ID_RE.fullmatch(job_id)
    ):
        raise ValueError("invalid job_id")
    from zyra.utils.env import env_path

    # Prefer new Zyra default; fall back to legacy job dir if it already exists
    base = env_path("RESULTS_DIR", "/tmp/zyra_results")
    legacy_base = Path(
        os.environ.get("DATAVIZHUB_RESULTS_DIR", "/tmp/datavizhub_results")
    )
    # Use a sanitized alias for path composition to make taint flow explicit
    safe_job_id = job_id
    # If a legacy results dir for this job already exists and the new one does not, use legacy for continuity
    full = base / safe_job_id
    legacy_full = legacy_base / safe_job_id
    if legacy_full.exists() and not full.exists():
        full = legacy_full
    full.mkdir(parents=True, exist_ok=True)
    return full


def zip_output_dir(job_id: str, output_dir: str) -> str | None:
    """Package an output directory into ``{job_id}.zip`` inside results dir."""
    d = Path(output_dir)
    if not d.exists() or not d.is_dir():
        return None
    # Create zip named {job_id}.zip in results dir
    results_dir = _ensure_results_dir(job_id)
    zip_path = results_dir / f"{job_id}.zip"
    try:
        # Build zip preserving relative paths
        with zipfile.ZipFile(
            str(zip_path), mode="w", compression=zipfile.ZIP_DEFLATED
        ) as zf:
            for root, _dirs, files in os.walk(d):
                for name in files:
                    p = Path(root) / name
                    arcname = str(p.relative_to(d))
                    zf.write(str(p), arcname)
        return str(zip_path)
    except Exception:
        return None


def _maybe_copy_output(args: dict[str, Any], res: RunResult, job_id: str) -> str | None:
    """Try to persist an output artifact for this job.

    Priority:
    - If args includes an output_dir containing files, package into {job_id}.zip
    - If args includes a concrete output file path that exists ("to_video" or "output"), copy it into results dir
    - Else if stdout has bytes, write binary file with guessed name
    Returns the persisted file path (str) or None.
    """
    out_path = None
    # 1) Zip output_dir if present
    out_dir = args.get("output_dir")
    if isinstance(out_dir, str):
        z = zip_output_dir(job_id, out_dir)
        if z:
            return z
    candidates = []
    # Prefer explicit video output
    if isinstance(args.get("to_video"), str):
        candidates.append(args.get("to_video"))
    if isinstance(args.get("output"), str):
        candidates.append(args.get("output"))
    # Decimate local or similar may use 'path' as output
    if isinstance(args.get("path"), str):
        candidates.append(args.get("path"))
    for p in candidates:
        try:
            if p and Path(p).is_file():
                out_path = p
                break
        except Exception:
            continue
    results_dir = _ensure_results_dir(job_id)
    if out_path:
        # Copy preserving extension
        try:
            src = Path(out_path)
            dest = results_dir / src.name
            if src.resolve() != dest.resolve():
                shutil.copy2(src, dest)
            return str(dest)
        except Exception:
            pass
    # Fallback: persist stdout bytes if present
    if res.stdout_bytes:
        try:
            name, _mime = _guess_bytes_name_and_mime(res.stdout_bytes)
            dest = results_dir / name
            dest.write_bytes(res.stdout_bytes)
            return str(dest)
        except Exception:
            return None
    return None


def _guess_mime_for_file(path: Path) -> str:
    """Guess MIME type for a file, using python-magic when available."""
    # Try python-magic if available, fall back to mimetypes
    try:
        import magic  # type: ignore

        m = magic.Magic(mime=True)
        return str(m.from_file(str(path))) or "application/octet-stream"
    except Exception:
        import mimetypes

        mt, _ = mimetypes.guess_type(str(path))
        return mt or "application/octet-stream"


def write_manifest(job_id: str) -> Path | None:
    """Write a manifest.json listing all artifacts in the job results dir.

    Uses contained, normalized joins and descriptor-based stats to avoid
    path-based operations on user-influenced values.
    """
    try:
        import errno as _errno
        import json
        import mimetypes
        import os as _os

        # Derive contained results directory. Validate and use a sanitized
        # single-segment value to avoid taint in path expressions.
        if not isinstance(job_id, str) or not job_id:
            return None
        if (
            Path(job_id).is_absolute()
            or job_id != Path(job_id).name
            or not _SAFE_JOB_ID_RE.fullmatch(job_id)
        ):
            return None
        safe_job_id = job_id
        from zyra.utils.env import env_path

        base = env_path("RESULTS_DIR", "/tmp/zyra_results")
        legacy_base = Path(
            os.environ.get("DATAVIZHUB_RESULTS_DIR", "/tmp/datavizhub_results")
        )
        # Choose base per existing job directory to preserve legacy runs (use sanitized id)
        selected_base = (
            legacy_base
            if (legacy_base / safe_job_id).exists()
            and not (base / safe_job_id).exists()
            else base
        )
        full = selected_base / safe_job_id
        # Normalize and ensure full is contained within base (compute base directly)
        base_resolved = selected_base.resolve()
        full_resolved = full.resolve()
        try:
            full_resolved.relative_to(base_resolved)
        except ValueError:
            # Prevent path traversal or unexpected directory placement
            return None
        full.mkdir(parents=True, exist_ok=True)

        items = []
        try:
            names = sorted(
                name
                for name in (p.name for p in full.iterdir())
                if name != "manifest.json"
            )
        except FileNotFoundError:
            names = []
        for name in names:
            # Skip unsafe names
            if not _SAFE_JOB_ID_RE.fullmatch(name) and not re.fullmatch(
                r"^[A-Za-z0-9._-]{1,255}$", name
            ):
                continue
            p = full / name
            # Normalize and ensure p is contained within full
            try:
                resolved_p = p.resolve()
                try:
                    resolved_p.relative_to(full.resolve())
                except ValueError:
                    continue
                # lgtm [py/path-injection] — resolved_p is contained via resolve()+relative_to, O_NOFOLLOW enforced
                fd = _os.open(
                    str(resolved_p),
                    getattr(_os, "O_RDONLY", 0) | getattr(_os, "O_NOFOLLOW", 0),
                )
                try:
                    st = _os.fstat(fd)
                finally:
                    import contextlib

                    with contextlib.suppress(Exception):
                        _os.close(fd)
            except OSError as e:  # pragma: no cover - platform dependent
                if getattr(e, "errno", None) == getattr(_errno, "ELOOP", 62):
                    continue
                continue
            # Guess media type by filename only to avoid opening the file
            media_type, _ = mimetypes.guess_type(name)
            items.append(
                {
                    "name": name,
                    "path": str(p),
                    "size": st.st_size,
                    "mtime": int(st.st_mtime),
                    "media_type": media_type or "application/octet-stream",
                }
            )
        manifest = {"job_id": safe_job_id, "artifacts": items}
        mf = full / "manifest.json"
        try:
            with mf.open("w", encoding="utf-8") as _fh:
                _fh.write(json.dumps(manifest, indent=2))
        except Exception:
            return None
        return mf
    except Exception:
        return None
