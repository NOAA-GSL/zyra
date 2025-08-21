"""Filesystem helper utilities.

Lightweight helpers for common file and directory operations used across the
project.

Examples
--------
Clean a scratch directory::

    from zyra.utils.file_utils import remove_all_files_in_directory

    remove_all_files_in_directory("./scratch")
"""

from __future__ import annotations

import logging
import shutil
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
                shutil.rmtree(path)
        except PermissionError as e:
            logging.error("Permission denied when deleting %s. Reason: %s", path, e)
        except FileNotFoundError as e:
            logging.error(
                "File or directory not found when deleting %s. Reason: %s", path, e
            )
        except OSError as e:
            logging.error("OS error when deleting %s. Reason: %s", path, e)
        except Exception as e:
            logging.error("Unexpected error when deleting %s. Reason: %s", path, e)
