# SPDX-License-Identifier: Apache-2.0
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
    file_path : str | None
        Optional path to a JSON file on disk. When provided, the file is read
        immediately and made available via ``self.data``. When omitted, the
        instance can be used with ``read_json``/``write_json`` utility methods
        for ad-hoc file operations.

    Examples
    --------
    Read, update, and save::

        jm = JSONFileManager("./data.json")
        jm.data["foo"] = "bar"
        jm.save_file()

    Ad-hoc helpers without binding to a path::

        jm = JSONFileManager()
        data = jm.read_json("./input.json")
        jm.write_json("./out.json", data)
    """

    def __init__(self, file_path: str | None = None):
        self.file_path = file_path
        self.data = None
        if file_path:
            self.read_file()

    def read_file(self) -> None:
        """Read the JSON file from disk into memory.

        Returns
        -------
        None
            Populates ``self.data`` or sets it to ``None`` on error.
        """
        try:
            if not self.file_path:
                # Nothing to read if no file path is bound
                self.data = None
                return
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
            if not file_path:
                raise OSError("No file path provided for save_file")
            file_ = Path(file_path)
            with file_.open("w") as f:
                json.dump(self.data, f, indent=4)
        except OSError:
            logging.error(f"Error writing to file: {file_path}")

    # Lightweight helpers for callers that want one-off JSON IO without
    # binding the manager to a specific path at construction time.
    def read_json(self, path: str):
        """Read JSON from ``path`` and return the parsed object.

        Returns ``None`` and logs on error.
        """
        try:
            text = Path(path).read_text(encoding="utf-8")
            return json.loads(text)
        except FileNotFoundError:
            logging.error(f"File not found: {path}")
            return None
        except json.JSONDecodeError:
            logging.error(f"Invalid JSON in file: {path}")
            return None
        except (OSError, UnicodeDecodeError) as exc:
            logging.error(f"Error reading JSON from file {path}: {exc}")
            return None

    def write_json(self, path: str, data) -> None:
        """Write ``data`` as pretty JSON to ``path``.

        Logs on error and does not raise.
        """
        # Serialize first so programming errors (unserializable objects) surface clearly
        text: str
        try:
            text = json.dumps(data, indent=2) + "\n"
        except (TypeError, ValueError):
            # Treat invalid JSON payloads as programming errors; let them propagate
            raise
        # Perform IO separately and log OS-level failures
        try:
            Path(path).write_text(text, encoding="utf-8")
        except OSError as exc:
            logging.error(f"Error writing JSON to file {path}: {exc}")

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
