from __future__ import annotations

import argparse
from typing import Any

from zyra.cli_common import add_output_option
from zyra.connectors.backends import ftp as ftp_backend
from zyra.connectors.backends import http as http_backend
from zyra.connectors.backends import s3 as s3_backend
from zyra.utils.cli_helpers import configure_logging_from_env
from zyra.utils.date_manager import DateManager
from zyra.utils.io_utils import open_output


def _cmd_http(ns: argparse.Namespace) -> int:
    """Acquire data over HTTP(S) and write to stdout or file."""
    configure_logging_from_env()
    inputs = list(getattr(ns, "inputs", []) or [])
    if getattr(ns, "manifest", None):
        try:
            from pathlib import Path

            with Path(ns.manifest).open(encoding="utf-8") as f:
                for line in f:
                    s = line.strip()
                    if s and not s.startswith("#"):
                        inputs.append(s)
        except Exception as e:
            raise SystemExit(f"Failed to read manifest: {e}") from e
    # Listing mode
    if getattr(ns, "list", False):
        urls = http_backend.list_files(ns.url, pattern=getattr(ns, "pattern", None))
        # Optional date filter using DateManager on URL basenames
        since = getattr(ns, "since", None)
        until = getattr(ns, "until", None)
        # Support ISO period
        if not since and getattr(ns, "since_period", None):
            dm = DateManager()
            start, _ = dm.get_date_range_iso(ns.since_period)
            since = start.isoformat()
        if since or until:
            dm = DateManager(
                [getattr(ns, "date_format", None)]
                if getattr(ns, "date_format", None)
                else None
            )
            from datetime import datetime

            start = datetime.min if not since else datetime.fromisoformat(since)
            end = datetime.max if not until else datetime.fromisoformat(until)
            urls = [u for u in urls if dm.is_date_in_range(u, start, end)]
        for u in urls:
            print(u)
        return 0

    if inputs:
        if ns.output_dir is None:
            raise SystemExit("--output-dir is required with --inputs")
        from pathlib import Path

        outdir = Path(ns.output_dir)
        outdir.mkdir(parents=True, exist_ok=True)
        for u in inputs:
            data = http_backend.fetch_bytes(u)
            name = Path(u).name or "download.bin"
            with (outdir / name).open("wb") as f:
                f.write(data)
        return 0
    data = http_backend.fetch_bytes(ns.url)
    with open_output(ns.output) as f:
        f.write(data)
    return 0


def _cmd_s3(ns: argparse.Namespace) -> int:
    """Acquire data from S3 (s3:// or bucket/key) and write to stdout or file."""
    configure_logging_from_env()
    # Batch via s3:// URLs
    inputs = list(getattr(ns, "inputs", []) or [])
    if getattr(ns, "manifest", None):
        try:
            from pathlib import Path

            with Path(ns.manifest).open(encoding="utf-8") as f:
                for line in f:
                    s = line.strip()
                    if s and not s.startswith("#"):
                        inputs.append(s)
        except Exception as e:
            raise SystemExit(f"Failed to read manifest: {e}") from e
    # Listing mode
    if getattr(ns, "list", False):
        # Prefer full s3:// URL when provided
        prefix = (
            ns.url
            if getattr(ns, "url", None)
            else (ns.bucket if getattr(ns, "bucket", None) else None)
        )
        keys = s3_backend.list_files(
            prefix,
            pattern=getattr(ns, "pattern", None),
            since=(
                lambda sp, s: (
                    DateManager().get_date_range_iso(sp)[0].isoformat()
                    if sp and not s
                    else s
                )
            )(getattr(ns, "since_period", None), getattr(ns, "since", None)),
            until=getattr(ns, "until", None),
            date_format=getattr(ns, "date_format", None),
        )
        for k in keys or []:
            print(k)
        return 0

    if inputs:
        if ns.output_dir is None:
            raise SystemExit("--output-dir is required with --inputs")
        from pathlib import Path

        outdir = Path(ns.output_dir)
        outdir.mkdir(parents=True, exist_ok=True)
        for u in inputs:
            data = s3_backend.fetch_bytes(u, unsigned=ns.unsigned)
            name = Path(u).name or "object.bin"
            with (outdir / name).open("wb") as f:
                f.write(data)
        return 0
    # Accept either s3://bucket/key or split bucket/key
    if ns.url.startswith("s3://"):
        data = s3_backend.fetch_bytes(ns.url, unsigned=ns.unsigned)
    else:
        data = s3_backend.fetch_bytes(ns.bucket, ns.key, unsigned=ns.unsigned)
    with open_output(ns.output) as f:
        f.write(data)
    return 0


