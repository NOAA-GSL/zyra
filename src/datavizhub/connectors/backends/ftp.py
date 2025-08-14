from __future__ import annotations

import tempfile
from typing import Tuple

from datavizhub.acquisition.ftp_manager import FTPManager


def parse_ftp_path(url_or_path: str) -> Tuple[str, str]:
    """Return (host, remote_path) for 'ftp://host/path' or 'host/path'."""
    s = url_or_path
    if s.startswith("ftp://"):
        s = s[len("ftp://") :]
    if "/" not in s:
        raise ValueError("FTP path must be host/path")
    host, path = s.split("/", 1)
    return host, path


def fetch_bytes(url_or_path: str) -> bytes:
    host, remote_path = parse_ftp_path(url_or_path)
    mgr = FTPManager(host)
    with tempfile.NamedTemporaryFile(suffix='._dl') as tmp:
        mgr.download_file(remote_path, tmp.name)
        tmp.flush()
        return tmp.read()


def upload_bytes(data: bytes, url_or_path: str) -> bool:
    host, remote_path = parse_ftp_path(url_or_path)
    mgr = FTPManager(host)
    with tempfile.NamedTemporaryFile(suffix='._up', delete=True) as tmp:
        tmp.write(data)
        tmp.flush()
        mgr.upload_file(tmp.name, remote_path)
    return True

