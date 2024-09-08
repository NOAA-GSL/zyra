import argparse
import logging
from datetime import datetime

from datavizhub.utils.DateManager import DateManager


def main():
    # Instantiate the parser
    parser = argparse.ArgumentParser(description="Find missing frames in a directory.")

    # Required arguments
    parser.add_argument(
        "--directory", type=str, help="Directory containing the frames."
    )
    parser.add_argument(
        "--period_seconds", type=int, help="Expected period between frames in seconds."
    )
    parser.add_argument(
        "--datetime_format", type=str, help="Datetime format in the filenames."
    )
    parser.add_argument(
        "--filename_format",
        type=str,
        help="Filename format used to extract the datetime.",
    )
    parser.add_argument(
        "--filename_mask",
        type=str,
        help="Filename mask used to filter files.",
    )
    parser.add_argument(
        "--start_datetime", type=str, help="Start datetime for the range to check."
    )
    parser.add_argument(
        "--end_datetime", type=str, help="End datetime for the range to check."
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose logging."
    )

    # Parse the arguments
    args = parser.parse_args()

    # Set logging level based on verbose argument immediately after parsing arguments
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    # Convert string datetime arguments to datetime objects
    start_datetime = datetime.strptime(args.start_datetime, args.datetime_format)
    end_datetime = datetime.strptime(args.end_datetime, args.datetime_format)

    # Create an instance of the DateManager class
    manager = DateManager()

    # Call the method
    actual_count, expected_count, additional_frames, missing_frames, gaps, additional_dates = manager.find_missing_frames(
        args.directory,
        args.period_seconds,
        args.datetime_format,
        args.filename_format,
        args.filename_mask,
        start_datetime,
        end_datetime,
    )

    # Print the results
    logging.info(f"Actual frame count: {actual_count}")
    logging.info(f"Expected frame count: {expected_count}")
    logging.info(
        f"Missing frames: Total: {len(missing_frames)} Names: {missing_frames}"
    )
    logging.info(
        f"Additional frames: Total: {len(additional_frames)} Names: {additional_frames}"
    )
    logging.debug(f"Gaps: Total {len(gaps)} Names: {gaps}")
    logging.debug(f"Additional Dates: Total {len(additional_dates)} Names: {additional_dates}")


if __name__ == "__main__":
    main()
