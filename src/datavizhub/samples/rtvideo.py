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

import argparse
import logging
import sys
import tempfile
from importlib.resources import files
from pathlib import Path

from datavizhub.datatransfer.FTPManager import FTPManager
from datavizhub.datatransfer.S3Manager import S3Manager
from datavizhub.datatransfer.VimeoManager import VimeoManager
from datavizhub.processing.VideoProcessor import VideoProcessor
from datavizhub.utils.CredentialManager import CredentialManager
from datavizhub.utils.DateManager import DateManager
from datavizhub.utils.ImageManager import ImageManager
from datavizhub.utils.JSONFileManager import JSONFileManager


def setup_arg_parser():
    """Set up and return the argument parser for command-line options."""
    parser = argparse.ArgumentParser(
        description="Create a video from images in a directory and upload to Vimeo and S3."
    )

    parser.add_argument(
        "-i",
        "--input_dir",
        dest="input_dir",
        required=True,
        help="input image directory where to find RT files",
    )

    parser.add_argument(
        "-o",
        "--output_file",
        dest="output_file",
        required=True,
        help="output RT video file",
    )

    parser.add_argument(
        "-vimeo-uri",
        "--existing_video_uri",
        dest="existing_video_uri",
        required=True,
        help="output URI on Vimeo where place updated video",
    )

    parser.add_argument(
        "-id",
        "--dataset_id",
        dest="dataset_id",
        required=True,
        help="catalog dataset ID to update with the new video.",
    )

    parser.add_argument(
        "-period",
        "-duration",
        dest="dataset_duration",
        required=True,
        help="how long of a duration for which to generate the movie (ISO 8601)",
    )

    parser.add_argument(
        "-period_seconds",
        dest="period_seconds",
        required=False,
        type=int,
        default=None,
        help="how long of an interval between each data frame (in seconds)",
    )

    parser.add_argument(
        "-datetime_format",
        dest="datetime_format",
        required=False,
        type=str,
        default=None,
        help="The format of the datetime found in a filename (ISO 8601)",
    )

    parser.add_argument(
        "-filename_format",
        dest="filename_format",
        required=False,
        type=str,
        default=None,
        help=r"The format of the datetime found in a filename (linear_rgb_cyl_(\d{8}_\d{4}))",
    )

    parser.add_argument(
        "-filename_mask",
        dest="filename_mask",
        required=False,
        type=str,
        default=None,
        help="A beginning character sequence that starts each filename",
    )

    parser.add_argument(
        "-vimeo-client",
        "--vimeo_client_id",
        dest="vimeo_client_id",
        default=None,
        help="the vimeo client id associated with the app",
    )

    parser.add_argument(
        "-vimeo-secret",
        "--vimeo_client_secret",
        dest="vimeo_client_secret",
        default=None,
        help="the vimeo client secret associated with the app",
    )

    parser.add_argument(
        "-vimeo-token",
        "--vimeo_access_token",
        dest="vimeo_access_token",
        default=None,
        help="the vimeo access token associated with the app",
    )

    parser.add_argument(
        "-aws-key",
        "--aws_access_key",
        dest="aws_access_key",
        default=None,
        help="the AWS access key required for s3 transfers",
    )

    parser.add_argument(
        "-aws-secret",
        "--aws_secret_key",
        dest="aws_secret_key",
        default=None,
        help="the AWS secret key required for s3 transfers",
    )

    parser.add_argument(
        "-host",
        "--ftp_host",
        dest="ftp_host",
        required=False,
        help="the FTP host to connect to",
        default="public.sos.noaa.gov",
    )

    parser.add_argument(
        "-ftp_port",
        "--ftp_port",
        dest="ftp_port",
        required=False,
        help="the FTP port to connect to",
        default=21,
    )

    parser.add_argument(
        "-r",
        "--remote_dir",
        dest="remote_dir",
        required=False,
        help="the directory on the FTP server to sync",
    )

    parser.add_argument(
        "-u",
        "--username",
        dest="username",
        required=False,
        help="ftp username",
    )

    parser.add_argument(
        "-p",
        "--password",
        dest="password",
        required=False,
        help="ftp password",
    )

    parser.add_argument(
        "-s3",
        "--s3_bucket",
        dest="s3_bucket",
        required=False,
        help="the S3 bucket to store SOSx metadata in",
        default="metadata.sosexplorer.gov",
    )

    parser.add_argument(
        "-b",
        "--basemap",
        dest="basemap",
        required=False,
        help="path to an optional basemap image that will appear behind data in a video",
        default=None,
    )

    parser.add_argument(
        "-skip_frame_check", "--skip_frame_check", action="store_true", help="Skip checking directory for missing or extra frames."
    )

    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose logging."
    )

    return parser


