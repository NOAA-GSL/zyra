from __future__ import annotations

import re
import tempfile
from typing import Optional, Tuple

from datavizhub.acquisition.s3_manager import S3Manager


_S3_RE = re.compile(r"^s3://([^/]+)/(.+)$")


def parse_s3_url(url: str) -> Tuple[str, str]:
    m = _S3_RE.match(url)
    if not m:
        raise ValueError("Invalid s3 URL. Expected s3://bucket/key")
    return m.group(1), m.group(2)


def fetch_bytes(url_or_bucket: str, key: Optional[str] = None, *, unsigned: bool = False) -> bytes:
    if key is None:
        bucket, key = parse_s3_url(url_or_bucket)
    else:
        bucket = url_or_bucket
    s3 = S3Manager(None, None, bucket_name=bucket, unsigned=unsigned)
    size = s3.get_size(key)  # type: ignore[arg-type]
    if size is None:
        raise RuntimeError("Failed to determine S3 object size")
    rng = [f"bytes=0-{size}"]
    return s3.download_byteranges(key, rng)  # type: ignore[arg-type]


def upload_bytes(data: bytes, url_or_bucket: str, key: Optional[str] = None) -> bool:
    if key is None:
        bucket, key = parse_s3_url(url_or_bucket)
    else:
        bucket = url_or_bucket
    s3 = S3Manager(None, None, bucket_name=bucket)
    # S3Manager uploads from file paths; use a temp file
    with tempfile.NamedTemporaryFile(suffix=".bin", delete=True) as tmp:
        tmp.write(data)
        tmp.flush()
        return s3.upload_file(tmp.name, key)  # type: ignore[arg-type]

