import json
import logging
from pathlib import Path

from datavizhub.utils.DateManager import DateManager


class JSONFileManager:
    """
    JSONFileManager is a utility class designed to simplify the reading, updating,
    and writing of JSON files. It provides an easy-to-use interface for manipulating
    JSON data stored in files, making it well-suited for applications where JSON
    files serve as data sources or configuration files.

    Key functionalities include reading JSON data from a file into a Python dictionary,
    updating this data in-memory, and then writing the modified data back to the same
    file or a new file. This class abstracts the complexities of file and JSON handling
    in Python, offering a streamlined way to work with JSON file data.

    Usage:
    Initialize the class with the path to a JSON file. Use the `update_data` method
    to modify the in-memory JSON data, and then call `save_file` to persist changes
    back to disk. The class handles file reading and writing errors, ensuring data
    integrity and providing feedback in case of issues.

    Example:
    ```python
    json_manager = JSONFileManager('/path/to/json_file.json')
    json_manager.update_dataset_times(target_id, directory)
    json_manager.save_file()
    ```

    Note:
    It is designed to handle JSON files with straightforward key-value pair structures
    but may require modifications for complex, nested JSON data.
    """

    def __init__(self, file_path):
        """
        Initialize the JSONFileManager with the path to the JSON file.

        Args:
            file_path (str): The path to the JSON file.
        """
        self.file_path = file_path
        self.data = None
        self.read_file()

    def read_file(self):
        """
        Reads the JSON file and stores its content.
        """
        try:
            file = Path(self.file_path)
            with file.open("r") as file:
                self.data = json.load(file)
        except FileNotFoundError:
            logging.error(f"File not found: {self.file_path}")
            self.data = None
        except json.JSONDecodeError:
            logging.error(f"Error decoding JSON from file: {self.file_path}")
            self.data = None

    def save_file(self, new_file_path=None):
        """
        Saves the modified data back to the JSON file or a new file if specified.

        Args:
            new_file_path (str, optional): The path to save the updated JSON file. Defaults to the original file.
        """
        file_path = new_file_path if new_file_path else self.file_path
        try:
            file_ = Path(self.file_path)
            with file_.open("w") as file:
                json.dump(self.data, file, indent=4)
        except OSError:
            logging.error(f"Error writing to file: {file_path}")

    def update_dataset_times(self, target_id, directory):
        """
        Update the start and end times for a specific dataset in the JSON data.

        Args:
            target_id (str): The ID of the dataset to modify.
            directory (str): The directory containing the images that generated the video dataset.

        Returns:
            str: A message indicating the result of the operation.
        """
        if self.data is None:
            return "No data loaded to update."

        date_manager = DateManager()
        start_time, end_time = date_manager.extract_dates_from_filenames(directory)

        for dataset in self.data.get("datasets", []):
            if dataset["id"] == target_id:
                dataset["startTime"] = start_time
                dataset["endTime"] = end_time
                self.save_file()
                return f"Dataset '{target_id}' updated and saved to {self.file_path}"

        return f"No dataset found with the ID: {target_id}"
