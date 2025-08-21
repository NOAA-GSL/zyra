"""GRIB utilities used by connectors and managers.

This module centralizes protocol-agnostic helpers for working with GRIB2
index files (.idx), calculating byte ranges, and performing parallel
multi-range downloads.

Notes
-----
- The `.idx` file path is assumed to be the GRIB file path with a `.idx`
  suffix appended, unless a path already ending in `.idx` is provided.
- Pattern filtering uses regular expressions via :func:`re.search`.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from typing import Callable, Iterable


def ensure_idx_path(path: str) -> str:
    """Return the `.idx` path for a GRIB file or pass through an explicit idx path.

    Parameters
    ----------
    path : str
        The GRIB file path or `.idx` path.

    Returns
    -------
    str
        ``path + '.idx'`` if ``path`` does not already end with ``.idx``,
        otherwise returns ``path`` unchanged.
    """
    return path if path.endswith(".idx") else f"{path}.idx"


def parse_idx_lines(idx_bytes_or_text: bytes | str) -> list[str]:
    """Parse a GRIB index payload into non-empty lines.

    Parameters
    ----------
    idx_bytes_or_text : bytes or str
        Raw `.idx` file content.

    Returns
    -------
    list of str
        The non-empty, newline-split lines of the index.
    """
    if isinstance(idx_bytes_or_text, (bytes, bytearray)):
        text = idx_bytes_or_text.decode()
    else:
        text = idx_bytes_or_text
    lines = [ln for ln in text.splitlines() if ln]
    return lines


def idx_to_byteranges(lines: list[str], search_regex: str) -> dict[str, str]:
    """Convert `.idx` lines plus a variable regex into HTTP Range headers.

    Parameters
    ----------
    lines : list of str
        Lines from a GRIB `.idx` file.
    search_regex : str
        Regular expression to select desired GRIB lines (e.g., "PRES:surface").

    Returns
    -------
    dict
        Mapping of ``{"bytes=start-end": matching_idx_line}`` suitable for
        use as Range headers.
    """
    expr = re.compile(search_regex)
    byte_ranges: dict[str, str] = {}
    for n, line in enumerate(lines, start=1):
        if expr.search(line):
            parts = line.split(":")
            if len(parts) < 2:
                continue
            rangestart = parts[1]
            # End is the start of the next record (if present)
            rangeend = ""
            if n < len(lines):
                nxt = lines[n].split(":")
                if len(nxt) > 1:
                    try:
                        rangeend = str(int(nxt[1]) - 1)
                    except ValueError:
                        rangeend = nxt[1]
            byte_ranges[f"bytes={rangestart}-{rangeend}"] = line
    return byte_ranges


def compute_chunks(total_size: int, chunk_size: int = 500 * 1024 * 1024) -> list[str]:
    """Compute contiguous byte ranges that partition a file.

    The final range uses the file size as the inclusive end byte (matching
    the behavior used by ``nodd_fetch.py``).

    Parameters
    ----------
    total_size : int
        Size of the file in bytes.
    chunk_size : int, default 500MB
        Upper bound for each chunk.

    Returns
    -------
    list of str
        Range header strings, e.g., ``["bytes=0-1048575", ...]``.
    """
    if total_size <= 0:
        return []
    ranges: list[str] = []
    start_byte = 0
    # Build split points like [chunk, 2*chunk, ...] up to but not including total_size
    split_points = list(range(0, total_size, chunk_size))[1:]
    for next_byte in split_points:
        ranges.append(f"bytes={start_byte}-{int(next_byte) - 1}")
        start_byte = next_byte
    ranges.append(f"bytes={start_byte}-{int(total_size)}")
    return ranges


def parallel_download_byteranges(
    download_func: Callable[[str, str], bytes],
    key_or_url: str,
    byte_ranges: Iterable[str],
    *,
    max_workers: int = 10,
) -> bytes:
    """Download multiple byte ranges in parallel and concatenate in input order.

    Parameters
    ----------
    download_func : Callable
        Function accepting ``(key_or_url, range_header)`` and returning bytes.
    key_or_url : str
        The resource identifier for the remote object.
    byte_ranges : Iterable[str]
        Iterable of Range header strings (e.g., "bytes=0-99"). Order matters
        and is preserved in the output concatenation.
    max_workers : int, default=10
        Maximum number of worker threads.

    Returns
    -------
    bytes
        The concatenated payload of all requested ranges in the input order.
    """
    # Preserve order by indexing the ranges and reassembling in order.
    indexed = list(enumerate(byte_ranges))
    if not indexed:
        return b""
    results: dict[int, bytes] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(download_func, key_or_url, rng): idx for idx, rng in indexed
        }
        for fut in as_completed(future_map):
            idx = future_map[fut]
            results[idx] = fut.result() or b""

    buf = BytesIO()
    for idx, _ in indexed:
        buf.write(results.get(idx, b""))
    return buf.getvalue()