def initialize_credential_manager(expected_keys):
    """
    Initialize the CredentialManager with credentials from the ~/.rtvideo/credentials file,
    and check for the presence of expected keys.

    Args:
        expected_keys (list of str): A list of expected keys to be found in the credentials.

    Returns:
        CredentialManager: An instance of the CredentialManager loaded with credentials.

    Raises:
        FileNotFoundError: If the credentials file is not found.
        KeyError: If any of the expected keys are missing.
    """
    home_directory = Path.home()
    credentials_file = home_directory / ".rtvideo" / "credentials"

    # Ensure credentials file exists
    if not credentials_file.exists():
        raise FileNotFoundError(f"Credentials file not found at {credentials_file}")

    # Initialize CredentialManager with the credentials file
    credential_manager = CredentialManager(str(credentials_file))
    credential_manager.read_credentials(expected_keys=expected_keys)

    # Additionally, check if all expected keys are available as environment variables
    # as a fallback or supplement
    for key in expected_keys:
        if not credential_manager.get_credential(key):
            raise KeyError(f"Missing expected key: {key}")

    return credential_manager


def validate_directories(local_image_directory, output_video_file):
    """Ensure required directories exist, if not, create them."""
    path = Path(local_image_directory)
    exists = path.exists()
    if not exists:
        logging.warning(f"Local directory {local_image_directory} not found. Creating.")
        Path(local_image_directory).mkdir(parents=True, exist_ok=True)

    path = Path(output_video_file)
    exists = path.parent.exists()
    if not exists:
        logging.warning(f"Output directory {path.parent} not found. Creating.")
        Path(path.parent).mkdir(parents=True, exist_ok=True)


def process_ftp_operations(
    ftp_host,
    ftp_port,
    ftp_username,
    ftp_password,
    remote_dir,
    local_image_directory,
    dataset_duration,
):
    """Handle all FTP-related operations: connect, sync files, and disconnect."""
    try:
        ftp_manager = FTPManager(ftp_host, ftp_port, ftp_username, ftp_password)
        ftp_manager.connect()
        ftp_manager.sync_ftp_directory(
            remote_dir, local_image_directory, dataset_duration
        )
        return True
    except Exception as e:
        logging.error(f"FTP operation failed: {e}")
        return False
    finally:
        # Disconnect from the FTP server regardless of success or failure
        ftp_manager.disconnect()


def check_image_frames(
    directory, period_seconds, datetime_format, filename_format, filename_mask
):
    """Check to see if a directory of time-based filenames has missing or extra files."""
    # Initialize DateManager and ImageManager instances
    date_manager = DateManager()
    image_manager = ImageManager(directory)

    try:
        # Find the start and end datetimes of images in the directory
        start_datetime, end_datetime = date_manager.find_start_end_datetimes(directory)
        if start_datetime and end_datetime:
            logging.debug(
                f"Start time: {start_datetime.strftime('%Y-%m-%d %H:%M:%S')}, End time: {end_datetime.strftime('%Y-%m-%d %H:%M:%S')}"
            )
        else:
            logging.warning(
                "No valid dates found in filenames. Check the directory and the filenames."
            )
            return False  # Exiting as no valid date range could be determined

        # Find missing and additional image frames based on the calculated date range and provided interval
        (
            actual_count,
            expected_count,
            additional_frames,
            missing_frames,
            gaps,
            additional_dates,
        ) = date_manager.find_missing_frames(
            directory,
            period_seconds,
            datetime_format,
            filename_format,
            filename_mask,
            start_datetime,
            end_datetime,
        )

        # Handle additional frames: rename them to a .extra file extension
        if additional_frames:
            image_manager.rename_images_to_extra(additional_frames)
            logging.warning(f"Renamed additional frames: {additional_frames}")
        else:
            logging.info(f"No additional frames found for {directory}.")

        # Optionally, log results or handle them as needed
        logging.debug(f"Actual frame count: {actual_count}")
        logging.debug(f"Expected frame count: {expected_count}")
        logging.debug(f"Missing frames: {missing_frames}")
        logging.debug(f"Gaps identified between frames: {gaps}")
        logging.debug(f"Dates for additional frames: {additional_dates}")

        return True

    except Exception as e:
        # General exception handling, can be refined for specific exceptions
        logging.error(f"An error occurred during frame checking: {e}")
        return False


def process_video(local_image_directory, output_video_file, basemap=None):
    """Process video creation from images in the specified directory."""
    try:
        video_processor = VideoProcessor(
            local_image_directory, output_video_file, basemap
        )
        video_processor.process_video()
        return bool(video_processor.validate_video_file(output_video_file))
    except Exception as e:
        logging.error(f"Video processing failed: {e}")
        return False


def upload_video_to_vimeo(
    vimeo_client_id,
    vimeo_client_secret,
    vimeo_access_token,
    output_video_file,
    existing_video_uri,
):
    """
    Upload the processed video to Vimeo. Returns the URI of the uploaded video.

    If the upload fails, logs the error and returns None.
    """
    try:
        vimeo_manager = VimeoManager(
            vimeo_client_id, vimeo_client_secret, vimeo_access_token
        )
        output_video_uri = vimeo_manager.update_video(
            output_video_file, existing_video_uri
        )
        logging.info(f"Vimeo URI: {output_video_uri}")
        return True
    except Exception as e:
        logging.error(f"Vimeo update failed: {e}")
        return False


