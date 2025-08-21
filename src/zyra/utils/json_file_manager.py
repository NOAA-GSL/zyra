"""Read, update, and write JSON files used as simple configs/datasets.

Provides :class:`JSONFileManager` to persist simple JSON structures and to
update dataset start/end times using dates inferred from a directory of frames.

Examples
--------
Update a dataset time window::

    from zyra.utils.json_file_manager import JSONFileManager

    jm = JSONFileManager("./config.json")
    jm.update_dataset_times("my-dataset", "./frames")
    jm.save_file()
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from zyra.utils.date_manager import DateManager


class JSONFileManager:
    """Convenience wrapper for manipulating JSON files.

    Parameters
    ----------
    file_path : str
        Path to a JSON file on disk.

    Examples
    --------
    Read, update, and save::

        jm = JSONFileManager("./data.json")
        jm.data["foo"] = "bar"
        jm.save_file()
    """

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.data = None
        self.read_file()

    def read_file(self) -> None:
        """Read the JSON file from disk into memory.

        Returns
        -------
        None
            Populates ``self.data`` or sets it to ``None`` on error.
        """
        try:
            file = Path(self.file_path)
            with file.open("r") as f:
                self.data = json.load(f)
        except FileNotFoundError:
            logging.error(f"File not found: {self.file_path}")
            self.data = None
        except json.JSONDecodeError:
            logging.error(f"Error decoding JSON from file: {self.file_path}")
            self.data = None

    def save_file(self, new_file_path: str | None = None) -> None:
        """Write the in-memory data back to disk.

        Parameters
        ----------
        new_file_path : str, optional
            If provided, save to this path instead of overwriting the original.
        Returns
        -------
        None
            This method returns nothing.
        """
        file_path = new_file_path if new_file_path else self.file_path
        try:
            file_ = Path(file_path)
            with file_.open("w") as f:
                json.dump(self.data, f, indent=4)
        except OSError:
            logging.error(f"Error writing to file: {file_path}")

    def update_dataset_times(self, target_id: str, directory: str) -> str:
        """Update start/end times for a dataset using directory image dates.

        Parameters
        ----------
        target_id : str
            Dataset identifier to match in the JSON payload.
        directory : str
            Directory to scan for frame timestamps.

        Returns
        -------
        str
            Status message describing the outcome of the update.
        """
        if self.data is None:
            return "No data loaded to update."
        date_manager = DateManager()
        start_time, end_time = date_manager.extract_dates_from_filenames(directory)
        for dataset in self.data.get("datasets", []):
            if dataset.get("id") == target_id:
                dataset["startTime"], dataset["endTime"] = start_time, end_time
                self.save_file()
                return f"Dataset '{target_id}' updated and saved to {self.file_path}"
        return f"No dataset found with the ID: {target_id}"
