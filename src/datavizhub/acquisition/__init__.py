"""Data acquisition managers (FTP, HTTP, S3, Vimeo) and base interface.

Provides :class:`DataAcquirer` and concrete managers for fetching and uploading
resources from remote sources. See each manager's docstrings for usage and
supported capabilities.
"""

from .base import DataAcquirer, AcquisitionError, NotSupportedError
from .ftp_manager import FTPManager
from .http_manager import HTTPHandler
from .s3_manager import S3Manager
from .vimeo_manager import VimeoManager

__all__ = [
    "DataAcquirer",
    "AcquisitionError",
    "NotSupportedError",
    "FTPManager",
    "HTTPHandler",
    "S3Manager",
    "VimeoManager",
]
