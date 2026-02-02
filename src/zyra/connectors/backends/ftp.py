# SPDX-License-Identifier: Apache-2.0
"""FTP connector backend.

Thin functional wrappers around the FTPManager to support simple byte fetches
and uploads, directory listing with regex/date filtering, sync-to-local flows,
and advanced GRIB workflows (``.idx`` handling, ranged downloads).

The URL parser supports anonymous and credentialed forms, e.g.:
``ftp://host/path``, ``ftp://user@host/path``, ``ftp://user:pass@host/path``.
"""

from __future__ import annotations

import contextlib
import json
import logging
import re
import warnings
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from ftplib import FTP, all_errors
from io import BytesIO
from pathlib import Path

from zyra.utils.date_manager import DateManager
from zyra.utils.grib import compute_chunks, ensure_idx_path, parse_idx_lines

_DELEGATE_NONE = object()


@dataclass(frozen=True)
class SyncOptions:
    """Configuration for FTP sync file replacement behavior.

    Controls how ``sync_directory`` decides whether to download a remote file
    when a local copy already exists. Options are evaluated in precedence order:

    1. ``skip_if_local_done`` - Skip if ``.done`` marker file exists
    2. ``overwrite_existing`` - Unconditional replacement
    3. ``prefer_remote`` - Always prioritize remote versions
    4. ``prefer_remote_if_meta_newer`` - Use frames-meta.json timestamps
    5. ``recheck_missing_meta`` - Re-download if metadata entry missing
    6. ``min_remote_size`` - Replace if remote exceeds size threshold
    7. ``recheck_existing`` - Compare sizes when mtime unavailable
    8. Default: Replace if remote mtime (via MDTM) is newer
    """

    overwrite_existing: bool = False
    """Replace local files unconditionally regardless of timestamps."""

    recheck_existing: bool = False
    """Compare file sizes when timestamps are unavailable."""

    min_remote_size: int | str | None = None
    """Replace if remote file exceeds threshold (bytes or percentage like '10%')."""

    prefer_remote: bool = False
    """Always prioritize remote versions over local copies."""

    prefer_remote_if_meta_newer: bool = False
    """Use frames-meta.json timestamps for comparison instead of MDTM."""

    skip_if_local_done: bool = False
    """Skip files that have a companion ``.done`` marker file."""

    recheck_missing_meta: bool = False
    """Re-download files that lack a companion entry in frames-meta.json."""

    frames_meta_path: str | None = None
    """Path to frames-meta.json for metadata-aware sync operations."""


class FTPManager:  # pragma: no cover - test patch hook
    """Placeholder for tests to patch.

    The backend functions will attempt to delegate to this manager if present.
    Tests patch this attribute with a mock class exposing expected methods.
    """

    pass


def _maybe_delegate(method: str, *args, **kwargs):  # pragma: no cover - test hook
    """If a ``FTPManager`` attribute is present on this module (patched in tests),
    instantiate it and call the requested method. Returns ``_NO`` on failure.
    """
    try:
        mgr = FTPManager()  # type: ignore[name-defined, call-arg]
        fn = getattr(mgr, method)
        return fn(*args, **kwargs)
    except Exception:
        return _DELEGATE_NONE


def parse_ftp_path(
    url_or_path: str,
    *,
    username: str | None = None,
    password: str | None = None,
) -> tuple[str, str, str | None, str | None]:
    """Return ``(host, remote_path, username, password)`` parsed from an FTP path."""
    s = url_or_path
    if s.startswith("ftp://"):
        s = s[len("ftp://") :]
    user = None
    pwd = None
    if "@" in s:
        auth, s = s.split("@", 1)
        if ":" in auth:
            user, pwd = auth.split(":", 1)
        else:
            user = auth
    if "/" not in s:
        raise ValueError("FTP path must be host/path")
    host, path = s.split("/", 1)
    if username is not None:
        if user is not None and username != user:
            warnings.warn(
                "Explicit FTP username overrides username embedded in the URL.",
                UserWarning,
                stacklevel=2,
            )
        user = username
    if password is not None:
        if pwd is not None and password != pwd:
            warnings.warn(
                "Explicit FTP password overrides credentials embedded in the URL.",
                UserWarning,
                stacklevel=2,
            )
        pwd = password
    return host, path, user, pwd


