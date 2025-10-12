# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import argparse
import os
from typing import Any

from zyra.cli_common import add_input_option
from zyra.connectors.backends import ftp as ftp_backend
from zyra.connectors.backends import http as http_backend
from zyra.connectors.backends import s3 as s3_backend
from zyra.connectors.backends import vimeo as vimeo_backend
from zyra.connectors.credentials import (
    CredentialResolutionError,
    apply_auth_header,
    apply_http_credentials,
    parse_header_strings,
    resolve_basic_auth_credentials,
    resolve_credentials,
)
from zyra.utils.cli_helpers import configure_logging_from_env
from zyra.utils.io_utils import open_input


def _read_all(path_or_dash: str) -> bytes:
    with open_input(path_or_dash) as f:
        return f.read()


def _cmd_local(ns: argparse.Namespace) -> int:
    """Write stdin or input file to a local path (creates parents)."""
    if getattr(ns, "verbose", False):
        os.environ["ZYRA_VERBOSITY"] = "debug"
    elif getattr(ns, "quiet", False):
        os.environ["ZYRA_VERBOSITY"] = "quiet"
    if getattr(ns, "trace", False):
        os.environ["ZYRA_SHELL_TRACE"] = "1"
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

    if os.environ.get("ZYRA_SHELL_TRACE"):
        logging.info("+ write '%s'", str(dest))
    logging.info(str(dest))
    return 0


def _cmd_s3(ns: argparse.Namespace) -> int:
    """Upload stdin or input file to S3 (s3:// or bucket/key)."""
    if getattr(ns, "verbose", False):
        os.environ["ZYRA_VERBOSITY"] = "debug"
    elif getattr(ns, "quiet", False):
        os.environ["ZYRA_VERBOSITY"] = "quiet"
    if getattr(ns, "trace", False):
        os.environ["ZYRA_SHELL_TRACE"] = "1"
    configure_logging_from_env()
    # Validate mutually exclusive input sources
    read_stdin = bool(getattr(ns, "read_stdin", False))
    current_input = getattr(ns, "input", None)
    if read_stdin and current_input not in (None, "-"):
        raise SystemExit(
            "Options --input and --read-stdin are mutually exclusive; provide exactly one."
        )
    # Convenience alias: --read-stdin behaves like -i -
    if read_stdin:
        ns.input = "-"
    if not getattr(ns, "input", None):
        raise SystemExit("Missing input: specify --input PATH or use --read-stdin")
    data = _read_all(ns.input)
    if os.environ.get("ZYRA_SHELL_TRACE"):
        import logging as _log

        from zyra.utils.cli_helpers import sanitize_for_log

        target = (
            ns.url if getattr(ns, "url", None) else f"s3://{ns.bucket}/{ns.key or ''}"
        )
        _log.info("+ s3 put '%s'", sanitize_for_log(target))
    ok = s3_backend.upload_bytes(data, ns.url if ns.url else ns.bucket, ns.key)
    if not ok:
        raise SystemExit(2)
    return 0


def _cmd_ftp(ns: argparse.Namespace) -> int:
    """Upload stdin or input file to FTP."""
    if getattr(ns, "verbose", False):
        os.environ["ZYRA_VERBOSITY"] = "debug"
    elif getattr(ns, "quiet", False):
        os.environ["ZYRA_VERBOSITY"] = "quiet"
    if getattr(ns, "trace", False):
        os.environ["ZYRA_SHELL_TRACE"] = "1"
    configure_logging_from_env()
    credential_entries = list(getattr(ns, "credential", []) or [])
    if getattr(ns, "user", None):
        credential_entries.append(f"user={ns.user}")
    if getattr(ns, "password", None):
        credential_entries.append(f"password={ns.password}")
    username: str | None = None
    password: str | None = None
    if credential_entries:
        try:
            resolved = resolve_credentials(
                credential_entries,
                credential_file=getattr(ns, "credential_file", None),
            )
        except CredentialResolutionError as exc:
            raise SystemExit(f"Credential error: {exc}") from exc
        username, password = resolve_basic_auth_credentials(resolved.values)
    data = _read_all(ns.input)
    ftp_backend.upload_bytes(data, ns.path, username=username, password=password)
    return 0


