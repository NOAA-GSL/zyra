# SPDX-License-Identifier: Apache-2.0
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO, Iterator


@contextmanager
def open_input(path_or_dash: str) -> Iterator[BinaryIO]:
    """Yield a readable binary file-like for path or '-' (stdin) without closing stdin.

    When ``path_or_dash`` is '-', yields ``sys.stdin.buffer`` and does not close it on exit.
    Otherwise opens the given path and closes it when the context exits.
    """
    if path_or_dash == "-":
        yield sys.stdin.buffer
    else:
        with Path(path_or_dash).open("rb") as f:
            yield f


@contextmanager
def open_output(path_or_dash: str) -> Iterator[BinaryIO]:
    """Yield a writable binary file-like for path or '-' (stdout) without closing stdout.

    When ``path_or_dash`` is '-', yields ``sys.stdout.buffer`` and does not close it on exit.
    Otherwise opens the given path and closes it when the context exits.
    """
    if path_or_dash == "-":
        yield sys.stdout.buffer
    else:
        with Path(path_or_dash).open("wb") as f:
            yield f


def open_input_file(path_or_dash: str) -> BinaryIO:
    """Backward-compatible factory returning a readable binary stream.

    - When ``path_or_dash`` is '-', returns ``sys.stdin.buffer``; caller must
      NOT close it.
    - Otherwise returns an open file object in ``'rb'`` mode; caller is
      responsible for closing it.

    Prefer ``open_input`` (context manager) in new code to avoid leaking file
    descriptors and to ensure stdout/stdin are not accidentally closed.
    """
    # Returning an open file object is intentional for backwards compatibility.
    return sys.stdin.buffer if path_or_dash == "-" else Path(path_or_dash).open("rb")  # noqa: SIM115


def open_output_file(path_or_dash: str) -> BinaryIO:
    """Backward-compatible factory returning a writable binary stream.

    - When ``path_or_dash`` is '-', returns ``sys.stdout.buffer``; caller must
      NOT close it.
    - Otherwise returns an open file object in ``'wb'`` mode; caller is
      responsible for closing it.

    Prefer ``open_output`` (context manager) in new code to avoid leaking file
    descriptors and to ensure stdout/stdin are not accidentally closed.
    """
    # Returning an open file object is intentional for backwards compatibility.
    return sys.stdout.buffer if path_or_dash == "-" else Path(path_or_dash).open("wb")  # noqa: SIM115


def read_bytes_any(
    path_or_url: str,
    *,
    idx_pattern: str | None = None,
    unsigned: bool = False,
) -> bytes:
    """Read bytes from a local path, ``-`` (stdin), or an HTTP(S)/S3 URL.

    URLs support GRIB ``.idx`` sidecar subsetting: when ``idx_pattern``
    is given, only the byte ranges whose index lines match the regex
    are fetched (the NOAA GRIB2-on-S3 access pattern — HRRR/GFS style).
    ``unsigned`` enables anonymous access for public S3 buckets.

    Raises
    ------
    RuntimeError
        On fetch failures, unsupported schemes, or missing local paths.
        Callers map this to their own error convention (CLI handlers log
        and return 2; ``zyra.cli`` converts to ``SystemExit``).
    """
    if path_or_url == "-":
        return sys.stdin.buffer.read()

    p = Path(path_or_url)
    if p.exists():
        return p.read_bytes()

    if path_or_url.startswith(("http://", "https://")):
        try:
            from zyra.connectors.backends import http as http_backend
            from zyra.utils.grib import idx_to_byteranges

            if idx_pattern:
                lines = http_backend.get_idx_lines(path_or_url)
                ranges = idx_to_byteranges(lines, idx_pattern)
                return http_backend.download_byteranges(path_or_url, ranges.keys())
            return http_backend.fetch_bytes(path_or_url)
        except Exception as exc:
            raise RuntimeError(f"Failed to fetch from URL: {exc}") from exc

    if path_or_url.startswith("s3://"):
        try:
            from zyra.connectors.backends import s3 as s3_backend
            from zyra.utils.grib import idx_to_byteranges

            if idx_pattern:
                lines = s3_backend.get_idx_lines(path_or_url, unsigned=unsigned)
                ranges = idx_to_byteranges(lines, idx_pattern)
                return s3_backend.download_byteranges(
                    path_or_url, None, ranges.keys(), unsigned=unsigned
                )
            return s3_backend.fetch_bytes(path_or_url, unsigned=unsigned)
        except Exception as exc:
            raise RuntimeError(f"Failed to fetch from S3: {exc}") from exc

    raise RuntimeError(f"Input not found or unsupported scheme: {path_or_url}")