def fetch_bytes(
    url_or_path: str, *, username: str | None = None, password: str | None = None
) -> bytes:
    """Fetch a remote file as bytes from an FTP server."""
    host, remote_path, user, pwd = parse_ftp_path(
        url_or_path, username=username, password=password
    )
    ftp = FTP(timeout=30)
    ftp.connect(host)
    ftp.login(user=(user or "anonymous"), passwd=(pwd or "test@test.com"))
    ftp.set_pasv(True)
    directory = ""
    filename = remote_path
    if "/" in remote_path:
        directory, filename = remote_path.rsplit("/", 1)
    if directory:
        ftp.cwd(directory)
    buf = BytesIO()
    ftp.retrbinary(f"RETR {filename}", buf.write)
    with contextlib.suppress(Exception):
        ftp.quit()
    return buf.getvalue()


def upload_bytes(
    data: bytes,
    url_or_path: str,
    *,
    username: str | None = None,
    password: str | None = None,
) -> bool:
    """Upload bytes to a remote FTP path."""
    host, remote_path, user, pwd = parse_ftp_path(
        url_or_path, username=username, password=password
    )
    ftp = FTP(timeout=30)
    ftp.connect(host)
    ftp.login(user=(user or "anonymous"), passwd=(pwd or "test@test.com"))
    ftp.set_pasv(True)
    directory = ""
    filename = remote_path
    if "/" in remote_path:
        directory, filename = remote_path.rsplit("/", 1)
    if directory:
        ftp.cwd(directory)
    with BytesIO(data) as bio:
        ftp.storbinary(f"STOR {filename}", bio)
    with contextlib.suppress(Exception):
        ftp.quit()
    return True


def list_files(
    url_or_dir: str,
    pattern: str | None = None,
    *,
    since: str | None = None,
    until: str | None = None,
    date_format: str | None = None,
    username: str | None = None,
    password: str | None = None,
) -> list[str] | None:
    """List FTP directory contents with optional regex and date filtering."""
    host, remote_dir, user, pwd = parse_ftp_path(
        url_or_dir, username=username, password=password
    )
    ftp = FTP(timeout=30)
    ftp.connect(host)
    ftp.login(user=(user or "anonymous"), passwd=(pwd or "test@test.com"))
    ftp.set_pasv(True)
    ftp.cwd(remote_dir)
    try:
        names = ftp.nlst()
    except all_errors:
        names = []
    if pattern:
        rx = re.compile(pattern)
        names = [n for n in names if rx.search(n)]
    if names is None:
        return None
    if since or until:
        dm = DateManager([date_format] if date_format else None)
        start = datetime.min if not since else datetime.fromisoformat(since)
        end = datetime.max if not until else datetime.fromisoformat(until)
        names = [n for n in names if dm.is_date_in_range(n, start, end)]
    return names


def exists(
    url_or_path: str, *, username: str | None = None, password: str | None = None
) -> bool:
    """Return True if the remote path exists on the FTP server."""
    host, remote_path, user, pwd = parse_ftp_path(
        url_or_path, username=username, password=password
    )
    ftp = FTP(timeout=30)
    ftp.connect(host)
    ftp.login(user=(user or "anonymous"), passwd=(pwd or "test@test.com"))
    ftp.set_pasv(True)
    directory = ""
    filename = remote_path
    if "/" in remote_path:
        directory, filename = remote_path.rsplit("/", 1)
    if directory:
        ftp.cwd(directory)
    try:
        files = ftp.nlst()
        return filename in files
    except all_errors:
        return False


