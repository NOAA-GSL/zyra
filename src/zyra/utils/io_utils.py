# SPDX-License-Identifier: Apache-2.0
import gzip
import sys
import zlib
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


# gzip member header: magic ``1f 8b`` plus compression method 8 (deflate),
# the only method gzip defines. Sniffing bytes (not the ``.gz`` suffix)
# covers stdin and URLs whose names do not end in ``.gz``.
_GZIP_MAGIC = b"\x1f\x8b\x08"


def _is_gz_url(path_or_url: str) -> bool:
    from urllib.parse import urlparse

    return urlparse(path_or_url).path.lower().endswith(".gz")


def _maybe_gunzip(data: bytes, source: str) -> bytes:
    if not data.startswith(_GZIP_MAGIC):
        return data
    try:
        return gzip.decompress(data)
    except (OSError, EOFError, zlib.error) as exc:
        raise RuntimeError(f"Failed to decompress gzip input {source}: {exc}") from exc


def _idx_gzip_error(path_or_url: str) -> RuntimeError:
    return RuntimeError(
        f".idx byte-range subsetting is not supported for gzip-compressed input "
        f"({path_or_url}): index offsets cannot address a compressed stream. "
        "Read the whole file instead (omit the .idx pattern), or acquire it "
        "first and process the local copy."
    )


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

    Gzip-compressed input (e.g., MRMS ``.grib2.gz``) is decompressed
    transparently. Detection uses the gzip magic bytes rather than the
    file extension, so it applies equally to local paths, stdin, and
    URLs. ``.idx`` subsetting cannot be combined with gzip input.

    Raises
    ------
    RuntimeError
        On fetch failures, unsupported schemes, missing local paths,
        corrupt gzip data, or ``idx_pattern`` with gzip-compressed input.
        Callers map this to their own error convention (CLI handlers log
        and return 2; ``zyra.cli`` converts to ``SystemExit``).
    """
    return _maybe_gunzip(
        _read_raw_bytes(path_or_url, idx_pattern=idx_pattern, unsigned=unsigned),
        path_or_url,
    )


def _read_raw_bytes(
    path_or_url: str,
    *,
    idx_pattern: str | None = None,
    unsigned: bool = False,
) -> bytes:
    if path_or_url == "-":
        return sys.stdin.buffer.read()

    p = Path(path_or_url)
    if p.exists():
        try:
            return p.read_bytes()
        except OSError as exc:
            # Keep the advertised RuntimeError contract for unreadable
            # paths (permissions, directories) too.
            raise RuntimeError(f"Failed to read {path_or_url}: {exc}") from exc

    if path_or_url.startswith(("http://", "https://")):
        try:
            from zyra.connectors.backends import http as http_backend
            from zyra.utils.grib import idx_to_byteranges

            if idx_pattern:
                if _is_gz_url(path_or_url):
                    raise _idx_gzip_error(path_or_url)
                lines = http_backend.get_idx_lines(path_or_url)
                ranges = idx_to_byteranges(lines, idx_pattern)
                if not ranges:
                    # Zero matched ranges would download nothing and look
                    # like a successful empty read.
                    raise RuntimeError(
                        f"No .idx lines matched pattern {idx_pattern!r} for {path_or_url}"
                    )
                data = http_backend.download_byteranges(path_or_url, ranges.keys())
                if data.startswith(_GZIP_MAGIC):
                    raise _idx_gzip_error(path_or_url)
                return data
            return http_backend.fetch_bytes(path_or_url)
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(f"Failed to fetch from URL: {exc}") from exc

    if path_or_url.startswith("s3://"):
        try:
            from zyra.connectors.backends import s3 as s3_backend
            from zyra.utils.grib import idx_to_byteranges

            if idx_pattern:
                if _is_gz_url(path_or_url):
                    raise _idx_gzip_error(path_or_url)
                lines = s3_backend.get_idx_lines(path_or_url, unsigned=unsigned)
                ranges = idx_to_byteranges(lines, idx_pattern)
                if not ranges:
                    raise RuntimeError(
                        f"No .idx lines matched pattern {idx_pattern!r} for {path_or_url}"
                    )
                data = s3_backend.download_byteranges(
                    path_or_url, None, ranges.keys(), unsigned=unsigned
                )
                if data.startswith(_GZIP_MAGIC):
                    raise _idx_gzip_error(path_or_url)
                return data
            return s3_backend.fetch_bytes(path_or_url, unsigned=unsigned)
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(f"Failed to fetch from S3: {exc}") from exc

    raise RuntimeError(f"Input not found or unsupported scheme: {path_or_url}")
