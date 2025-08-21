"""Date/time utilities for parsing, ranges, and frame calculations.

Provides :class:`DateManager` for extracting timestamps from filenames, building
date ranges from period specs (e.g., 1Y, 6M, 7D, 24H), and validating or
interpolating time-based frame sequences.

Examples
--------
Parse dates and compute a range::

    from zyra.utils.date_manager import DateManager

    dm = DateManager(["%Y%m%d"])
    start, end = dm.get_date_range("7D")
    ok = dm.is_date_in_range("frame_20240102.png", start, end)
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable


class DateManager:
    """High-level utilities for working with dates and filenames.

    Parameters
    ----------
    date_formats : list of str, optional
        Preferred strftime-style formats to use when parsing dates from
        filenames (e.g., ``["%Y%m%d"]``).

    Examples
    --------
    Use a custom filename format first, then fall back to ISO-like detection::

        dm = DateManager(["%Y%m%d%H%M%S"])
        when = dm.extract_date_time("frame_20240101093000.png")
    """

    def __init__(self, date_formats: list[str] | None = None) -> None:
        """Optionally store preferred date formats for filename parsing."""
        self.date_formats = date_formats or []

    # The remainder of this class mirrors the original DateManager implementation
    # with docstrings retained or added where relevant.

    def get_date_range(self, period: str) -> tuple[datetime, datetime]:
        """Compute a date range ending at the current minute from a period spec.

        Parameters
        ----------
        period : str
            Period string such as ``"1Y"``, ``"6M"``, ``"7D"``, or ``"24H"``.

        Returns
        -------
        (datetime, datetime)
            Start and end datetimes for the period ending at "now" (rounded to minute).
        """
        from dateutil.relativedelta import relativedelta

        now = datetime.now().replace(second=0, microsecond=0)
        unit = period[-1].upper()
        amount = int(period[:-1])
        if unit == "H":
            start = now - timedelta(hours=amount)
        elif unit == "D":
            start = now - timedelta(days=amount)
        elif unit == "M":
            start = now - relativedelta(months=amount)
        elif unit == "Y":
            start = now - relativedelta(years=amount)
        else:
            raise ValueError(f"Unsupported period unit in: {period}")
        return start, now

    def get_date_range_iso(self, iso_duration: str) -> tuple[datetime, datetime]:
        """Compute a date range ending now from an ISO-8601 duration (e.g., P1Y, P6M, P7D, PT24H).

        Supports a subset of ISO-8601: years (Y), months (M), days (D), hours (H)
        with the "P...T..." structure. Examples: "P1Y", "P6M", "P7D", "PT24H".
        """
        now = datetime.now().replace(second=0, microsecond=0)
        years = months = days = hours = 0
        s = iso_duration.strip().upper()
        if not s.startswith("P"):
            raise ValueError(f"Invalid ISO-8601 duration: {iso_duration}")
        # Split date and time parts
        date_part = s[1:]
        time_part = ""
        if "T" in date_part:
            date_part, time_part = date_part.split("T", 1)
        # Parse date components
        m = re.findall(r"(\d+)([YMD])", date_part)
        for num, unit in m:
            n = int(num)
            if unit == "Y":
                years = n
            elif unit == "M":
                months = n
            elif unit == "D":
                days = n
        # Parse time components (hours only, minimal subset)
        tm = re.findall(r"(\d+)([H])", time_part)
        for num, unit in tm:
            n = int(num)
            if unit == "H":
                hours = n
        from dateutil.relativedelta import relativedelta

        start = now - relativedelta(years=years, months=months, days=days, hours=hours)
        return start, now

    def is_date_in_range(
        self, filepath: str, start_date: datetime, end_date: datetime
    ) -> bool:
        """Check if a filename contains a date within a range.

        Parameters
        ----------
        filepath : str
            Path or filename containing a date stamp.
        start_date : datetime
            Inclusive start of the permitted range.
        end_date : datetime
            Inclusive end of the permitted range.

        Returns
        -------
        bool
            True if a parsed date falls within the range, else False.
        """
        path = Path(filepath)
        filename = path.name
        extracted_date_str = self.extract_date_time(filename)
        logging.debug(f"Extracted date string: {extracted_date_str}")
        if extracted_date_str:
            try:
                extracted_date = datetime.fromisoformat(extracted_date_str)
                return start_date <= extracted_date <= end_date
            except ValueError as e:
                logging.error(
                    f"Error converting extracted date string to datetime: {e}"
                )
        else:
            logging.error(f"No valid date extracted from filename: {filename}")
        return False

    def extract_date_time(self, string: str) -> str | None:
        """Extract a date string from a filename/text using known formats.

        Tries known formats first; falls back to a simple ISO-like pattern.
        """
        # Try configured formats
        for fmt in self.date_formats:
            try:
                # Build regex from format and search
                regex = self.datetime_format_to_regex(fmt)
                m = re.search(regex, string)
                if m:
                    dt = datetime.strptime(m.group(), fmt)
                    return dt.isoformat()
            except Exception:
                continue
        # Fallback ISO-like pattern
        match = re.search(r"\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2})?", string)
        return match.group(0) if match else None

    def extract_dates_from_filenames(
        self,
        directory_path: str,
        image_extensions: Iterable[str] = (
            ".jpg",
            ".jpeg",
            ".png",
            ".gif",
            ".bmp",
            ".dds",
        ),
    ) -> tuple[str | None, str | None]:
        """Extract dates from the first and last image file names in a directory.

        Parameters
        ----------
        directory_path : str
            Directory to scan for images.
        image_extensions : Iterable[str]
            File extensions to include when scanning.

        Returns
        -------
        tuple
            ``(first_date, last_date)`` as strings, or ``(None, None)``.
        """
        files = sorted(
            file
            for file in os.listdir(directory_path)
            if file.lower().endswith(tuple(image_extensions))
        )
        first_file = files[0] if files else None
        last_file = files[-1] if files else None
        first_file_date = self.extract_date_time(first_file) if first_file else None
        last_file_date = self.extract_date_time(last_file) if last_file else None
        return first_file_date, last_file_date

    def calculate_expected_frames(
        self, start_datetime: datetime, end_datetime: datetime, period_seconds: int
    ) -> int:
        """Calculate expected frame count between two datetimes at a cadence.

        Returns
        -------
        int
            Number of expected frames (inclusive of endpoints).
        """
        total_seconds = (end_datetime - start_datetime).total_seconds()
        return int(total_seconds // period_seconds) + 1

    def datetime_format_to_regex(self, datetime_format: str) -> str:
        """Convert a datetime format string to a regex pattern."""
        format_to_regex = {
            "%Y": r"\d{4}",
            "%m": r"\d{2}",
            "%d": r"\d{2}",
            "%H": r"\d{2}",
            "%M": r"\d{2}",
            "%S": r"\d{2}",
        }
        regex = datetime_format
        for format_spec, regex_spec in format_to_regex.items():
            regex = regex.replace(format_spec, regex_spec)
        return regex

    def parse_timestamps_from_filenames(self, filenames, datetime_format):
        """Parse timestamps from filenames based on the given format."""
        timestamps = []
        regex = (
            self.datetime_format_to_regex(datetime_format)
            if datetime_format is not None
            else None
        )
        for filename in filenames:
            try:
                ts = re.search(regex, filename).group()
                timestamp = datetime.strptime(ts, datetime_format)
                timestamps.append(timestamp)
            except Exception as e:
                logging.error(f"Error parsing timestamp from {filename}: {e}")
        return sorted(timestamps)

    def find_start_end_datetimes(self, directory: str):
        """Find earliest and latest datetimes from filenames in a directory."""
        files = sorted(os.listdir(directory))
        if not files:
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
        """Find gaps and overfrequent frames in timestamps and predict names."""
        gaps = []
        additional_frames = []
        predicted_missing_frames = []
        predicted_additional_frames = []
        for i in range(1, len(timestamps)):
            gap = (timestamps[i] - timestamps[i - 1]).total_seconds()
            if gap <= 0.94 * period_seconds:
                additional_frames.append(timestamps[i])
                predicted_frame = timestamps[i].strftime(filename_pattern)
                predicted_additional_frames.append(predicted_frame)
            elif gap >= 1.06 * period_seconds:
                gaps.append((timestamps[i - 1], timestamps[i]))
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
        all_filenames = os.listdir(directory)
        filtered_filenames = [
            f
            for f in all_filenames
            if f.lower().endswith((".jpg", ".png", ".jpeg", ".dds"))
        ]
        actual_filenames = []
        if filename_format != "":
            for filename in filtered_filenames:
                try:
                    date_str = re.search(filename_format, filename).group(1)
                    file_date = datetime.strptime(date_str, datetime_format)
                    if (start_datetime is None or file_date >= start_datetime) and (
                        end_datetime is None or file_date <= end_datetime
                    ):
                        actual_filenames.append(filename)
                except Exception as e:
                    logging.error(f"Error parsing date from {filename}: {e}")
        else:
            actual_filenames = filtered_filenames
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
