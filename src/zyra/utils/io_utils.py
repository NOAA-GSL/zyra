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
