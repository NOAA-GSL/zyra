# SPDX-License-Identifier: Apache-2.0
"""S3 connector backend.

Functional helpers for working with Amazon S3 using the existing S3Manager
implementation under the hood. Exposes byte fetching, uploading, listing, and
introspection utilities, plus GRIB-centric helpers for ``.idx`` and ranged
downloads.
"""

from __future__ import annotations

import re
from typing import Iterable

# Optional dependency: boto3/botocore. Avoid import-time failure so the CLI can
# still load when S3 features aren't used.
try:  # pragma: no cover - optional dep import guard
    import boto3  # type: ignore[import-not-found]
except ModuleNotFoundError:  # pragma: no cover - optional dep
    boto3 = None  # type: ignore[assignment]

try:  # pragma: no cover - optional dep import guard
    from botocore.exceptions import BotoCoreError, ClientError  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - optional dep

    class BotoCoreError(Exception):  # type: ignore[no-redef]
        pass

    class ClientError(Exception):  # type: ignore[no-redef]
        pass


from zyra.utils.date_manager import DateManager
from zyra.utils.grib import (
    ensure_idx_path,
    parallel_download_byteranges,
    parse_idx_lines,
)

# Accept bucket-only (for listing) or bucket+key URLs.
# Examples: s3://my-bucket, s3://my-bucket/, s3://my-bucket/path/to/object
_S3_RE = re.compile(r"^s3://([^/]+)(?:/(.*))?$")


def _require_boto3() -> None:
    """Ensure boto3 is available before using S3 helpers.

    Raises a clear error instructing users to install the connectors extra
    when boto3 (and botocore) are not present.
    """
    if boto3 is None:  # pragma: no cover - simple runtime guard
        raise ModuleNotFoundError(
            "boto3 is required for S3 features. Install with 'pip install "
            "\"zyra[connectors]\"' or add 'boto3' to your environment."
        )


def parse_s3_url(url: str) -> tuple[str, str]:
    """Parse an S3 URL into ``(bucket, key)`` with a required key.

    Backward compatible with earlier versions that always returned a non-empty
    key. Raises ``ValueError`` if the URL does not include a key
    (e.g., ``s3://bucket`` or ``s3://bucket/``).
    """
    m = _S3_RE.match(url)
    if not m:
        raise ValueError("Invalid s3 URL. Expected s3://bucket/key")
    # Be defensive about capture groups: compute from groups() to avoid
    # assumptions if the regex changes.
    g = m.groups()
    # Require a non-empty, non-whitespace key for strict object operations
    if len(g) < 2 or not (g[1] and str(g[1]).strip()):
        raise ValueError("Invalid s3 URL. Expected s3://bucket/key")
    bucket = g[0]
    key = g[1]
    return bucket, key


def parse_s3_url_optional_key(url: str) -> tuple[str, str | None]:
    """Parse an S3 URL into ``(bucket, key_or_none)``.

    - Returns ``(bucket, None)`` when the URL points to the bucket root (e.g.,
      ``s3://bucket`` or ``s3://bucket/``). Useful for list/prefix operations.
    - For object operations, prefer ``parse_s3_url`` which requires a key.
    """
    m = _S3_RE.match(url)
    if not m:
        raise ValueError("Invalid s3 URL. Expected s3://bucket[/key]")
    g = m.groups()
    # Regex ensures at least the bucket group is present when matched
    bucket = g[0]
    key = g[1] if len(g) > 1 else None
    if not bucket:
        raise ValueError("Invalid s3 URL. Expected s3://bucket[/key]")
    return bucket, key


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
    if not key:
        raise ValueError("Missing key in s3 URL (expected s3://bucket/key)")
    _require_boto3()
    if unsigned:
        # Import botocore lazily to avoid import-time failure when optional.
        from botocore import (  # type: ignore
            UNSIGNED,
        )
        from botocore import (
            config as _botocore_config,
        )

        c = boto3.client(  # type: ignore[union-attr]
            "s3", config=_botocore_config.Config(signature_version=UNSIGNED)
        )
    else:
        c = boto3.client("s3")  # type: ignore[union-attr]
    resp = c.get_object(Bucket=bucket, Key=key)  # type: ignore[arg-type]
    return resp["Body"].read()


