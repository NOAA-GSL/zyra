"""S3 connector backend.

Functional helpers for working with Amazon S3 using the existing S3Manager
implementation under the hood. Exposes byte fetching, uploading, listing, and
introspection utilities, plus GRIB-centric helpers for ``.idx`` and ranged
downloads.
"""

from __future__ import annotations

import re
import tempfile
from typing import Iterable

import boto3
from botocore import config as _botocore_config
from botocore.exceptions import ClientError

from zyra.utils.date_manager import DateManager
from zyra.utils.grib import (
    ensure_idx_path,
    parallel_download_byteranges,
    parse_idx_lines,
)

_S3_RE = re.compile(r"^s3://([^/]+)/(.+)$")


def parse_s3_url(url: str) -> tuple[str, str]:
    m = _S3_RE.match(url)
    if not m:
        raise ValueError("Invalid s3 URL. Expected s3://bucket/key")
    return m.group(1), m.group(2)


def fetch_bytes(
    url_or_bucket: str, key: str | None = None, *, unsigned: bool = False
) -> bytes:
    """Fetch an object's full bytes using ranged GET semantics.

    Accepts either a single ``s3://bucket/key`` URL or ``bucket``+``key``.
    """
    if key is None:
        bucket, key = parse_s3_url(url_or_bucket)
    else:
        bucket = url_or_bucket
    if unsigned:
        from botocore import UNSIGNED

        c = boto3.client(
            "s3", config=_botocore_config.Config(signature_version=UNSIGNED)
        )
    else:
        c = boto3.client("s3")
    resp = c.get_object(Bucket=bucket, Key=key)  # type: ignore[arg-type]
    return resp["Body"].read()


def upload_bytes(data: bytes, url_or_bucket: str, key: str | None = None) -> bool:
    """Upload bytes to an S3 object by writing to a temporary file first."""
    if key is None:
        bucket, key = parse_s3_url(url_or_bucket)
    else:
        bucket = url_or_bucket
    c = boto3.client("s3")
    # Upload from a temp file
    with tempfile.NamedTemporaryFile(suffix=".bin", delete=True) as tmp:
        tmp.write(data)
        tmp.flush()
        c.upload_file(tmp.name, bucket, key)  # type: ignore[arg-type]
    return True


def list_files(
    prefix_or_url: str | None = None,
    *,
    pattern: str | None = None,
    since: str | None = None,
    until: str | None = None,
    date_format: str | None = None,
) -> list[str]:
    """List S3 keys with optional regex and date filtering.

    Accepts either a full ``s3://bucket/prefix`` or ``bucket`` only (prefix
    may be None) and filters using regex ``pattern`` and/or filename-based
    date filtering via ``since``/``until`` with ``date_format``.
    """
    if prefix_or_url and prefix_or_url.startswith("s3://"):
        bucket, prefix = parse_s3_url(prefix_or_url)
    else:
        # When bucket not provided via URL, require env/role defaults; prefix may be None
        bucket = prefix_or_url or ""
        prefix = None
    c = boto3.client("s3")
    paginator = c.get_paginator("list_objects_v2")
    page_iter = paginator.paginate(Bucket=bucket, Prefix=prefix or "")
    keys: list[str] = []
    for page in page_iter:
        for obj in page.get("Contents", []) or []:
            k = obj.get("Key")
            if k:
                keys.append(k)
    if pattern:
        rx = re.compile(pattern)
        keys = [k for k in keys if rx.search(k)]
    # Optional date filtering using filename inference
    if since or until:
        dm = DateManager([date_format] if date_format else None)
        from datetime import datetime

        start = datetime.min if not since else datetime.fromisoformat(since)
        end = datetime.max if not until else datetime.fromisoformat(until)
        keys = [k for k in keys if dm.is_date_in_range(k, start, end)]
    return keys


def exists(url_or_bucket: str, key: str | None = None) -> bool:
    """Return True if an S3 object exists."""
    if key is None:
        bucket, key = parse_s3_url(url_or_bucket)
    else:
        bucket = url_or_bucket
    c = boto3.client("s3")
    try:
        c.head_object(Bucket=bucket, Key=key)  # type: ignore[arg-type]
        return True
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code")
        if code in ("404", "NoSuchKey", "NotFound"):
            return False
        return False


def delete(url_or_bucket: str, key: str | None = None) -> bool:
    """Delete an object by URL or bucket+key."""
    if key is None:
        bucket, key = parse_s3_url(url_or_bucket)
    else:
        bucket = url_or_bucket
    c = boto3.client("s3")
    c.delete_object(Bucket=bucket, Key=key)  # type: ignore[arg-type]
    return True


def stat(url_or_bucket: str, key: str | None = None):
    """Return a basic metadata mapping for an object (size/etag/last_modified)."""
    if key is None:
        bucket, key = parse_s3_url(url_or_bucket)
    else:
        bucket = url_or_bucket
    c = boto3.client("s3")
    try:
        resp = c.head_object(Bucket=bucket, Key=key)  # type: ignore[arg-type]
        return {
            "size": int(resp.get("ContentLength", 0)),
            "last_modified": resp.get("LastModified"),
            "etag": resp.get("ETag"),
        }
    except Exception:
        return None


def get_size(url_or_bucket: str, key: str | None = None) -> int | None:
    """Return the size in bytes for an S3 object, or None if unknown."""
    if key is None:
        bucket, key = parse_s3_url(url_or_bucket)
    else:
        bucket = url_or_bucket
    c = boto3.client("s3")
    try:
        resp = c.head_object(Bucket=bucket, Key=key)  # type: ignore[arg-type]
        return int(resp.get("ContentLength", 0))
    except Exception:
        return None


def get_idx_lines(
    url_or_bucket: str,
    key: str | None = None,
    *,
    unsigned: bool = False,
    timeout: int = 30,
    max_retries: int = 3,
) -> list[str]:
    """Fetch and parse the GRIB .idx content for an S3 object.

    Accepts either a full s3:// URL or (bucket, key).
    """
    if key is None:
        bucket, key = parse_s3_url(url_or_bucket)
    else:
        bucket = url_or_bucket
    idx_key = ensure_idx_path(key)
    url = f"s3://{bucket}/{idx_key}"
    attempt = 0
    last_exc = None
    while attempt < max_retries:
        try:
            data = fetch_bytes(url, unsigned=unsigned)
            return parse_idx_lines(data)
        except Exception as e:  # pragma: no cover - simple retry wrapper
            last_exc = e
            attempt += 1
    if last_exc:
        raise last_exc
    return []


def download_byteranges(
    url_or_bucket: str,
    key: str | None,
    byte_ranges: Iterable[str],
    *,
    unsigned: bool = False,
    max_workers: int = 10,
    timeout: int = 30,
) -> bytes:
    """Download multiple byte ranges from an S3 object and concatenate in order."""
    if key is None:
        bucket, key = parse_s3_url(url_or_bucket)
    else:
        bucket = url_or_bucket
    if unsigned:
        from botocore import UNSIGNED

        c = boto3.client(
            "s3", config=_botocore_config.Config(signature_version=UNSIGNED)
        )
    else:
        c = boto3.client("s3")

    def _ranged(k: str, rng: str) -> bytes:
        resp = c.get_object(Bucket=bucket, Key=k, Range=rng)
        return resp["Body"].read()

    return parallel_download_byteranges(
        _ranged, key, byte_ranges, max_workers=max_workers
    )  # type: ignore[arg-type]