def _cmd_ftp(ns: argparse.Namespace) -> int:
    """Acquire data from FTP and write to stdout or file."""
    configure_logging_from_env()
    inputs = list(getattr(ns, "inputs", []) or [])
    if getattr(ns, "manifest", None):
        try:
            from pathlib import Path

            with Path(ns.manifest).open(encoding="utf-8") as f:
                for line in f:
                    s = line.strip()
                    if s and not s.startswith("#"):
                        inputs.append(s)
        except Exception as e:
            raise SystemExit(f"Failed to read manifest: {e}") from e
    # Listing mode
    if getattr(ns, "list", False):
        names = (
            ftp_backend.list_files(
                ns.path,
                pattern=getattr(ns, "pattern", None),
                since=(
                    lambda sp, s: (
                        DateManager().get_date_range_iso(sp)[0].isoformat()
                        if sp and not s
                        else s
                    )
                )(getattr(ns, "since_period", None), getattr(ns, "since", None)),
                until=getattr(ns, "until", None),
                date_format=getattr(ns, "date_format", None),
            )
            or []
        )
        for n in names:
            print(n)
        return 0

    # Sync mode
    if getattr(ns, "sync_dir", None):
        ftp_backend.sync_directory(
            ns.path,
            ns.sync_dir,
            pattern=getattr(ns, "pattern", None),
            since=(
                lambda sp, s: (
                    DateManager().get_date_range_iso(sp)[0].isoformat()
                    if sp and not s
                    else s
                )
            )(getattr(ns, "since_period", None), getattr(ns, "since", None)),
            until=getattr(ns, "until", None),
            date_format=getattr(ns, "date_format", None),
        )
        return 0

    if inputs:
        if ns.output_dir is None:
            raise SystemExit("--output-dir is required with --inputs")
        from pathlib import Path

        outdir = Path(ns.output_dir)
        outdir.mkdir(parents=True, exist_ok=True)
        for p in inputs:
            data = ftp_backend.fetch_bytes(p)
            name = Path(p).name or "download.bin"
            with (outdir / name).open("wb") as f:
                f.write(data)
        return 0
    data = ftp_backend.fetch_bytes(ns.path)
    with open_output(ns.output) as f:
        f.write(data)
    return 0


def _cmd_vimeo(ns: argparse.Namespace) -> int:  # pragma: no cover - placeholder
    """Placeholder for Vimeo acquisition; not implemented."""
    configure_logging_from_env()
    raise SystemExit("acquire vimeo is not implemented yet")