def update_metadata_and_upload_to_s3(
    aws_access_key, aws_secret_key, aws_bucket_name, dataset_id, local_image_directory
):
    """
    Update metadata based on the latest video and upload it to S3.

    Returns:
        bool: True if the operation was successful, False otherwise.
    """

    # Create a temporary directory
    with tempfile.TemporaryDirectory() as temp_dir:
        logging.debug(f"Temporary directory created at {temp_dir}")

        dataset_file = Path(temp_dir) / "dataset.json"

        try:
            s3_manager = S3Manager(aws_access_key, aws_secret_key, aws_bucket_name)
            s3_manager.download_file("dataset.json", dataset_file)
            json_manager = JSONFileManager(dataset_file)
            json_manager.update_dataset_times(dataset_id, local_image_directory)
            s3_manager.upload_file(dataset_file, "dataset.json")

            return True
        except Exception as e:
            logging.error(f"Metadata update operation failed: {e}")
            return False


def main():
    # Set up and parse command-line arguments first
    parser = setup_arg_parser()
    args = parser.parse_args()

    # Set logging level based on verbose argument immediately after parsing arguments
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    try:
        # Retrieve secrets from credentials file
        expected_keys = [
            "VIMEO_CLIENT_ID",
            "VIMEO_CLIENT_SECRET",
            "VIMEO_ACCESS_TOKEN",
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
        ]
        credential_manager = initialize_credential_manager(expected_keys)

        # If certain arguments were not provided, update them with credentials
        args.vimeo_client_id = (
            args.vimeo_client_id or credential_manager.get_credential("VIMEO_CLIENT_ID")
        )
        args.vimeo_client_secret = (
            args.vimeo_client_secret
            or credential_manager.get_credential("VIMEO_CLIENT_SECRET")
        )
        args.vimeo_access_token = (
            args.vimeo_access_token
            or credential_manager.get_credential("VIMEO_ACCESS_TOKEN")
        )
        args.aws_access_key = args.aws_access_key or credential_manager.get_credential(
            "AWS_ACCESS_KEY_ID"
        )
        args.aws_secret_key = args.aws_secret_key or credential_manager.get_credential(
            "AWS_SECRET_ACCESS_KEY"
        )

    except KeyError as e:
        logging.error(f"Missing credential: {e}")
        sys.exit(1)

    # Validate and prepare directories for image storage and video output
    validate_directories(args.input_dir, args.output_file)

    # Process FTP operations for image synchronization only if FTP details are provided
    if (
        args.ftp_host
        and args.ftp_port
        and args.username
        and args.password
        and not process_ftp_operations(
            args.ftp_host,
            args.ftp_port,
            args.username,
            args.password,
            args.remote_dir,
            args.input_dir,
            args.dataset_duration,
        )
    ):
        sys.exit(1)

    # Check for missing and additional data frames
    if (
        args.input_dir
        and args.period_seconds
        and args.datetime_format
        and args.filename_format
        and args.filename_mask
        and not args.skip_frame_check
    ):
        if not Path(args.input_dir).is_dir():
            logging.error(f"The input directory {args.input_dir} does not exist or is not a directory.")
        elif not check_image_frames(
            args.input_dir,
            args.period_seconds,
            args.datetime_format,
            args.filename_format,
            args.filename_mask,
        ):
            logging.error("Missing and additional image frame check failed.")
    else:
        logging.info("One or more required arguments for checking data frames are missing or skip was specified.")

    # Build the path to the basemap image
    if args.basemap is not None:
        basemap = files("rtvideo.images").joinpath(args.basemap)
    else:
        basemap = None

    # Process and create the video from synchronized images and optional basemap
    if not process_video(args.input_dir, args.output_file, basemap):
        sys.exit(1)

    # logging.info("Temporary Stop")
    # sys.exit(0)

    # Upload the processed video to Vimeo
    if not upload_video_to_vimeo(
        args.vimeo_client_id,
        args.vimeo_client_secret,
        args.vimeo_access_token,
        args.output_file,
        args.existing_video_uri,
    ):
        sys.exit(1)

    logging.info(f"{args.dataset_id} uploaded to Vimeo at {args.existing_video_uri}")

    # Update video metadata and upload it to AWS S3
    if not update_metadata_and_upload_to_s3(
        args.aws_access_key,
        args.aws_secret_key,
        args.s3_bucket,
        args.dataset_id,
        args.input_dir,
    ):
        sys.exit(1)

    logging.info(f"{args.dataset_id} metadata updated on {args.s3_bucket}.")
    sys.exit(0)


if __name__ == "__main__":
    main()
