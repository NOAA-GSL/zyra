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
