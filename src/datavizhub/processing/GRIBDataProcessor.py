import logging
import os
import subprocess
from pathlib import Path

import numpy as np
import pygrib
from scipy.interpolate import interp1d
from siphon.catalog import TDSCatalog


class GRIBDataProcessor:
    def __init__(self, catalog_url=None):
        self.catalog_url = catalog_url

    def list_datasets(self):
        """Lists datasets from a THREDDS data server catalog."""
        catalog = TDSCatalog(self.catalog_url)
        for ref in catalog.catalog_refs:
            logging.info(f"Catalog: {ref}")
            sub_catalog = catalog.catalog_refs[ref].follow()
            for dataset in sub_catalog.datasets:
                logging.info(f" - Dataset: {dataset}")

    def read_grib_file(file_path):
        """Reads a GRIB file and prints out basic information about each message."""
        try:
            with Path(file_path).open("rb") as f:
                grib_file = pygrib.open(f)
                for i, message in enumerate(grib_file, start=1):
                    logging.info(f"Message {i}:")
                    logging.info(f" - Name: {message.name}")
                    logging.info(f" - Short Name: {message.shortName}")
                    logging.info(f" - Valid Date: {message.validDate}")
                    logging.info(f" - Data Type: {message.dataType}")
                    logging.info(f" - Units: {message.units}")
                    logging.info("")
                grib_file.close()
        except Exception as e:
            logging.error(f"Error reading GRIB file: {e}")

    def read_grib_to_numpy(grib_file_path, shift_180=False):
        """
        Reads a GRIB file and converts it to a list of numpy arrays.

        Parameters:
        grib_file_path (str): Path to the GRIB file.
        shift_180 (bool): Whether to shift the data by 180 degrees.

        Returns:
        tuple: A tuple containing a list of numpy arrays and a list of corresponding dates.
        """
        try:
            # Open the GRIB file
            grbs = pygrib.open(grib_file_path)
        except OSError as e:
            print(f"Error opening GRIB file: {e}")
            return None, None

        # Initialize an empty list to store data arrays
        data_list = []
        dates = []

        try:
            # Loop through each time step
            for grb in grbs:
                # Extract the data from the GRIB message
                data = grb.values
                date = grb.validDate

                # Rotate the data by 180 degrees if shift_180 is True
                if shift_180:
                    data = np.roll(data, data.shape[1] // 2, axis=1)

                # Append the data array and date to the lists
                data_list.append(data)
                dates.append(date)
        except Exception as e:
            print(f"Error processing GRIB data: {e}")
            return None, None
        finally:
            # Close the GRIB file
            grbs.close()

        return data_list, dates

        # Convert the list of data arrays to a NumPy array
        data_array = np.array(data_list)

        return data_array, dates

    def load_data_from_file(file_path, short_name, shift_180=False):
        """Load a 2D grid from a GRIB file and return its data, latitudes, and longitudes."""
        with Path(file_path).open("rb") as f:
            grib_file = pygrib.open(f)
            message = next(
                (msg for msg in grib_file if msg.shortName == short_name), None
            )
            if message:
                data = message.values
                lats, lons = message.latlons()
                if shift_180:
                    data = GRIBDataProcessor.shift_data_180(data, lons)
                return (
                    data,
                    lats,
                    lons,
                )  # Return (possibly shifted) data, latitudes, and longitudes
            else:
                return None, None, None  # Return None if no data found

    def process_grib_files_wgrib2(grib_dir, command, output_file):
        # Get a sorted list of GRIB files
        files = sorted([f for f in os.listdir(grib_dir)])

        for file in files:
            file_path = Path(grib_dir) / file
            print(f"Processing {file_path}...")

            # Define the command and arguments
            # command = [
            #     'wgrib2', file_path,
            #     '-match', 'COLMD',
            #     '-match', 'organic',
            #     '-append',
            #     '-grib_out', output_file
            # ]

            result = subprocess.run(command, capture_output=True, text=True)

            # Print the output
            print(result.stdout)

    def combine_into_3d_array(directory, file_pattern):
        """Combine 2D grids from multiple files into a 3D numpy array."""
        directory_path = Path(directory)
        file_paths = sorted(directory_path.rglob(file_pattern))
        if not file_paths:
            raise FileNotFoundError("No files found matching the pattern.")
        data_arrays = [
            GRIBDataProcessor.load_data_from_file(str(path), "tc_mdens", True)
            for path in file_paths
        ]
        combined_data = np.stack(data_arrays, axis=0)
        return combined_data

def interpolate_time_steps(data, current_interval_hours=6, new_interval_hours=1):
    """
    Interpolates data from a current time interval to a desired time interval.

    :param data: 3D numpy array with the first dimension representing time.
    :param current_interval_hours: The current time interval between data points in hours.
    :param new_interval_hours: The desired time interval between interpolated data points in hours.
    :return: Interpolated 3D numpy array with the new time resolution.
    """
    # Current time points
    current_time_points = np.arange(data.shape[0]) * current_interval_hours

    # New time points for interpolation
    total_duration = current_time_points[-1]
    new_time_points = np.arange(0, total_duration + new_interval_hours, new_interval_hours)

    # Interpolated data array initialization
    interpolated_data = np.zeros((len(new_time_points), data.shape[1], data.shape[2]))

    # Perform interpolation for each spatial point
    for i in range(data.shape[1]):
        for j in range(data.shape[2]):
            f = interp1d(current_time_points, data[:, i, j], kind='quadratic')
            interpolated_data[:, i, j] = f(new_time_points)

    return interpolated_data
