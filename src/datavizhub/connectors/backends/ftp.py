from __future__ import annotations

"""FTP connector backend.

Thin functional wrappers around the FTPManager to support simple byte fetches
and uploads, directory listing with regex/date filtering, sync-to-local flows,
and advanced GRIB workflows (``.idx`` handling, ranged downloads).

The URL parser supports anonymous and credentialed forms, e.g.:
``ftp://host/path``, ``ftp://user@host/path``, ``ftp://user:pass@host/path``.
"""

import tempfile
from typing import Tuple, Optional, List, Iterable
import re
from datetime import datetime
from io import BytesIO
from ftplib import FTP, error_perm, error_temp

from datavizhub.utils.date_manager import DateManager
from datavizhub.utils.grib import ensure_idx_path, parse_idx_lines, compute_chunks


def parse_ftp_path(url_or_path: str) -> Tuple[str, str, Optional[str], Optional[str]]:
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
    try:
        ftp.quit()
    except Exception:
        pass
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
    try:
        ftp.quit()
    except Exception:
        pass
    return True


def list_files(
    url_or_dir: str,
    pattern: Optional[str] = None,
    *,
    since: Optional[str] = None,
    until: Optional[str] = None,
    date_format: Optional[str] = None,
) -> Optional[List[str]]:
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
    pattern: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    date_format: Optional[str] = None,
    clean_zero_bytes: bool = False,
) -> None:
    """Sync files from a remote FTP directory to a local directory.

    Applies regex/date filters prior to download; optionally removes local
    zero-byte files before syncing and deletes local files that are no
    longer present on the server.
    """
    host, remote_dir, user, pwd = parse_ftp_path(url_or_dir)
    if pattern is None and not (since or until):
        # Fast path: use existing sync by period if provided via since/until mapping
        period = ""
        if since and until:
            # If both provided, approximate via DateManager period when possible is complex;
            # fall back to manager's file-by-file logic by listing then fetching.
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
        try:
            for fp in Path(local_dir).iterdir():
                if fp.is_file() and fp.stat().st_size == 0:
                    fp.unlink()
        except Exception:
            pass
    local_set = {p.name for p in Path(local_dir).iterdir() if p.is_file()}
    # Remove locals not on server
    remote_set = set(Path(n).name for n in names)
    for fname in list(local_set - remote_set):
        try:
            (Path(local_dir) / fname).unlink()
        except Exception:
            pass
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
            with open(dest, "wb") as lf:
                ftp.retrbinary(f"RETR {filename}", lf.write)
            try:
                ftp.quit()
            except Exception:
                pass


def get_size(url_or_path: str) -> Optional[int]:
    """Return remote file size in bytes via FTP SIZE."""
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
    write_to: Optional[str] = None,
    timeout: int = 30,
    max_retries: int = 3,
) -> Optional[List[str]]:
    """Fetch and parse the GRIB ``.idx`` for a remote path via FTP."""
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
    try:
        ftp.quit()
    except Exception:
        pass
    lines = parse_idx_lines(buf.getvalue())
    if write_to:
        outp = write_to if write_to.endswith(".idx") else f"{write_to}.idx"
        try:
            with open(outp, "w", encoding="utf8") as f:
                f.write("\n".join(lines))
        except Exception:
            pass
    return lines


def get_chunks(url_or_path: str, chunk_size: int = 500 * 1024 * 1024) -> List[str]:
    """Compute contiguous chunk ranges for an FTP file."""
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
            try:
                ftp.abort()
            except Exception:
                pass
        try:
            ftp.quit()
        except Exception:
            pass
        return out.getvalue()

    from concurrent.futures import ThreadPoolExecutor

    results: List[bytes] = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        results = list(ex.map(_worker, list(byte_ranges)))
    return b"".join(results)
