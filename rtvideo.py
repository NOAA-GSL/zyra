#!/usr/bin/env python
"""
RTVideo.py

This script automates the process of creating videos from a collection of images stored in a directory,
and subsequently uploading the resulting video to Vimeo and AWS S3. It's designed to handle various
stages of video processing and uploading, including FTP operations for image synchronization,
video processing, Vimeo uploads, and metadata management on AWS S3.

The script leverages several custom classes for handling specific tasks:
- CredentialManager: Manages application credentials securely and efficiently.
- FTPManager: Handles FTP operations for syncing images from an FTP server.
- JSONFileManager: Manages JSON file operations, particularly for metadata handling.
- S3Manager: Handles interactions with AWS S3 for file uploads and downloads.
- VideoProcessor: Processes a sequence of images to create a video.
- VimeoManager: Manages the upload process of videos to Vimeo.

The script is configurable via command-line arguments, making it flexible for different use cases.
It includes an option to enable verbose logging for detailed debug information.

Key Features:
- Automates video creation from images and uploading to Vimeo.
- Automates metadata management on AWS S3.
- Manages credentials securely using a credential file.
- Supports FTP operations for image fetching.
- Allows for verbose logging to facilitate debugging.

Author: Eric Hackathorn (eric.j.hackathorn@noaa.gov)
"""

import logging
import time  # noqa: F401
from importlib.resources import files  # noqa: F401
from pathlib import Path  # noqa: F401

# Re-exports for test monkeypatch compatibility
# Re-export datavizhub classes with compatibility for 0.1.13 module paths
try:  # datavizhub >= 0.1.13
    from datavizhub.acquisition.ftp_manager import FTPManager  # noqa: F401
    from datavizhub.acquisition.s3_manager import S3Manager  # noqa: F401
    from datavizhub.acquisition.vimeo_manager import VimeoManager  # noqa: F401
    from datavizhub.processing.video_processor import (  # noqa: F401
        VideoProcessor,
    )
    from datavizhub.utils.credential_manager import (  # noqa: F401
        CredentialManager,
    )
    from datavizhub.utils.date_manager import DateManager  # noqa: F401
    from datavizhub.utils.image_manager import ImageManager  # noqa: F401
    from datavizhub.utils.json_file_manager import (  # noqa: F401
        JSONFileManager,
    )
except Exception as _dvz_exc:  # pragma: no cover - import-time fallback
    # Fallback for environments still on older datavizhub or missing package.
    # These attributes are present to allow tests to patch them.
    logging.warning(  # pragma: no cover - informational only
        "datavizhub import failed; falling back to patchable placeholders. "
        "Install datavizhub>=0.1.13 to enable runtime functionality. Error: %s",
        _dvz_exc,
    )
    FTPManager = None  # type: ignore  # pragma: no cover - placeholder
    S3Manager = None  # type: ignore  # pragma: no cover - placeholder
    VimeoManager = None  # type: ignore  # pragma: no cover - placeholder
    VideoProcessor = None  # type: ignore  # pragma: no cover - placeholder
    CredentialManager = None  # type: ignore  # pragma: no cover - placeholder
    DateManager = None  # type: ignore  # pragma: no cover - placeholder
    ImageManager = None  # type: ignore  # pragma: no cover - placeholder
    JSONFileManager = None  # type: ignore  # pragma: no cover - placeholder

from .errors import FtpSyncError, S3UpdateError, VideoProcessingError, VimeoUploadError

# Service layer imports (re-exported at module level)


def initialize_credential_manager(expected_keys):
    """Passthrough to the single source in config.initialize_credential_manager."""
    from .config import initialize_credential_manager as _init

    return _init(expected_keys)


# Thin wrappers to delegate to services while preserving public API


def validate_directories(local_image_directory, output_video_file):
    from .services.fs import validate_directories as _validate

    return _validate(local_image_directory, output_video_file)


def process_ftp_operations(
    ftp_host,
    ftp_port,
    ftp_username,
    ftp_password,
    remote_dir,
    local_image_directory,
    dataset_duration,
    max_retries=5,
    retry_delay=5,
):
    from .services.ftp import process_ftp_operations as _ftp

    try:
        return _ftp(
            ftp_host,
            ftp_port,
            ftp_username,
            ftp_password,
            remote_dir,
            local_image_directory,
            dataset_duration,
            max_retries,
            retry_delay,
        )
    except FtpSyncError:
        if USE_TYPED_ERRORS:
            raise
        return False
    except Exception:
        if USE_TYPED_ERRORS:
            raise
        return False


def check_image_frames(
    directory, period_seconds, datetime_format, filename_format, filename_mask
):
    from .services.frames import check_image_frames as _frames

    return _frames(
        directory, period_seconds, datetime_format, filename_format, filename_mask
    )


def process_video(local_image_directory, output_video_file, basemap=None):
    from .services.video import process_video as _video

    try:
        return _video(local_image_directory, output_video_file, basemap)
    except VideoProcessingError:
        if USE_TYPED_ERRORS:
            raise
        return False
    except Exception:
        if USE_TYPED_ERRORS:
            raise
        return False


def upload_video_to_vimeo(
    vimeo_client_id,
    vimeo_client_secret,
    vimeo_access_token,
    output_video_file,
    existing_video_uri,
):
    from .services.vimeo import upload_video_to_vimeo as _vimeo

    try:
        return _vimeo(
            vimeo_client_id,
            vimeo_client_secret,
            vimeo_access_token,
            output_video_file,
            existing_video_uri,
        )
    except VimeoUploadError:
        if USE_TYPED_ERRORS:
            raise
        return False
    except Exception:
        if USE_TYPED_ERRORS:
            raise
        return False


def update_metadata_and_upload_to_s3(
    aws_access_key, aws_secret_key, aws_bucket_name, dataset_id, local_image_directory
):
    from .services.s3 import update_metadata_and_upload_to_s3 as _s3

    try:
        return _s3(
            aws_access_key,
            aws_secret_key,
            aws_bucket_name,
            dataset_id,
            local_image_directory,
        )
    except S3UpdateError:
        if USE_TYPED_ERRORS:
            raise
        return False
    except Exception:
        if USE_TYPED_ERRORS:
            raise
        return False


# Controls whether wrappers re-raise typed errors (enabled by app.run)
USE_TYPED_ERRORS = False


def setup_arg_parser():
    from .cli import setup_arg_parser as _setup

    return _setup()


def main():
    # Delegate CLI behavior (including sys.exit) to cli.main without circular import
    from .cli import main as _cli_main

    _cli_main()


if __name__ == "__main__":  # pragma: no cover - CLI entry
    main()  # pragma: no cover
