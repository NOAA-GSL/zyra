from __future__ import annotations

import argparse
from typing import Any

from datavizhub.cli_common import add_output_option
from datavizhub.utils.cli_helpers import configure_logging_from_env
from datavizhub.utils.io_utils import open_output
from datavizhub.connectors.backends import http as http_backend
from datavizhub.connectors.backends import s3 as s3_backend
from datavizhub.connectors.backends import ftp as ftp_backend
from datavizhub.connectors.backends import vimeo as vimeo_backend


def _cmd_http(ns: argparse.Namespace) -> int:
    """Acquire data over HTTP(S) and write to stdout or file."""
    configure_logging_from_env()
    data = http_backend.fetch_bytes(ns.url)
    with open_output(ns.output) as f:
        f.write(data)
    return 0


def _cmd_s3(ns: argparse.Namespace) -> int:
    """Acquire data from S3 (s3:// or bucket/key) and write to stdout or file."""
    configure_logging_from_env()
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
    p_http.set_defaults(func=_cmd_http)

    # s3
    p_s3 = acq_subparsers.add_parser("s3", help="Fetch from S3")
    # Either a single s3:// URL or bucket+key
    grp = p_s3.add_mutually_exclusive_group(required=True)
    grp.add_argument("--url", help="Full URL s3://bucket/key")
    grp.add_argument("--bucket", help="Bucket name")
    p_s3.add_argument("--key", help="Object key (when using --bucket)")
    p_s3.add_argument("--unsigned", action="store_true", help="Use unsigned access for public buckets")
    add_output_option(p_s3)
    p_s3.set_defaults(func=_cmd_s3)

    # ftp
    p_ftp = acq_subparsers.add_parser("ftp", help="Fetch from FTP")
    p_ftp.add_argument("path", help="ftp://host/path or host/path")
    add_output_option(p_ftp)
    p_ftp.set_defaults(func=_cmd_ftp)

    # vimeo (placeholder)
    p_vimeo = acq_subparsers.add_parser("vimeo", help="Fetch video by id (not implemented)")
    p_vimeo.add_argument("video_id")
    add_output_option(p_vimeo)
    p_vimeo.set_defaults(func=_cmd_vimeo)
