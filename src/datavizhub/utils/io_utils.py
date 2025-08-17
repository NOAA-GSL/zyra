import sys
from typing import BinaryIO
from pathlib import Path


def open_input(path_or_dash: str) -> BinaryIO:
    """Return a readable binary file-like for path or '-' (stdin)."""
    return sys.stdin.buffer if path_or_dash == "-" else Path(path_or_dash).open("rb")


def open_output(path_or_dash: str) -> BinaryIO:
    """Return a writable binary file-like for path or '-' (stdout)."""
    return sys.stdout.buffer if path_or_dash == "-" else Path(path_or_dash).open("wb")
