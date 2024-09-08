import glob
import logging
import os
from pathlib import Path


class FileUtils:
    """
    A utility class for file operations.
    """

    def __init__(self):
        """
        Initialize the FileUtils class.
        """
        pass

def remove_all_files_in_directory(directory):
    files = Path(directory).glob('*')
    for file in files:
        try:
            if Path(file).is_file() or Path(file).is_symlink():
                Path(file).unlink()
            elif Path(file).is_dir():
                for _ in os.listdir(file):
                    Path(file).unlink()
                Path(file).rmdir()
        except Exception as e:
            print(f'Failed to delete {file}. Reason: {e}')
