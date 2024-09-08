import logging
import os
import re
from datetime import datetime, timedelta
from pathlib import Path


class DateManager:
    """
    DateManager is a class designed to handle date calculations and manipulations, particularly
    for generating date ranges based on various formats. This class simplifies tasks like calculating
    dates from a given period in the past (using ISO 8601 period formats like '1Y' for one year,
    '6M' for six months, etc.) and formatting these dates for use in applications.

    The class is especially useful in scenarios where date ranges are required, such as generating
    reports, filtering data by date, or setting up schedules. It supports multiple date formats and
    can handle different types of date inputs, making it versatile for various date-related operations.

    Usage:
    Initialize the class with a list of potential date formats. Use the `get_date_range` method
    to calculate start and end dates based on an ISO 8601 period string. The class handles the parsing
    and conversion of these period strings into actual date ranges.

    Example:
    ```python
    date_manager = DateManager(['%Y%m%d', '%d-%m-%Y'])
    start_date, end_date = date_manager.get_date_range('1Y')
    print('Start Date:', start_date, 'End Date:', end_date)
    ```

    Note:
    The ISO 8601 period parsing in this class is an approximation and handles basic formats.
    For more complex period calculations, additional logic may be required. Also, ensure that
    date formats provided to the class are consistent with the dates being parsed.
    """

    def __init__(self, date_format="%Y%m%d"):
        """
        Initialize the DateManager with a specific date format.

        Args:
            date_format (str): The format to return dates in. Defaults to '%Y%m%d'.
        """
        self.date_format = date_format

    def parse_iso_period(self, period):
        """
        Parses an ISO 8601 period string and returns the corresponding timedelta.

        Args:
            period (str): The ISO 8601 period string (e.g., '1Y', '6M').

        Returns:
            timedelta: A timedelta object representing the period.
        """
        period_pattern = r"(\d+)([YMWD])"
        periods = re.findall(period_pattern, period)

        delta_args = {"days": 0, "weeks": 0, "months": 0, "years": 0}
        for amount, unit in periods:
            if unit == "Y":
                delta_args["years"] = int(amount)
            elif unit == "M":
                delta_args["months"] = int(amount)
            elif unit == "W":
                delta_args["weeks"] = int(amount) * 7
            elif unit == "D":
                delta_args["days"] = int(amount)

        # Convert months and years to days (approximation)
        total_days = (
            delta_args["years"] * 365
            + delta_args["months"] * 30
            + delta_args["weeks"]
            + delta_args["days"]
        )
        return timedelta(days=total_days)

    def convert_yyyymmdd_to_yyjjj(self, date_str):
        """
        Convert a date string in 'YYYYMMDD' format to 'YYJJJ' format,
        where 'YY' is the last two digits of the year and 'JJJ' is the Julian day.

        Args:
            date_str (str): Date string in 'YYYYMMDD' format.

        Returns:
            str: Date string in 'YYJJJ' format.

        Raises:
            ValueError: If the input date_str is not in the correct format.
        """
        from datetime import datetime

        try:
            # Parse the input date string
            date = datetime.strptime(date_str, "%Y%m%d")
        except ValueError as e:
            raise ValueError(
                f"Invalid date format: {date_str}. Expected 'YYYYMMDD'."
            ) from e

        # Extract the last two digits of the year
        year = date.year % 100

        # Calculate the Julian day
        julian_day = date.timetuple().tm_yday

        # Return the formatted string
        return f"{year:02d}{julian_day:03d}"

    def get_date_range(self, period):
        """
        Calculates the current date and the date a certain period ago according to ISO 8601 format.

        Args:
            period (str): The ISO 8601 period string (e.g., '1Y', '6M').

        Returns:
            tuple: A tuple containing start_date and end_date.
        """
        current_date = datetime.now().replace(second=0, microsecond=0)
        period_delta = self.parse_iso_period(period)
        past_date = current_date - period_delta

        return past_date, current_date

    def extract_date_time(self, filename):
        """
        Enhanced to extract both date and time from a filename, supporting multiple formats.
        This version also strips off leading non-numeric characters from filenames.

        Args:
            filename (str): The filename containing a date and possibly a time.

        Returns:
            str: The extracted date and time as an ISO formatted string, or None if no datetime is found.
        """
        # Remove leading non-numeric characters (e.g., from 'pw_20240226_1900.jpg')
        cleaned_filename = re.sub(r"^[^\d]+", "", filename)

        date_time_formats = [
            ("%Y%m%d", r"\d{4}\d{2}\d{2}"),  # For '20240111'
            (
                "%Y%m%d_%H%M",
                r"\d{4}\d{2}\d{2}_\d{2}\d{2}",
            ),  # Correct format for '20240211_0620'
            (
                "%Y%m%d%H%M",
                r"\d{4}\d{2}\d{2}\d{2}\d{2}",
            ),  # For continuous digits '202402090000'
            (
                "%Y-%m-%dT%H_%M_%SZ",
                r"\d{4}-\d{2}-\d{2}T\d{2}_\d{2}_\d{2}Z",
            ),  # ISO 8601 format
        ]

        for dt_format, regex in date_time_formats:
            match = re.search(regex, cleaned_filename)
            if match:
                try:
                    extracted_date_str = match.group()
                    extracted_date = datetime.strptime(extracted_date_str, dt_format)
                    if not any(
                        c.isdigit() for c in extracted_date_str[-5:]
                    ):  # Checks if time is missing
                        extracted_date = extracted_date.replace(
                            hour=0, minute=0, second=0
                        )
                    return extracted_date.isoformat()
                except ValueError as e:
                    logging.error(
                        f"Failed to convert extracted date string to datetime object: {e}"
                    )
                    return None
            else:
                logging.debug(
                    f"No match found with format {dt_format} for filename {cleaned_filename}"
                )

        logging.error(f"No valid date extracted from filename: {filename}")
        return None

    def is_date_in_range(self, filepath, start_date, end_date):
        """
        Checks if the date in the filename at the given path falls within the given date range.

        Args:
            filepath (str): The path of the file containing a date in its filename.
            start_date (datetime): The start date of the range.
            end_date (datetime): The end date of the range.

        Returns:
            bool: True if the date is within the range, False otherwise or if no date is found in the filename,
                  or if the path is not a file.
        """
        path = Path(filepath)

        # # Check if the path exists
        # if not path.exists():
        #     logging.error(f"The path does not exist: {filepath}")
        #     return False

        # # Check if the path is not a file
        # if not path.is_file():
        #     logging.error(f"The path does not point to a valid file: {filepath}")
        #     return False

        filename = path.name
        extracted_date_str = self.extract_date_time(filename)
        logging.debug(f"Extracted date string: {extracted_date_str}")

        if extracted_date_str:
            try:
                extracted_date = datetime.fromisoformat(extracted_date_str)
                # Now check if the extracted date is within the range
                if start_date <= extracted_date <= end_date:
                    logging.debug(
                        f"Date {extracted_date} is within range {start_date} to {end_date}."
                    )
                    return True
                else:
                    logging.debug(
                        f"Date {extracted_date} is not within range {start_date} to {end_date}."
                    )
            except ValueError as e:
                # This block catches errors in converting the extracted date string to a datetime object
                logging.error(
                    f"Error converting extracted date string to datetime: {e}"
                )
        else:
            # This means there was no valid date string extracted from the filename
            logging.error(f"No valid date extracted from filename: {filename}")

        return False

    def extract_dates_from_filenames(
        self,
        directory_path,
        image_extensions=(".jpg", ".jpeg", ".png", ".gif", ".bmp", ".dds"),
    ):
        """
        Extract dates from the first and last image file names in a directory.

        Args:
            directory_path (str): Path to the directory containing the files.
            image_extensions (tuple): Tuple of image file extensions to consider.

        Returns:
            tuple: A tuple containing the date from the first and last file names.
        """
        # List all files in the directory and sort them
        files = sorted(
            file
            for file in os.listdir(directory_path)
            if file.lower().endswith(image_extensions)
        )

        # Get the first and last files
        first_file = files[0] if files else None
        last_file = files[-1] if files else None

        # Use the existing extract_date_time method to extract dates from filenames
        first_file_date = self.extract_date_time(first_file) if first_file else None
        last_file_date = self.extract_date_time(last_file) if last_file else None

        # Return the extracted dates
        return first_file_date, last_file_date

    def calculate_expected_frames(self, start_datetime, end_datetime, period_seconds):
        """Calculate the expected number of frames based on the time period and interval."""
        total_seconds = (end_datetime - start_datetime).total_seconds()
        # Adding one to include both start and end times in the count
        return int(total_seconds // period_seconds) + 1

    def datetime_format_to_regex(self, datetime_format):
        """Convert a datetime format string to a regular expression."""
        format_to_regex = {
            "%Y": r"\d{4}",
            "%m": r"\d{2}",
            "%d": r"\d{2}",
            "%H": r"\d{2}",
            "%M": r"\d{2}",
            "%S": r"\d{2}",
            # Add more mappings if you use other format specifiers
        }
        regex = datetime_format
        for format_spec, regex_spec in format_to_regex.items():
            regex = regex.replace(format_spec, regex_spec)
        return regex

    def parse_timestamps_from_filenames(self, filenames, datetime_format):
        """Parse timestamps from filenames based on the given format."""
        timestamps = []
        if datetime_format is not None:
            regex = self.datetime_format_to_regex(datetime_format)
            logging.debug(f"regex: {regex}")
        for filename in filenames:
            try:
                # Extracting the datetime part from the filename
                timestamp_str = re.search(regex, filename).group()
                # Converting the extracted string to a datetime object
                timestamp = datetime.strptime(timestamp_str, datetime_format)
                # logging.debug(f"timestamp str: {timestamp_str}")
                timestamps.append(timestamp)
            except Exception as e:
                logging.error(f"Error parsing timestamp from {filename}: {e}")
        return sorted(timestamps)

    def find_start_end_datetimes(self, directory):
        """
        Scans the specified directory for files, sorts them, and uses the DateManager's
        extract_date_time method to extract timestamps from the first and last filenames,
        identifying the earliest and latest datetimes.

        Args:
            directory (str): The directory to scan for files.
            date_manager (DateManager): An instance of the DateManager class with predefined formats.

        Returns:
            tuple: A tuple containing the start datetime and end datetime. If no valid dates are found, returns (None, None).
        """
        files = sorted(os.listdir(directory))
        if not files:  # Check if the list is empty
            return None, None

        start_datetime_str = self.extract_date_time(files[0])
        end_datetime_str = self.extract_date_time(files[-1])

        start_datetime = (
            datetime.fromisoformat(start_datetime_str) if start_datetime_str else None
        )
        end_datetime = (
            datetime.fromisoformat(end_datetime_str) if end_datetime_str else None
        )

        return start_datetime, end_datetime

    def find_missing_frames_and_predict_names(
        self, timestamps, period_seconds, filename_pattern
    ):
        """Find gaps and overfrequent frames in timestamps and predict missing frame names."""
        gaps = []
        additional_frames = []  # Store timestamps of unexpectedly frequent frames
        predicted_missing_frames = []
        predicted_additional_frames = []

        for i in range(1, len(timestamps)):
            gap = (timestamps[i] - timestamps[i - 1]).total_seconds()

            # Check if frames are more frequent than expected
            if gap <= 0.94 * period_seconds:
                additional_frames.append(timestamps[i])
                # Predict additional frame names
                predicted_frame = timestamps[i].strftime(filename_pattern)
                predicted_additional_frames.append(predicted_frame)

            # Check if a gap is identified
            elif gap >= 1.06 * period_seconds:
                gaps.append((timestamps[i - 1], timestamps[i]))
                # Predict missing frame names
                missing_date = timestamps[i - 1] + timedelta(seconds=period_seconds)
                while missing_date < timestamps[i]:
                    predicted_frame = missing_date.strftime(filename_pattern)
                    predicted_missing_frames.append(predicted_frame)
                    missing_date += timedelta(seconds=period_seconds)

        return (
            gaps,
            additional_frames,
            predicted_missing_frames,
            predicted_additional_frames,
        )

    def find_missing_frames(
        self,
        directory,
        period_seconds,
        datetime_format,
        filename_format,
        filename_mask,
        start_datetime,
        end_datetime,
    ):
        """Find missing frames in a local directory with inconsistent period, only for image files."""
        # Retrieve all filenames and filter for only image files
        all_filenames = os.listdir(directory)
        filtered_filenames = [
            f
            for f in all_filenames
            if f.lower().endswith((".jpg", ".png", ".jpeg", ".dds"))
        ]

        actual_filenames = []
        if filename_format != "":
            # Further filter files to include only those within the start and end times
            for filename in filtered_filenames:
                try:
                    # Extract date from filename
                    date_str = re.search(filename_format, filename).group(1)
                    file_date = datetime.strptime(date_str, datetime_format)
                    logging.debug(f"Extracted file date: {file_date.isoformat()}")

                    # Check if date falls within the start and end times
                    if (start_datetime is None or file_date >= start_datetime) and (
                        end_datetime is None or file_date <= end_datetime
                    ):
                        actual_filenames.append(filename)
                except Exception as e:
                    logging.error(f"Error parsing date from {filename}: {e}")
        else:
            actual_filenames = filtered_filenames

        # logging.debug(f"Actual Filenames: {sorted(actual_filenames)}")

        actual_frame_count = len(actual_filenames)
        expected_frame_count = self.calculate_expected_frames(
            start_datetime, end_datetime, period_seconds
        )

        timestamps = self.parse_timestamps_from_filenames(
            actual_filenames, datetime_format
        )
        (
            gaps,
            additional_frames,
            predicted_missing_frames,
            predicted_additional_frames,
        ) = self.find_missing_frames_and_predict_names(
            timestamps, period_seconds, filename_mask + datetime_format
        )
        return (
            actual_frame_count,
            expected_frame_count,
            predicted_additional_frames,
            predicted_missing_frames,
            gaps,
            additional_frames,
        )
