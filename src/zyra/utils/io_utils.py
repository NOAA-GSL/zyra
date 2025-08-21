import sys
from pathlib import Path
from typing import BinaryIO


def open_input(path_or_dash: str) -> BinaryIO:
    """Return a readable binary file-like for path or '-' (stdin)."""
    # Factory method returns a file object; callers are expected to manage it.
    # noqa: SIM115
    return sys.stdin.buffer if path_or_dash == "-" else Path(path_or_dash).open("rb")  # noqa: SIM115


def open_output(path_or_dash: str) -> BinaryIO:
    """Return a writable binary file-like for path or '-' (stdout)."""
    # Factory method returns a file object; callers are expected to manage it.
    # noqa: SIM115
    return sys.stdout.buffer if path_or_dash == "-" else Path(path_or_dash).open("wb")  # noqa: SIM115