def upload_bytes(data: bytes, url_or_bucket: str, key: str | None = None) -> bool:
    """Upload bytes to an S3 object using managed transfer.

    - Calls ``upload_file`` for compatibility with existing tests/mocks.
    - Sets ``ContentType=application/json`` for ``.json`` keys via ExtraArgs.
    """
    if key is None:
        bucket, key = parse_s3_url(url_or_bucket)
    else:
        bucket = url_or_bucket
    if not key:
        raise ValueError("Missing key in s3 URL (expected s3://bucket/key)")
    _require_boto3()
    c = boto3.client("s3")  # type: ignore[union-attr]
    # Set Content-Type for JSON keys
    extra_args = None
    if key is not None and str(key).lower().endswith(".json"):
        extra_args = {"ContentType": "application/json"}
    # Upload from a temp file to satisfy upload_file
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".bin", delete=True) as tmp:
        tmp.write(data)
        tmp.flush()
        kwargs = {"ExtraArgs": extra_args} if extra_args else {}
        c.upload_file(tmp.name, bucket, key, **kwargs)  # type: ignore[arg-type]
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
        bucket, prefix = parse_s3_url_optional_key(prefix_or_url)
    else:
        # When bucket not provided via URL, require env/role defaults; prefix may be None
        bucket = prefix_or_url or ""
        prefix = None
    _require_boto3()
    c = boto3.client("s3")  # type: ignore[union-attr]
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
    if not key:
        raise ValueError("Missing key in s3 URL (expected s3://bucket/key)")
    _require_boto3()
    c = boto3.client("s3")  # type: ignore[union-attr]
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
    if not key:
        raise ValueError("Missing key in s3 URL (expected s3://bucket/key)")
    _require_boto3()
    c = boto3.client("s3")  # type: ignore[union-attr]
    c.delete_object(Bucket=bucket, Key=key)  # type: ignore[arg-type]
    return True


def stat(url_or_bucket: str, key: str | None = None):
    """Return a basic metadata mapping for an object (size/etag/last_modified)."""
    if key is None:
        bucket, key = parse_s3_url(url_or_bucket)
    else:
        bucket = url_or_bucket
    if not key:
        raise ValueError("Missing key in s3 URL (expected s3://bucket/key)")
    _require_boto3()
    c = boto3.client("s3")  # type: ignore[union-attr]
    try:
        resp = c.head_object(Bucket=bucket, Key=key)  # type: ignore[arg-type]
        return {
            "size": int(resp.get("ContentLength", 0)),
            "last_modified": resp.get("LastModified"),
            "etag": resp.get("ETag"),
        }
    except (ClientError, BotoCoreError, ValueError, TypeError):
        return None


def get_size(url_or_bucket: str, key: str | None = None) -> int | None:
    """Return the size in bytes for an S3 object, or None if unknown."""
    if key is None:
        bucket, key = parse_s3_url(url_or_bucket)
    else:
        bucket = url_or_bucket
    if not key:
        raise ValueError("Missing key in s3 URL (expected s3://bucket/key)")
    c = boto3.client("s3")
    try:
        resp = c.head_object(Bucket=bucket, Key=key)  # type: ignore[arg-type]
        return int(resp.get("ContentLength", 0))
    except (ClientError, BotoCoreError, ValueError, TypeError):
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
    _require_boto3()
    if unsigned:
        # Import botocore lazily to avoid import-time failure when optional.
        from botocore import (  # type: ignore
            UNSIGNED,
        )
        from botocore import (
            config as _botocore_config,
        )

        c = boto3.client(  # type: ignore[union-attr]
            "s3", config=_botocore_config.Config(signature_version=UNSIGNED)
        )
    else:
        c = boto3.client("s3")  # type: ignore[union-attr]

    def _ranged(k: str, rng: str) -> bytes:
        resp = c.get_object(Bucket=bucket, Key=k, Range=rng)
        return resp["Body"].read()

    return parallel_download_byteranges(
        _ranged, key, byte_ranges, max_workers=max_workers
    )  # type: ignore[arg-type]
