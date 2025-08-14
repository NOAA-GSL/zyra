from __future__ import annotations

import argparse

from datavizhub.cli_common import add_input_option
from datavizhub.utils.cli_helpers import configure_logging_from_env
from datavizhub.utils.io_utils import open_input
from datavizhub.connectors.backends import http as http_backend
from datavizhub.connectors.backends import s3 as s3_backend
from datavizhub.connectors.backends import ftp as ftp_backend


def _read_all(path_or_dash: str) -> bytes:
    with open_input(path_or_dash) as f:
        return f.read()


def _cmd_local(ns: argparse.Namespace) -> int:
    """Write stdin or input file to a local path (creates parents)."""
    configure_logging_from_env()
    import os
    from pathlib import Path

    data = _read_all(ns.input)
    dest = Path(ns.path)
    try:
        if dest.parent and not dest.parent.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("wb") as f:
            f.write(data)
    except Exception as exc:
        raise SystemExit(f"Failed to write local file: {exc}")
    import logging
    logging.info(str(dest))
    return 0


def _cmd_s3(ns: argparse.Namespace) -> int:
    """Upload stdin or input file to S3 (s3:// or bucket/key)."""
    configure_logging_from_env()
    data = _read_all(ns.input)
    ok = s3_backend.upload_bytes(data, ns.url if ns.url else ns.bucket, ns.key)
    if not ok:
        raise SystemExit(2)
    return 0


def _cmd_ftp(ns: argparse.Namespace) -> int:
    """Upload stdin or input file to FTP."""
    configure_logging_from_env()
    data = _read_all(ns.input)
    ftp_backend.upload_bytes(data, ns.path)
    return 0


def _cmd_post(ns: argparse.Namespace) -> int:
    """HTTP POST stdin or input file to a URL with optional content-type."""
    configure_logging_from_env()
    data = _read_all(ns.input)
    http_backend.post_bytes(ns.url, data, content_type=ns.content_type)
    return 0


def register_cli(dec_subparsers: argparse._SubParsersAction) -> None:
    # local
    p_local = dec_subparsers.add_parser("local", help="Write to local file")
    add_input_option(p_local, required=True)
    p_local.add_argument("path", help="Destination file path")
    p_local.set_defaults(func=_cmd_local)

    # s3
    p_s3 = dec_subparsers.add_parser("s3", help="Upload to S3")
    add_input_option(p_s3, required=True)
    grp = p_s3.add_mutually_exclusive_group(required=True)
    grp.add_argument("--url", help="Full URL s3://bucket/key")
    grp.add_argument("--bucket", help="Bucket name")
    p_s3.add_argument("--key", help="Object key (when using --bucket)")
    p_s3.set_defaults(func=_cmd_s3)

    # ftp
    p_ftp = dec_subparsers.add_parser("ftp", help="Upload to FTP")
    add_input_option(p_ftp, required=True)
    p_ftp.add_argument("path", help="ftp://host/path or host/path")
    p_ftp.set_defaults(func=_cmd_ftp)

    # http post
    p_post = dec_subparsers.add_parser("post", help="POST to HTTP endpoint")
    add_input_option(p_post, required=True)
    p_post.add_argument("url")
    p_post.add_argument("--content-type", dest="content_type", help="Content-Type header")
    p_post.set_defaults(func=_cmd_post)