def delete(
    url_or_path: str, *, username: str | None = None, password: str | None = None
) -> bool:
    """Delete a remote FTP path (file)."""
    host, remote_path, user, pwd = parse_ftp_path(
        url_or_path, username=username, password=password
    )
    ftp = FTP(timeout=30)
    ftp.connect(host)
    ftp.login(user=(user or "anonymous"), passwd=(pwd or "test@test.com"))
    ftp.set_pasv(True)
    directory = ""
    filename = remote_path
    if "/" in remote_path:
        directory, filename = remote_path.rsplit("/", 1)
    if directory:
        ftp.cwd(directory)
    try:
        ftp.delete(filename)
        return True
    except all_errors:
        return False
    except Exception:
        # Test doubles in unit tests may raise a plain Exception rather than
        # an ftplib-specific error. Handle these as non-fatal and return False
        # to preserve the semantic of "delete failed / missing file" without
        # coupling tests to ftplib's exception hierarchy.
        return False


def stat(url_or_path: str, *, username: str | None = None, password: str | None = None):
    """Return minimal metadata mapping for a remote path (e.g., size)."""
    host, remote_path, user, pwd = parse_ftp_path(
        url_or_path, username=username, password=password
    )
    ftp = FTP(timeout=30)
    ftp.connect(host)
    ftp.login(user=(user or "anonymous"), passwd=(pwd or "test@test.com"))
    ftp.set_pasv(True)
    directory = ""
    filename = remote_path
    if "/" in remote_path:
        directory, filename = remote_path.rsplit("/", 1)
    if directory:
        ftp.cwd(directory)
    try:
        size = ftp.size(filename)
        return {"size": int(size) if size is not None else None}
    except all_errors:
        return None


