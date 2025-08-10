"""Filesystem helper utilities.

Lightweight helpers for common file and directory operations used across the
project.

Examples
--------
Clean a scratch directory::

    from datavizhub.utils.file_utils import remove_all_files_in_directory

    remove_all_files_in_directory("./scratch")
"""

from __future__ import annotations

import logging
import os
from pathlib import Path


class FileUtils:
    """Namespace for file-related helper routines.

    Examples
    --------
    While most functions are provided at module-level, a class instance can
    be created if you prefer an object to group related operations.
    """

    def __init__(self) -> None:
        pass


def remove_all_files_in_directory(directory: str) -> None:
    """Remove all files and subdirectories under a directory.

    Parameters
    ----------
    directory : str
        Directory to clean.

    Returns
    -------
    None
        This function returns nothing.

    Notes
    -----
    Errors are reported via ``logging.error`` for consistency with the rest of
    the codebase.
    """
    for path in Path(directory).glob("*"):
        try:
            if path.is_file() or path.is_symlink():
                path.unlink()
            elif path.is_dir():
                for child in path.iterdir():
                    if child.is_file() or child.is_symlink():
                        child.unlink()
                path.rmdir()
        except Exception as e:
            logging.error(f"Failed to delete %s. Reason: %s", path, e)