def _cmd_post(ns: argparse.Namespace) -> int:
    """HTTP POST stdin or input file to a URL with optional content-type."""
    if getattr(ns, "verbose", False):
        os.environ["ZYRA_VERBOSITY"] = "debug"
    elif getattr(ns, "quiet", False):
        os.environ["ZYRA_VERBOSITY"] = "quiet"
    if getattr(ns, "trace", False):
        os.environ["ZYRA_SHELL_TRACE"] = "1"
    configure_logging_from_env()
    headers = parse_header_strings(getattr(ns, "header", None))
    credential_entries = list(getattr(ns, "credential", []) or [])
    if credential_entries:
        try:
            resolved = resolve_credentials(
                credential_entries,
                credential_file=getattr(ns, "credential_file", None),
            )
        except CredentialResolutionError as exc:
            raise SystemExit(f"Credential error: {exc}") from exc
        apply_http_credentials(headers, resolved.values)
    apply_auth_header(headers, getattr(ns, "auth", None))
    data = _read_all(ns.input)
    if os.environ.get("ZYRA_SHELL_TRACE"):
        import logging as _log

        from zyra.utils.cli_helpers import sanitize_for_log

        _log.info("+ http post '%s'", sanitize_for_log(ns.url))
    http_backend.post_bytes(
        ns.url,
        data,
        content_type=ns.content_type,
        headers=headers or None,
    )
    return 0