def register_cli(acq_subparsers: Any) -> None:
    # http
    p_http = acq_subparsers.add_parser("http", help="Fetch via HTTP(S)")
    p_http.add_argument("url")
    add_output_option(p_http)
    p_http.add_argument(
        "--list", action="store_true", help="List links on a directory page"
    )
    p_http.add_argument("--pattern", help="Regex to filter listed links")
    p_http.add_argument("--since", help="ISO date filter for list mode")
    p_http.add_argument(
        "--since-period",
        dest="since_period",
        help="ISO-8601 duration for lookback (e.g., P1Y, P6M, P7D, PT24H)",
    )
    p_http.add_argument("--until", help="ISO date filter for list mode")
    p_http.add_argument(
        "--date-format",
        dest="date_format",
        help="Filename date format for list filtering (e.g., YYYYMMDD)",
    )
    p_http.add_argument("--inputs", nargs="+", help="Multiple HTTP URLs to fetch")
    p_http.add_argument("--manifest", help="Path to a file listing URLs (one per line)")
    p_http.add_argument(
        "--output-dir",
        dest="output_dir",
        help="Directory to write outputs for --inputs",
    )
    p_http.set_defaults(func=_cmd_http)

    # s3
    p_s3 = acq_subparsers.add_parser("s3", help="Fetch from S3")
    # Either a single s3:// URL or bucket+key
    grp = p_s3.add_mutually_exclusive_group(required=True)
    grp.add_argument("--url", help="Full URL s3://bucket/key")
    grp.add_argument("--bucket", help="Bucket name")
    p_s3.add_argument("--key", help="Object key (when using --bucket)")
    p_s3.add_argument(
        "--unsigned", action="store_true", help="Use unsigned access for public buckets"
    )
    p_s3.add_argument("--list", action="store_true", help="List keys under a prefix")
    p_s3.add_argument("--pattern", help="Regex to filter listed keys")
    p_s3.add_argument("--since", help="ISO date filter for list mode")
    p_s3.add_argument(
        "--since-period",
        dest="since_period",
        help="ISO-8601 duration for lookback (e.g., P1Y, P6M, P7D, PT24H)",
    )
    p_s3.add_argument("--until", help="ISO date filter for list mode")
    p_s3.add_argument(
        "--date-format",
        dest="date_format",
        help="Filename date format for list filtering (e.g., YYYYMMDD)",
    )
    p_s3.add_argument("--inputs", nargs="+", help="Multiple s3:// URLs to fetch")
    p_s3.add_argument(
        "--manifest", help="Path to a file listing s3:// URLs (one per line)"
    )
    p_s3.add_argument(
        "--output-dir",
        dest="output_dir",
        help="Directory to write outputs for --inputs",
    )
    add_output_option(p_s3)
    p_s3.set_defaults(func=_cmd_s3)

    # ftp
    p_ftp = acq_subparsers.add_parser("ftp", help="Fetch from FTP")
    p_ftp.add_argument("path", help="ftp://host/path or host/path")
    add_output_option(p_ftp)
    p_ftp.add_argument(
        "--list", action="store_true", help="List files in an FTP directory"
    )
    p_ftp.add_argument(
        "--sync-dir", dest="sync_dir", help="Sync FTP directory to a local directory"
    )
    p_ftp.add_argument("--pattern", help="Regex to filter list/sync")
    p_ftp.add_argument("--since", help="ISO date filter for list/sync")
    p_ftp.add_argument(
        "--since-period",
        dest="since_period",
        help="ISO-8601 duration for lookback (e.g., P1Y, P6M, P7D, PT24H)",
    )
    p_ftp.add_argument("--until", help="ISO date filter for list/sync")
    p_ftp.add_argument(
        "--date-format",
        dest="date_format",
        help="Filename date format for filtering (e.g., YYYYMMDD)",
    )
    p_ftp.add_argument("--inputs", nargs="+", help="Multiple FTP paths to fetch")
    p_ftp.add_argument(
        "--manifest", help="Path to a file listing FTP paths (one per line)"
    )
    p_ftp.add_argument(
        "--output-dir",
        dest="output_dir",
        help="Directory to write outputs for --inputs",
    )
    p_ftp.set_defaults(func=_cmd_ftp)

    # vimeo (placeholder)
    p_vimeo = acq_subparsers.add_parser(
        "vimeo", help="Fetch video by id (not implemented)"
    )
    p_vimeo.add_argument("video_id")
    add_output_option(p_vimeo)
    p_vimeo.set_defaults(func=_cmd_vimeo)