def sync_directory(
    url_or_dir: str,
    local_dir: str,
    *,
    pattern: str | None = None,
    since: str | None = None,
    until: str | None = None,
    date_format: str | None = None,
    clean_zero_bytes: bool = False,
    username: str | None = None,
    password: str | None = None,
    sync_options: SyncOptions | None = None,
) -> None:
    """Sync files from a remote FTP directory to a local directory.

    Applies regex/date filters prior to download; optionally removes local
    zero-byte files before syncing and deletes local files that are no
    longer present on the server.

    Args:
        url_or_dir: FTP URL or path to the remote directory.
        local_dir: Local directory path to sync files to.
        pattern: Optional regex pattern to filter filenames.
        since: ISO date string for start of date range filter.
        until: ISO date string for end of date range filter.
        date_format: Custom date format for parsing dates in filenames.
        clean_zero_bytes: Remove zero-byte local files before syncing.
        username: FTP username (overrides URL-embedded credentials).
        password: FTP password (overrides URL-embedded credentials).
        sync_options: Configuration for file replacement behavior. If None,
            a default SyncOptions instance is used, which downloads files
            that are missing, zero-byte, or have a newer remote modification
            time than the local copy.
    """
    host, remote_dir, user, pwd = parse_ftp_path(
        url_or_dir, username=username, password=password
    )
    options = sync_options or SyncOptions()

    if pattern is None and not (since or until):
        # Fast path placeholder reserved for future optimization.
        pass
    # List, filter, then fetch missing/zero-size files
    names = (
        list_files(
            url_or_dir,
            pattern,
            since=since,
            until=until,
            date_format=date_format,
            username=username,
            password=password,
        )
        or []
    )
    if not names and (since or until):
        logging.warning(
            "FTP sync found no files for date range (since=%s until=%s); retrying without date filter",
            since,
            until,
        )
        names = (
            list_files(
                url_or_dir,
                pattern,
                since=None,
                until=None,
                date_format=date_format,
                username=username,
                password=password,
            )
            or []
        )
    if since or until:
        dm = DateManager([date_format] if date_format else None)
        start = datetime.min if not since else datetime.fromisoformat(since)
        end = datetime.max if not until else datetime.fromisoformat(until)
        names = [n for n in names if dm.is_date_in_range(n, start, end)]

    local_dir_path = Path(local_dir)
    local_dir_path.mkdir(parents=True, exist_ok=True)

    if clean_zero_bytes:
        with contextlib.suppress(Exception):
            for fp in local_dir_path.iterdir():
                if fp.is_file() and fp.stat().st_size == 0:
                    fp.unlink()
    local_set = {p.name for p in local_dir_path.iterdir() if p.is_file()}

    # Remove locals not on server
    remote_set = set(Path(n).name for n in names)
    for fname in list(local_set - remote_set):
        with contextlib.suppress(Exception):
            (local_dir_path / fname).unlink()

    # Load frames metadata if needed for metadata-aware sync
    frames_meta = None
    if options.prefer_remote_if_meta_newer or options.recheck_missing_meta:
        frames_meta = _load_frames_meta(options.frames_meta_path)

    # Determine if we need remote metadata for decision-making
    needs_remote_size = options.recheck_existing or options.min_remote_size is not None
    needs_remote_mtime = not (options.overwrite_existing or options.prefer_remote)

    # Use a single FTP connection for all metadata queries and downloads
    # to avoid connection overhead per file
    ftp: FTP | None = None

    def ensure_ftp_connection() -> FTP:
        """Ensure we have an active FTP connection, creating one if needed."""
        nonlocal ftp
        if ftp is None:
            ftp = FTP(timeout=30)
            ftp.connect(host)
            ftp.login(user=(user or "anonymous"), passwd=(pwd or "test@test.com"))
            ftp.set_pasv(True)
            if remote_dir:
                ftp.cwd(remote_dir)
        return ftp

    def get_size_via_conn(filename: str) -> int | None:
        """Get file size using the shared connection."""
        try:
            conn = ensure_ftp_connection()
            return conn.size(filename)
        except all_errors as exc:
            logging.debug("FTP SIZE failed for %s: %s", filename, exc)
            return None

    def get_mtime_via_conn(filename: str) -> datetime | None:
        """Get file mtime using the shared connection via MDTM."""
        try:
            conn = ensure_ftp_connection()
            resp = conn.sendcmd(f"MDTM {filename}")
            if resp.startswith("213 "):
                ts_str = resp[4:].strip()
                return datetime.strptime(ts_str, "%Y%m%d%H%M%S")
        except all_errors as exc:
            logging.debug("FTP MDTM failed for %s: %s", filename, exc)
            return None
        return None

    try:
        for name in names:
            filename = Path(name).name
            local_path = local_dir_path / filename
            dest = str(local_path)

            # Short-circuit: check local-only conditions first to avoid remote queries
            # NOTE: skip_if_local_done has highest precedence, matching should_download().
            # If a .done marker exists, we always skip, even if the base file is missing.
            if options.skip_if_local_done and _has_done_marker(local_path):
                do_download, reason = False, ".done marker present"
            # File missing or zero-byte -> download
            elif not local_path.exists() or local_path.stat().st_size == 0:
                do_download, reason = True, "missing or zero-byte"
            else:
                # Need full decision logic with potentially remote metadata
                remote_size: int | None = None
                remote_mtime: datetime | None = None

                if needs_remote_size:
                    remote_size = get_size_via_conn(filename)
                if needs_remote_mtime:
                    remote_mtime = get_mtime_via_conn(filename)

                do_download, reason = should_download(
                    filename,
                    local_path,
                    remote_size,
                    remote_mtime,
                    options,
                    frames_meta,
                )

            if do_download:
                logging.debug("Downloading %s: %s", filename, reason)
                conn = ensure_ftp_connection()
                with Path(dest).open("wb") as lf:
                    conn.retrbinary(f"RETR {filename}", lf.write)
            else:
                logging.debug("Skipping %s: %s", filename, reason)
    finally:
        if ftp is not None:
            with contextlib.suppress(Exception):
                ftp.quit()


