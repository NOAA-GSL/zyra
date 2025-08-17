"""Utilities used across DataVizHub (dates, files, images, credentials).

Avoid importing optional heavy dependencies at package import time to keep the
CLI lightweight when only a subset of functionality is needed (e.g., pipeline
runner). Submodules can still be imported directly when required.
"""

from .credential_manager import CredentialManager
from .date_manager import DateManager
from .file_utils import FileUtils, remove_all_files_in_directory
from .json_file_manager import JSONFileManager

# image_manager depends on optional heavy deps (numpy/Pillow). Import lazily when available.
try:  # pragma: no cover - optional path
    from .image_manager import ImageManager  # type: ignore

    _HAS_IMAGE = True
except (ImportError, ModuleNotFoundError):  # pragma: no cover - optional path
    _HAS_IMAGE = False

__all__ = [
    "CredentialManager",
    "DateManager",
    "FileUtils",
    "remove_all_files_in_directory",
    "JSONFileManager",
]
if _HAS_IMAGE:
    __all__.append("ImageManager")
