from unittest.mock import mock_open, patch

import pytest
from datavizhub.utils.JSONFileManager import JSONFileManager


@pytest.fixture()
def json_manager():
    """Fixture to provide a JSONFileManager instance."""
    file_path = "test.json"
    return JSONFileManager(file_path)


@patch("pathlib.Path.open", new_callable=mock_open, read_data='{"test": "data"}')
def test_read_file(mock_file, json_manager):
    json_manager.read_file()
    mock_file.assert_called_with("r")
    assert json_manager.data == {"test": "data"}


@patch("pathlib.Path.open", new_callable=mock_open)
@patch("json.dump")
def test_save_file(mock_json_dump, mock_file, json_manager):
    new_data = {"new": "data"}
    json_manager.data = new_data
    json_manager.save_file()
    mock_file.assert_called_with("w")
    mock_json_dump.assert_called_with(new_data, mock_file.return_value, indent=4)

    # Test saving to a new file
    new_file_path = "new_test.json"
    json_manager.save_file(new_file_path)
    mock_file.assert_called_with("w")  # Check if it's called with the 'w' mode again
    mock_json_dump.assert_called_with(new_data, mock_file.return_value, indent=4)


@patch("datavizhub.utils.JSONFileManager.DateManager")
def test_update_dataset_times(mock_date_manager, json_manager):
    # Setup mock for DateManager
    mock_date_manager_instance = mock_date_manager.return_value
    mock_date_manager_instance.extract_dates_from_filenames.return_value = (
        "2024-01-01",
        "2024-01-02",
    )

    # Mock data setup
    json_manager.data = {
        "datasets": [
            {"id": "123", "startTime": "oldStart", "endTime": "oldEnd"},
            {"id": "456", "startTime": "oldStart", "endTime": "oldEnd"},
        ]
    }

    # Test updating an existing dataset
    response = json_manager.update_dataset_times("123", "dummy_directory")
    assert response == f"Dataset '123' updated and saved to {json_manager.file_path}"
    assert json_manager.data["datasets"][0]["startTime"] == "2024-01-01"
    assert json_manager.data["datasets"][0]["endTime"] == "2024-01-02"

    # Test updating a non-existent dataset
    response = json_manager.update_dataset_times("nonexistent", "dummy_directory")
    assert response == "No dataset found with the ID: nonexistent"

    # Test calling method when self.data is None
    json_manager.data = None
    response = json_manager.update_dataset_times("123", "dummy_directory")
    assert response == "No data loaded to update."


# Additional tests...
