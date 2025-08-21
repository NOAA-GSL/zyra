from __future__ import annotations

import argparse
from typing import Any

from zyra.cli_common import add_input_option
from zyra.connectors.backends import ftp as ftp_backend
from zyra.connectors.backends import http as http_backend
from zyra.connectors.backends import s3 as s3_backend
from zyra.connectors.backends import vimeo as vimeo_backend
from zyra.utils.cli_helpers import configure_logging_from_env
from zyra.utils.io_utils import open_input


def _read_all(path_or_dash: str) -> bytes:
    with open_input(path_or_dash) as f:
        return f.read()


def _cmd_local(ns: argparse.Namespace) -> int:
    """Write stdin or input file to a local path (creates parents)."""
    configure_logging_from_env()
    from pathlib import Path

    data = _read_all(ns.input)
    dest = Path(ns.path)
    try:
        if dest.parent and not dest.parent.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("wb") as f:
            f.write(data)
    except OSError as exc:
        raise SystemExit(f"Failed to write local file: {exc}") from exc
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


def register_cli(dec_subparsers: Any) -> None:
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
    p_post.add_argument(
        "--content-type", dest="content_type", help="Content-Type header"
    )
    p_post.set_defaults(func=_cmd_post)

    # vimeo
    def _cmd_vimeo(ns: argparse.Namespace) -> int:
        configure_logging_from_env()
        import sys

        # Upload or replace
        uri: str
        if getattr(ns, "replace_uri", None):
            # Replace existing video file
            path = ns.input
            if path == "-":
                import tempfile

                data = _read_all(ns.input)
                with tempfile.NamedTemporaryFile(suffix=".mp4", delete=True) as tmp:
                    tmp.write(data)
                    tmp.flush()
                    uri = vimeo_backend.update_video(tmp.name, ns.replace_uri)
            else:
                uri = vimeo_backend.update_video(path, ns.replace_uri)
            # Optional description update
            if getattr(ns, "description", None):
                from contextlib import suppress

                with suppress(Exception):
                    vimeo_backend.update_description(uri, ns.description)
        else:
            # Upload new video
            path = ns.input
            if path == "-":
                import tempfile

                data = _read_all(ns.input)
                with tempfile.NamedTemporaryFile(suffix=".mp4", delete=True) as tmp:
                    tmp.write(data)
                    tmp.flush()
                    uri = vimeo_backend.upload_path(
                        tmp.name, name=ns.name, description=ns.description
                    )
            else:
                uri = vimeo_backend.upload_path(
                    path, name=ns.name, description=ns.description
                )
        # Emit the resulting URI to stdout so pipelines can capture it
        sys.stdout.write(str(uri) + "\n")
        return 0

    p_vimeo = dec_subparsers.add_parser(
        "vimeo", help="Upload or replace a video on Vimeo"
    )
    add_input_option(p_vimeo, required=True)
    p_vimeo.add_argument("--name", help="Video title")
    p_vimeo.add_argument("--description", help="Video description")
    p_vimeo.add_argument(
        "--replace-uri",
        dest="replace_uri",
        help="Replace existing video at this Vimeo URI",
    )
    p_vimeo.set_defaults(func=_cmd_vimeo)