def get_size(
    url_or_path: str, *, username: str | None = None, password: str | None = None
) -> int | None:
    """Return remote file size in bytes via FTP SIZE."""
    v = _maybe_delegate("get_size", url_or_path, username=username, password=password)
    if v is not _DELEGATE_NONE:
        return v  # type: ignore[return-value]
    host, remote_path, user, pwd = parse_ftp_path(
        url_or_path, username=username, password=password
    )
    ftp = FTP(timeout=30)
    ftp.connect(host)
    ftp.login(user=(user or "anonymous"), passwd=(pwd or "test@test.com"))
    ftp.set_pasv(True)
    directory = ""
    filename = remote_path
    if "/" in remote_path:
        directory, filename = remote_path.rsplit("/", 1)
    if directory:
        ftp.cwd(directory)
    try:
        sz = ftp.size(filename)
        return int(sz) if sz is not None else None
    except all_errors:
        return None


def get_remote_mtime(
    url_or_path: str,
    *,
    username: str | None = None,
    password: str | None = None,
) -> datetime | None:
    """Return modification time from FTP MDTM command, or None if unavailable.

    The MDTM command returns timestamps in the format ``YYYYMMDDhhmmss``.
    Not all FTP servers support this command; failures return None gracefully.
    """
    v = _maybe_delegate(
        "get_remote_mtime", url_or_path, username=username, password=password
    )
    if v is not _DELEGATE_NONE:
        return v  # type: ignore[return-value]
    host, remote_path, user, pwd = parse_ftp_path(
        url_or_path, username=username, password=password
    )
    ftp = FTP(timeout=30)
    try:
        ftp.connect(host)
        ftp.login(user=(user or "anonymous"), passwd=(pwd or "test@test.com"))
        ftp.set_pasv(True)
        directory = ""
        filename = remote_path
        if "/" in remote_path:
            directory, filename = remote_path.rsplit("/", 1)
        if directory:
            ftp.cwd(directory)
        # FTP MDTM returns: "213 YYYYMMDDhhmmss"
        resp = ftp.sendcmd(f"MDTM {filename}")
        if resp.startswith("213 "):
            ts_str = resp[4:].strip()
            return datetime.strptime(ts_str, "%Y%m%d%H%M%S")
        return None
    except all_errors:
        return None
    finally:
        with contextlib.suppress(Exception):
            ftp.quit()


def _parse_min_size(spec: int | str | None, local_size: int) -> int | None:
    """Parse min_remote_size spec (bytes or percentage) into absolute bytes.

    Examples:
        - ``1000`` -> 1000 (absolute bytes)
        - ``"1000"`` -> 1000 (string form of bytes)
        - ``"10%"`` -> local_size * 1.10 (local size plus 10%)
    """
    if spec is None:
        return None
    if isinstance(spec, int):
        return spec
    spec_str = str(spec).strip()
    if spec_str.endswith("%"):
        try:
            pct = float(spec_str[:-1])
            return int(local_size * (1 + pct / 100))
        except ValueError:
            return None
    try:
        return int(spec_str)
    except ValueError:
        return None


def _load_frames_meta(path: str | None) -> dict | None:
    """Load frames-meta.json if provided and exists."""
    if not path:
        return None
    try:
        p = Path(path)
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        logging.getLogger(__name__).warning(
            "Failed to load frames meta from %s: %s", path, exc
        )
    return None


def _has_done_marker(local_path: Path) -> bool:
    """Check if a .done marker file exists for the given file.

    Marker files are named ``<filename>.done``, e.g., ``frame_001.png.done``.
    """
    done_path = local_path.parent / (local_path.name + ".done")
    return done_path.exists()


def _has_companion_meta(filename: str, frames_meta: dict | None) -> bool:
    """Check if a file has companion metadata in frames-meta.json.

    Returns True if no metadata source is provided (assume OK).
    """
    if not frames_meta:
        return True  # Assume OK if no metadata source
    frames = frames_meta.get("frames", [])
    if isinstance(frames, list):
        return any(f.get("filename") == filename for f in frames)
    return True


