"""FTP connector backend.

Thin functional wrappers around the FTPManager to support simple byte fetches
and uploads, directory listing with regex/date filtering, sync-to-local flows,
and advanced GRIB workflows (``.idx`` handling, ranged downloads).

The URL parser supports anonymous and credentialed forms, e.g.:
``ftp://host/path``, ``ftp://user@host/path``, ``ftp://user:pass@host/path``.
"""

from __future__ import annotations

import contextlib
import re
from datetime import datetime
from ftplib import FTP
from io import BytesIO
from typing import Iterable

from zyra.utils.date_manager import DateManager
from zyra.utils.grib import compute_chunks, ensure_idx_path, parse_idx_lines

_DELEGATE_NONE = object()


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


def parse_ftp_path(url_or_path: str) -> tuple[str, str, str | None, str | None]:
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
    return host, path, user, pwd


def fetch_bytes(url_or_path: str) -> bytes:
    """Fetch a remote file as bytes from an FTP server."""
    host, remote_path, user, pwd = parse_ftp_path(url_or_path)
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


def upload_bytes(data: bytes, url_or_path: str) -> bool:
    """Upload bytes to a remote FTP path."""
    host, remote_path, user, pwd = parse_ftp_path(url_or_path)
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
) -> list[str] | None:
    """List FTP directory contents with optional regex and date filtering."""
    host, remote_dir, user, pwd = parse_ftp_path(url_or_dir)
    ftp = FTP(timeout=30)
    ftp.connect(host)
    ftp.login(user=(user or "anonymous"), passwd=(pwd or "test@test.com"))
    ftp.set_pasv(True)
    ftp.cwd(remote_dir)
    try:
        names = ftp.nlst()
    except Exception:
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


def exists(url_or_path: str) -> bool:
    """Return True if the remote path exists on the FTP server."""
    host, remote_path, user, pwd = parse_ftp_path(url_or_path)
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
    except Exception:
        return False


def delete(url_or_path: str) -> bool:
    """Delete a remote FTP path (file)."""
    host, remote_path, user, pwd = parse_ftp_path(url_or_path)
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
    except Exception:
        return False


def stat(url_or_path: str):
    """Return minimal metadata mapping for a remote path (e.g., size)."""
    host, remote_path, user, pwd = parse_ftp_path(url_or_path)
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
    except Exception:
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
) -> None:
    """Sync files from a remote FTP directory to a local directory.

    Applies regex/date filters prior to download; optionally removes local
    zero-byte files before syncing and deletes local files that are no
    longer present on the server.
    """
    host, remote_dir, user, pwd = parse_ftp_path(url_or_dir)
    if pattern is None and not (since or until):
        # Fast path placeholder reserved for future optimization.
        pass
    # List, filter, then fetch missing/zero-size files
    names = (
        list_files(
            url_or_dir, pattern, since=since, until=until, date_format=date_format
        )
        or []
    )
    if since or until:
        dm = DateManager([date_format] if date_format else None)
        start = datetime.min if not since else datetime.fromisoformat(since)
        end = datetime.max if not until else datetime.fromisoformat(until)
        names = [n for n in names if dm.is_date_in_range(n, start, end)]
    from pathlib import Path

    Path(local_dir).mkdir(parents=True, exist_ok=True)
    if clean_zero_bytes:
        with contextlib.suppress(Exception):
            for fp in Path(local_dir).iterdir():
                if fp.is_file() and fp.stat().st_size == 0:
                    fp.unlink()
    local_set = {p.name for p in Path(local_dir).iterdir() if p.is_file()}
    # Remove locals not on server
    remote_set = set(Path(n).name for n in names)
    for fname in list(local_set - remote_set):
        with contextlib.suppress(Exception):
            (Path(local_dir) / fname).unlink()
    for name in names:
        dest = str(Path(local_dir) / Path(name).name)
        if (not Path(dest).exists()) or Path(dest).stat().st_size == 0:
            ftp = FTP(timeout=30)
            ftp.connect(host)
            ftp.login(user=(user or "anonymous"), passwd=(pwd or "test@test.com"))
            ftp.set_pasv(True)
            directory = remote_dir
            filename = Path(name).name
            if directory:
                ftp.cwd(directory)
            from pathlib import Path as _P

            with _P(dest).open("wb") as lf:
                ftp.retrbinary(f"RETR {filename}", lf.write)
            with contextlib.suppress(Exception):
                ftp.quit()


def get_size(url_or_path: str) -> int | None:
    """Return remote file size in bytes via FTP SIZE."""
    v = _maybe_delegate("get_size", url_or_path)
    if v is not _DELEGATE_NONE:
        return v  # type: ignore[return-value]
    host, remote_path, user, pwd = parse_ftp_path(url_or_path)
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
    except Exception:
        return None


def get_idx_lines(
    url_or_path: str,
    *,
    write_to: str | None = None,
    timeout: int = 30,
    max_retries: int = 3,
) -> list[str] | None:
    """Fetch and parse the GRIB ``.idx`` for a remote path via FTP."""
    v = _maybe_delegate(
        "get_idx_lines",
        url_or_path,
        write_to=write_to,
        timeout=timeout,
        max_retries=max_retries,
    )
    if v is not _DELEGATE_NONE:
        return v  # type: ignore[return-value]
    host, remote_path, user, pwd = parse_ftp_path(url_or_path)
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


def get_chunks(url_or_path: str, chunk_size: int = 500 * 1024 * 1024) -> list[str]:
    """Compute contiguous chunk ranges for an FTP file."""
    v = _maybe_delegate("get_chunks", url_or_path, chunk_size)
    if v is not _DELEGATE_NONE:
        return v  # type: ignore[return-value]
    size = get_size(url_or_path)
    if size is None:
        return []
    return compute_chunks(size, chunk_size)


def download_byteranges(
    url_or_path: str,
    byte_ranges: Iterable[str],
    *,
    max_workers: int = 10,
    timeout: int = 30,
) -> bytes:
    """Download multiple ranges via FTP REST and concatenate in the input order."""
    v = _maybe_delegate(
        "download_byteranges",
        url_or_path,
        byte_ranges,
        max_workers=max_workers,
        timeout=timeout,
    )
    if v is not _DELEGATE_NONE:
        return v  # type: ignore[return-value]
    host, remote_path, user, pwd = parse_ftp_path(url_or_path)

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
