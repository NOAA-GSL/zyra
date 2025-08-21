import logging
import os
import subprocess
from pathlib import Path
from typing import Any, List, Optional, Tuple

import numpy as np
import pygrib
from scipy.interpolate import interp1d
from siphon.catalog import TDSCatalog

from zyra.processing.base import DataProcessor


class GRIBDataProcessor(DataProcessor):
    """Process GRIB data and THREDDS catalogs.

    Reads GRIB files into NumPy arrays and provides utilities for working with
    THREDDS data catalogs. Supports simple longitude shifts for global grids
    and helper functions for stacking 2D slices over time.

    Parameters
    ----------
    catalog_url : str, optional
        Optional THREDDS catalog URL for dataset listing.

    Examples
    --------
    Read a GRIB file into arrays::

        from zyra.processing.grib_data_processor import GRIBDataProcessor

        gp = GRIBDataProcessor()
        data, dates = gp.process(grib_file_path="/path/to/file.grib2", shift_180=True)
    """

    def __init__(self, catalog_url: Optional[str] = None):
        self.catalog_url = catalog_url
        self._data = None
        self._dates = None

    FEATURES = {"load", "process", "save", "validate"}

    # --- DataProcessor interface --------------------------------------------------------
    def load(self, input_source: Any) -> None:
        """Load or set a THREDDS catalog URL.

        Parameters
        ----------
        input_source : Any
            Catalog URL string (converted with ``str()``).
        """
        self.catalog_url = str(input_source)

    def process(self, **kwargs: Any):
        """Process a GRIB file into arrays and timestamps.

        Parameters
        ----------
        grib_file_path : str, optional
            Path to a GRIB file to parse.
        shift_180 : bool, default=False
            If True, roll the longitudes by 180 degrees for global alignment.

        Returns
        -------
        tuple or None
            ``(data_list, dates)`` when ``grib_file_path`` is provided, where
            ``data_list`` is a list of 2D arrays. Otherwise ``None``.
        """
        grib_file_path = kwargs.get("grib_file_path")
        shift_180 = bool(kwargs.get("shift_180", False))
        if grib_file_path:
            self._data, self._dates = self.read_grib_to_numpy(grib_file_path, shift_180)
            return self._data, self._dates
        return None

    def save(self, output_path: Optional[str] = None) -> Optional[str]:
        """Save processed data to a NumPy ``.npy`` file if available.

        Parameters
        ----------
        output_path : str, optional
            Destination filename to write array data to.

        Returns
        -------
        str or None
            The path written to, or ``None`` if there is no data.
        """
        if output_path and self._data is not None:
            np.save(output_path, self._data)
            return output_path
        return None

    # --- Existing utilities -------------------------------------------------------------
    def list_datasets(self) -> None:
        """List datasets from a THREDDS data server catalog configured by ``catalog_url``."""
        if not self.catalog_url:
            logging.warning("No catalog_url set for GRIBDataProcessor.list_datasets().")
            return
        catalog = TDSCatalog(self.catalog_url)
        for ref in catalog.catalog_refs:
            logging.info(f"Catalog: {ref}")
            sub_catalog = catalog.catalog_refs[ref].follow()
            for dataset in sub_catalog.datasets:
                logging.info(f" - Dataset: {dataset}")

    @staticmethod
    def read_grib_file(file_path: str) -> None:
        """Print basic metadata for each GRIB message.

        Parameters
        ----------
        file_path : str
            Path to a GRIB file to inspect.
        """
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
                grib_file.close()
        except Exception as e:
            logging.error(f"Error reading GRIB file: {e}")

    @staticmethod
    def read_grib_to_numpy(
        grib_file_path: str, shift_180: bool = False
    ) -> Tuple[Optional[List], Optional[List]]:
        """Convert a GRIB file into a list of 2D arrays and dates.

        Parameters
        ----------
        grib_file_path : str
            Path to a GRIB file to read.
        shift_180 : bool, default=False
            If True, roll the longitudes by half the width for -180/180 alignment.

        Returns
        -------
        tuple of list or (None, None)
            ``(data_list, dates)`` on success; ``(None, None)`` on error.
        """
        try:
            grbs = pygrib.open(grib_file_path)
        except OSError as e:
            logging.error(f"Error opening GRIB file: {e}")
            return None, None
        data_list = []
        dates = []
        try:
            for grb in grbs:
                data = grb.values
                date = grb.validDate
                if shift_180:
                    data = np.roll(data, data.shape[1] // 2, axis=1)
                data_list.append(data)
                dates.append(date)
        except Exception as e:
            logging.error(f"Error processing GRIB data: {e}")
            return None, None
        finally:
            grbs.close()
        return data_list, dates

    @staticmethod
    def load_data_from_file(file_path: str, short_name: str, shift_180: bool = False):
        """Load one field by ``short_name`` returning data and coordinates.

        Parameters
        ----------
        file_path : str
            Path to the GRIB file.
        short_name : str
            GRIB message shortName to select (e.g., ``"tc_mdens"``).
        shift_180 : bool, default=False
            If True, shift longitudes and roll the data accordingly.

        Returns
        -------
        tuple
            ``(data, lats, lons)`` arrays when found; otherwise ``(None, None, None)``.
        """
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
                return data, lats, lons
            else:
                return None, None, None

    @staticmethod
    def shift_data_180(data: np.ndarray, lons: np.ndarray) -> np.ndarray:
        """Shift global longitude grid by 180 degrees.

        Parameters
        ----------
        data : numpy.ndarray
            2D array of gridded values with longitudes varying along axis=1.
        lons : numpy.ndarray
            2D array of longitudes corresponding to ``data`` (unused for the
            basic roll operation but included for interface symmetry).

        Returns
        -------
        numpy.ndarray
            Rolled data such that a 0–360 grid is centered at -180..180.
        """
        # Roll columns by half the width to move 0–360 to -180..180 ordering
        shift = data.shape[1] // 2
        return np.roll(data, shift, axis=1)

    @staticmethod
    def process_grib_files_wgrib2(
        grib_dir: str, command: List[str], output_file: str
    ) -> None:
        """Invoke an external wgrib2 command for each file in a directory.

        Parameters
        ----------
        grib_dir : str
            Directory containing input GRIB files.
        command : list of str
            Command and arguments to execute (``wgrib2`` invocation).
        output_file : str
            Path to write outputs to, according to the command.
        """
        files = sorted([f for f in os.listdir(grib_dir)])
        for file in files:
            file_path = Path(grib_dir) / file
            logging.info(f"Processing {file_path}...")
            result = subprocess.run(command, capture_output=True, text=True)
            logging.debug(result.stdout)

    @staticmethod
    def combine_into_3d_array(directory: str, file_pattern: str):
        """Combine 2D grids from multiple files into a 3D array.

        Parameters
        ----------
        directory : str
            Root directory to search.
        file_pattern : str
            Glob pattern to match files (used with ``Path.rglob``).

        Returns
        -------
        numpy.ndarray
            A 3D array stacking the first returned field across files.
        """
        directory_path = Path(directory)
        file_paths = sorted(directory_path.rglob(file_pattern))
        if not file_paths:
            raise FileNotFoundError("No files found matching the pattern.")
        data_arrays = [
            GRIBDataProcessor.load_data_from_file(str(path), "tc_mdens", True)[0]
            for path in file_paths
        ]
        combined_data = np.stack(data_arrays, axis=0)
        return combined_data


def interpolate_time_steps(
    data, current_interval_hours: int = 6, new_interval_hours: int = 1
):
    """Interpolate a 3D time-sequenced array to a new temporal resolution.

    Parameters
    ----------
    data : numpy.ndarray
        3D array with time as the first dimension.
    current_interval_hours : int, default=6
        Current spacing in hours between frames in ``data``.
    new_interval_hours : int, default=1
        Desired spacing in hours for interpolated frames.

    Returns
    -------
    numpy.ndarray
        Interpolated array with adjusted time dimension length.
    """
    current_time_points = np.arange(data.shape[0]) * current_interval_hours
    total_duration = current_time_points[-1]
    new_time_points = np.arange(
        0, total_duration + new_interval_hours, new_interval_hours
    )
    interpolated_data = np.zeros((len(new_time_points), data.shape[1], data.shape[2]))
    for i in range(data.shape[1]):
        for j in range(data.shape[2]):
            f = interp1d(current_time_points, data[:, i, j], kind="quadratic")
            interpolated_data[:, i, j] = f(new_time_points)
    return interpolated_data