def _get_meta_timestamp(filename: str, frames_meta: dict | None) -> datetime | None:
    """Extract timestamp for a file from frames-meta.json."""
    if not frames_meta:
        return None
    frames = frames_meta.get("frames", [])
    if not isinstance(frames, list):
        return None
    for frame in frames:
        if frame.get("filename") == filename:
            ts = frame.get("timestamp")
            if ts:
                try:
                    return datetime.fromisoformat(ts)
                except ValueError:
                    pass
            break
    return None


def should_download(
    remote_name: str,
    local_path: Path,
    remote_size: int | None,
    remote_mtime: datetime | None,
    options: SyncOptions,
    frames_meta: dict | None = None,
) -> tuple[bool, str]:
    """Determine if a remote file should be downloaded based on sync options.

    Args:
        remote_name: The filename on the remote server.
        local_path: Path to the local file (may not exist).
        remote_size: Remote file size in bytes, or None if unknown.
        remote_mtime: Remote modification time from MDTM, or None if unavailable.
        options: SyncOptions configuration.
        frames_meta: Parsed frames-meta.json content, or None.

    Returns:
        A tuple of ``(should_download, reason)`` where reason is a short
        description suitable for logging.
    """
    # 1. Skip if .done marker exists
    if options.skip_if_local_done and _has_done_marker(local_path):
        return (False, "skip: .done marker exists")

    # 2. File doesn't exist locally - always download
    if not local_path.exists():
        return (True, "new file")

    local_size = local_path.stat().st_size

    # 3. Zero-byte local file - always replace
    if local_size == 0:
        return (True, "local file is zero bytes")

    # 4. Overwrite existing unconditionally
    if options.overwrite_existing:
        return (True, "overwrite-existing mode")

    # 5. Prefer remote unconditionally
    if options.prefer_remote:
        return (True, "prefer-remote mode")

    # 6. Prefer remote if meta is newer
    if options.prefer_remote_if_meta_newer and frames_meta:
        meta_ts = _get_meta_timestamp(remote_name, frames_meta)
        if meta_ts:
            try:
                local_mtime = datetime.fromtimestamp(local_path.stat().st_mtime)
                if meta_ts > local_mtime:
                    return (True, "meta timestamp newer than local")
            except OSError as exc:
                logging.debug(
                    "Failed to read mtime for %s when comparing to meta timestamp: %s",
                    local_path,
                    exc,
                )

    # 7. Recheck missing meta
    if options.recheck_missing_meta and not _has_companion_meta(
        remote_name, frames_meta
    ):
        return (True, "missing companion metadata")

    # 8. Min remote size check
    if options.min_remote_size is not None and remote_size is not None:
        threshold = _parse_min_size(options.min_remote_size, local_size)
        if threshold is not None and remote_size >= threshold:
            return (True, f"remote size {remote_size} >= threshold {threshold}")

    # 9. Recheck existing (size comparison when mtime unavailable)
    if (
        options.recheck_existing
        and remote_size is not None
        and remote_size != local_size
    ):
        return (True, f"size mismatch: local={local_size}, remote={remote_size}")

    # 10. Default: MDTM-based comparison
    if remote_mtime is not None:
        try:
            local_mtime = datetime.fromtimestamp(local_path.stat().st_mtime)
            if remote_mtime > local_mtime:
                return (True, "remote mtime newer")
        except OSError as exc:
            logging.debug(
                "Failed to read local mtime for %s during MDTM comparison: %s",
                local_path,
                exc,
            )

    return (False, "up-to-date")