def register_cli(dec_subparsers: Any) -> None:
    # local
    p_local = dec_subparsers.add_parser(
        "local",
        help="Write to local file",
        description=(
            "Write stdin or an input file to a local destination path, creating parent directories as needed."
        ),
    )
    add_input_option(p_local, required=True)
    p_local.add_argument("path", help="Destination file path")
    p_local.add_argument(
        "--verbose", action="store_true", help="Verbose logging for this command"
    )
    p_local.add_argument(
        "--quiet", action="store_true", help="Quiet logging for this command"
    )
    p_local.add_argument(
        "--trace",
        action="store_true",
        help="Shell-style trace of key steps and external commands",
    )
    p_local.set_defaults(func=_cmd_local)

    # s3
    p_s3 = dec_subparsers.add_parser(
        "s3",
        help="Upload to S3",
        description=(
            "Upload stdin or an input file to Amazon S3, specified by s3:// URL or bucket/key."
        ),
    )
    # Input is optional when --read-stdin is provided
    add_input_option(p_s3, required=False)
    p_s3.add_argument(
        "--read-stdin",
        action="store_true",
        help="Read object body from stdin (alias for -i -)",
    )
    grp = p_s3.add_mutually_exclusive_group(required=True)
    grp.add_argument("--url", help="Full URL s3://bucket/key")
    grp.add_argument("--bucket", help="Bucket name")
    p_s3.add_argument("--key", help="Object key (when using --bucket)")
    p_s3.add_argument(
        "--verbose", action="store_true", help="Verbose logging for this command"
    )
    p_s3.add_argument(
        "--quiet", action="store_true", help="Quiet logging for this command"
    )
    p_s3.add_argument(
        "--trace",
        action="store_true",
        help="Shell-style trace of key steps and external commands",
    )
    p_s3.set_defaults(func=_cmd_s3)

    # ftp
    p_ftp = dec_subparsers.add_parser(
        "ftp",
        help="Upload to FTP",
        description=("Upload stdin or an input file to an FTP destination path."),
    )
    add_input_option(p_ftp, required=True)
    p_ftp.add_argument("path", help="ftp://host/path or host/path")
    p_ftp.add_argument(
        "--verbose", action="store_true", help="Verbose logging for this command"
    )
    p_ftp.add_argument(
        "--quiet", action="store_true", help="Quiet logging for this command"
    )
    p_ftp.add_argument(
        "--trace",
        action="store_true",
        help="Shell-style trace of key steps and external commands",
    )
    p_ftp.add_argument("--user", help="FTP username (alias for --credential user=...)")
    p_ftp.add_argument(
        "--password", help="FTP password (alias for --credential password=...)"
    )
    p_ftp.add_argument(
        "--credential",
        action="append",
        dest="credential",
        help="Credential slot resolution (repeatable), e.g., 'user=@FTP_USER'",
    )
    p_ftp.add_argument(
        "--credential-file",
        dest="credential_file",
        help="Optional dotenv file for resolving @KEY credentials",
    )
    p_ftp.set_defaults(func=_cmd_ftp)

    # http post
    p_post = dec_subparsers.add_parser(
        "post",
        help="POST to HTTP endpoint",
        description=(
            "HTTP POST stdin or an input file to a URL with optional content-type."
        ),
    )
    add_input_option(p_post, required=True)
    p_post.add_argument("url")
    p_post.add_argument(
        "--content-type", dest="content_type", help="Content-Type header"
    )
    p_post.add_argument(
        "--header",
        action="append",
        help="Add custom HTTP header 'Name: Value' (repeatable)",
    )
    p_post.add_argument(
        "--auth",
        help=(
            "Convenience auth helper: 'bearer:$TOKEN' -> Authorization: Bearer <value>, 'basic:user:pass' sets HTTP Basic auth"
        ),
    )
    p_post.add_argument(
        "--credential",
        action="append",
        dest="credential",
        help="Credential slot resolution (repeatable), e.g., 'token=$API_TOKEN'",
    )
    p_post.add_argument(
        "--credential-file",
        dest="credential_file",
        help="Optional dotenv file for resolving @KEY credentials",
    )
    p_post.add_argument(
        "--verbose", action="store_true", help="Verbose logging for this command"
    )
    p_post.add_argument(
        "--quiet", action="store_true", help="Quiet logging for this command"
    )
    p_post.add_argument(
        "--trace",
        action="store_true",
        help="Shell-style trace of key steps and external commands",
    )
    p_post.set_defaults(func=_cmd_post)

    # vimeo
    def _cmd_vimeo(ns: argparse.Namespace) -> int:
        configure_logging_from_env()
        import logging
        import sys

        credential_entries = list(getattr(ns, "credential", []) or [])
        if getattr(ns, "vimeo_token", None):
            credential_entries.append(f"access_token={ns.vimeo_token}")
        if getattr(ns, "vimeo_client_id", None):
            credential_entries.append(f"client_id={ns.vimeo_client_id}")
        if getattr(ns, "vimeo_client_secret", None):
            credential_entries.append(f"client_secret={ns.vimeo_client_secret}")
        resolved_token: str | None = None
        resolved_client_id: str | None = None
        resolved_client_secret: str | None = None
        if credential_entries:
            try:
                resolved = resolve_credentials(
                    credential_entries,
                    credential_file=getattr(ns, "credential_file", None),
                )
            except CredentialResolutionError as exc:
                raise SystemExit(f"Credential error: {exc}") from exc
            resolved_token = (
                resolved.get("access_token")
                or resolved.get("token")
                or resolved.get("bearer")
            )
            resolved_client_id = resolved.get("client_id")
            resolved_client_secret = resolved.get("client_secret")

        # Resolve description from --description or --description-file
        desc: str | None = getattr(ns, "description", None)
        if not desc and getattr(ns, "description_file", None):
            try:
                from pathlib import Path as _P

                data = _P(ns.description_file).read_text(encoding="utf-8")
                max_len = 4800
                if len(data) > max_len:
                    data = data[: max_len - 12] + "\n...[truncated]"
                desc = data
            except Exception as exc:
                logging.warning(f"Failed to read --description-file: {exc}")
                desc = None

        try:
            uri: str
            if getattr(ns, "replace_uri", None):
                path = ns.input
                if path == "-":
                    import tempfile

                    data = _read_all(ns.input)
                    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=True) as tmp:
                        tmp.write(data)
                        tmp.flush()
                        uri = vimeo_backend.update_video(
                            tmp.name,
                            ns.replace_uri,
                            token=resolved_token,
                            client_id=resolved_client_id,
                            client_secret=resolved_client_secret,
                        )
                else:
                    uri = vimeo_backend.update_video(
                        path,
                        ns.replace_uri,
                        token=resolved_token,
                        client_id=resolved_client_id,
                        client_secret=resolved_client_secret,
                    )
                if desc:
                    try:
                        vimeo_backend.update_description(
                            uri,
                            desc,
                            token=resolved_token,
                            client_id=resolved_client_id,
                            client_secret=resolved_client_secret,
                        )
                        logging.info(
                            "Updated Vimeo description (chars=%d)", len(desc or "")
                        )
                    except Exception as exc:
                        logging.warning("Vimeo description update failed: %s", str(exc))
            else:
                path = ns.input
                if path == "-":
                    import tempfile

                    data = _read_all(ns.input)
                    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=True) as tmp:
                        tmp.write(data)
                        tmp.flush()
                        uri = vimeo_backend.upload_path(
                            tmp.name,
                            name=ns.name,
                            description=desc,
                            token=resolved_token,
                            client_id=resolved_client_id,
                            client_secret=resolved_client_secret,
                        )
                else:
                    uri = vimeo_backend.upload_path(
                        path,
                        name=ns.name,
                        description=desc,
                        token=resolved_token,
                        client_id=resolved_client_id,
                        client_secret=resolved_client_secret,
                    )
            sys.stdout.write(str(uri) + "\n")
            return 0
        except Exception as exc:
            msg = (
                "Vimeo upload failed. Ensure the 'PyVimeo' extra is installed and credentials are set.\n"
                "Install: poetry install -E connectors (or pip install 'zyra[datatransfer]')\n"
                "Env: export VIMEO_ACCESS_TOKEN=... (and any required client key/secret).\n"
                f"Details: {exc}"
            )
            logging.error(msg)
            return 2

    p_vimeo = dec_subparsers.add_parser(
        "vimeo",
        help="Upload or replace a video on Vimeo",
        description=(
            "Upload a new video to Vimeo or replace an existing video by URI. Optionally set title and description."
        ),
    )
    add_input_option(p_vimeo, required=True)
    p_vimeo.add_argument("--name", help="Video title")
    p_vimeo.add_argument("--description", help="Video description")
    p_vimeo.add_argument(
        "--description-file",
        dest="description_file",
        help="Read description text from a file (UTF-8)",
    )
    p_vimeo.add_argument(
        "--replace-uri",
        dest="replace_uri",
        help="Replace existing video at this Vimeo URI",
    )
    p_vimeo.add_argument(
        "--verbose", action="store_true", help="Verbose logging for this command"
    )
    p_vimeo.add_argument(
        "--quiet", action="store_true", help="Quiet logging for this command"
    )
    p_vimeo.add_argument(
        "--trace",
        action="store_true",
        help="Shell-style trace of key steps and external commands",
    )
    p_vimeo.add_argument(
        "--vimeo-token",
        dest="vimeo_token",
        help="Access token (alias for --credential access_token=...)",
    )
    p_vimeo.add_argument(
        "--vimeo-client-id",
        dest="vimeo_client_id",
        help="Client ID (alias for --credential client_id=...)",
    )
    p_vimeo.add_argument(
        "--vimeo-client-secret",
        dest="vimeo_client_secret",
        help="Client secret (alias for --credential client_secret=...)",
    )
    p_vimeo.add_argument(
        "--credential",
        action="append",
        dest="credential",
        help="Credential slot resolution (repeatable), e.g., 'access_token=$VIMEO_TOKEN'",
    )
    p_vimeo.add_argument(
        "--credential-file",
        dest="credential_file",
        help="Optional dotenv file for resolving @KEY credentials",
    )
    p_vimeo.set_defaults(func=_cmd_vimeo)
