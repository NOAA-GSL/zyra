import sys
from typing import BinaryIO


def open_input(path_or_dash: str) -> BinaryIO:
    """Return a readable binary file-like for path or '-' (stdin)."""
    return sys.stdin.buffer if path_or_dash == "-" else open(path_or_dash, "rb")


def open_output(path_or_dash: str) -> BinaryIO:
    """Return a writable binary file-like for path or '-' (stdout)."""
    return sys.stdout.buffer if path_or_dash == "-" else open(path_or_dash, "wb")