def get_idx_lines(
    url_or_path: str,
    *,
    write_to: str | None = None,
    timeout: int = 30,
    max_retries: int = 3,
    username: str | None = None,
    password: str | None = None,
) -> list[str] | None:
    """Fetch and parse the GRIB ``.idx`` for a remote path via FTP."""
    v = _maybe_delegate(
        "get_idx_lines",
        url_or_path,
        write_to=write_to,
        timeout=timeout,
        max_retries=max_retries,
        username=username,
        password=password,
    )
    if v is not _DELEGATE_NONE:
        return v  # type: ignore[return-value]
    host, remote_path, user, pwd = parse_ftp_path(
        url_or_path, username=username, password=password
    )
    ftp = FTP(timeout=30)
    ftp.connect(host)
    ftp.login(user=(user or "anonymous"), passwd=(pwd or "test@test.com"))
    ftp.set_pasv(True)
    idx_path = ensure_idx_path(remote_path)
    directory = ""
    filename = idx_path
    if "/" in idx_path:
        directory, filename = idx_path.rsplit("/", 1)
    if directory:
        ftp.cwd(directory)
    buf = BytesIO()
    ftp.retrbinary(f"RETR {filename}", buf.write)
    with contextlib.suppress(Exception):
        ftp.quit()
    lines = parse_idx_lines(buf.getvalue())
    if write_to:
        outp = write_to if write_to.endswith(".idx") else f"{write_to}.idx"
        try:
            from pathlib import Path as _P

            with _P(outp).open("w", encoding="utf8") as f:
                f.write("\n".join(lines))
        except Exception:
            pass
    return lines


def get_chunks(
    url_or_path: str,
    chunk_size: int = 500 * 1024 * 1024,
    *,
    username: str | None = None,
    password: str | None = None,
) -> list[str]:
    """Compute contiguous chunk ranges for an FTP file."""
    v = _maybe_delegate(
        "get_chunks",
        url_or_path,
        chunk_size,
        username=username,
        password=password,
    )
    if v is not _DELEGATE_NONE:
        return v  # type: ignore[return-value]
    size = get_size(url_or_path, username=username, password=password)
    if size is None:
        return []
    return compute_chunks(size, chunk_size)


def download_byteranges(
    url_or_path: str,
    byte_ranges: Iterable[str],
    *,
    max_workers: int = 10,
    timeout: int = 30,
    username: str | None = None,
    password: str | None = None,
) -> bytes:
    """Download multiple ranges via FTP REST and concatenate in the input order."""
    v = _maybe_delegate(
        "download_byteranges",
        url_or_path,
        byte_ranges,
        max_workers=max_workers,
        timeout=timeout,
        username=username,
        password=password,
    )
    if v is not _DELEGATE_NONE:
        return v  # type: ignore[return-value]
    host, remote_path, user, pwd = parse_ftp_path(
        url_or_path, username=username, password=password
    )

    def _worker(_range: str) -> bytes:
        start_end = _range.replace("bytes=", "").split("-")
        start = int(start_end[0]) if start_end[0] else 0
        if start_end[1]:
            end = int(start_end[1])
        else:
            sz = get_size(url_or_path) or 0
            end = max(sz - 1, start)
        ftp = FTP(timeout=timeout)
        ftp.connect(host)
        ftp.login(user=(user or "anonymous"), passwd=(pwd or "test@test.com"))
        ftp.set_pasv(True)
        directory = ""
        filename = remote_path
        if "/" in remote_path:
            directory, filename = remote_path.rsplit("/", 1)
        if directory:
            ftp.cwd(directory)
        remaining = end - start + 1
        out = BytesIO()

        class _Stop(Exception):
            pass

        def _cb(chunk: bytes):
            nonlocal remaining
            if remaining <= 0:
                raise _Stop()
            take = min(len(chunk), remaining)
            if take:
                out.write(chunk[:take])
                remaining -= take
            if remaining <= 0:
                raise _Stop()

        try:
            ftp.retrbinary(f"RETR {filename}", _cb, rest=start)
        except _Stop:
            with contextlib.suppress(Exception):
                ftp.abort()
        with contextlib.suppress(Exception):
            ftp.quit()
        return out.getvalue()

    from concurrent.futures import ThreadPoolExecutor

    results: list[bytes] = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        results = list(ex.map(_worker, list(byte_ranges)))
    return b"".join(results)
