"""Image utilities for basic inspection and change detection.

Provides :class:`ImageManager` to read images from a directory, compute
normalized deltas between frames, and detect significant changes.

Examples
--------
Detect changes between sequential images::

    from zyra.utils.image_manager import ImageManager

    im = ImageManager("./frames")
    changes = im.detect_significant_changes(threshold=0.15)
    for prev_name, name, delta in changes:
        print(prev_name, name, delta)
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
from PIL import Image


class ImageManager:
    """Work with images in a directory and detect changes.

    Parameters
    ----------
    directory : str
        Path to a directory containing images.

    Examples
    --------
    Measure per-frame deltas for a frame directory::

        im = ImageManager("./frames")
        flagged = im.detect_significant_changes(0.2)
    """

    def __init__(self, directory: str):
        self.directory = Path(directory)
        self.filepaths = [
            p
            for p in sorted(self.directory.glob("*"))
            if p.suffix.lower() in [".jpg", ".png", ".jpeg"]
        ]

    def load_image(self, filepath: str | Path):
        """Load a single image from the specified filepath as a NumPy array.

        Parameters
        ----------
        filepath : str or Path
            Path to the image on disk.

        Returns
        -------
        numpy.ndarray or None
            The image as an array; ``None`` if loading fails.
        """
        try:
            image = Image.open(filepath)
            return np.array(image)
        except Exception as e:
            logging.error(f"Error loading {Path(filepath).name}: {e}")
            return None

    def calculate_delta(self, image1, image2):
        """Calculate normalized mean absolute delta between two images.

        Parameters
        ----------
        image1, image2 : numpy.ndarray
            Images of identical shape.

        Returns
        -------
        float
            Mean absolute difference normalized to [0, 1].

        Raises
        ------
        ValueError
            If the input images differ in shape.
        """
        if image1.shape != image2.shape:
            raise ValueError("Images must be of the same size")
        delta = np.abs(image1.astype("int16") - image2.astype("int16"))
        normalized_delta = np.mean(delta) / 255
        return normalized_delta

    def detect_significant_changes(self, threshold: float = 0.1):
        """Detect pairs of frames that changed by more than the threshold.

        Parameters
        ----------
        threshold : float, default=0.1
            Minimum normalized delta to consider a change significant.

        Returns
        -------
        list of tuple
            Tuples of the form ``(prev_filename, filename, delta)``.
        """
        flagged_images = []
        prev_image = None
        prev_filename = ""
        for filepath in self.filepaths:
            current_image = self.load_image(filepath)
            if current_image is None:
                continue
            if prev_image is not None:
                delta = self.calculate_delta(prev_image, current_image)
                if delta >= threshold:
                    flagged_images.append((prev_filename, filepath.name, delta))
            prev_image = current_image
            prev_filename = filepath.name
        return flagged_images

    def report_dimensions(self, filepath: str | Path):
        """Report the dimensions of a single image as (width, height).

        Parameters
        ----------
        filepath : str or Path
            Path to the image file.

        Returns
        -------
        tuple or None
            Image size ``(width, height)``; ``None`` if loading fails.
        """
        try:
            with Image.open(filepath) as img:
                return img.size
        except Exception as e:
            logging.error(f"Error obtaining dimensions for {Path(filepath).name}: {e}")
            return None

    def copy_image_to_new_files(self, source_image_path: str | Path, new_filenames):
        """Copy an image to multiple new file names, preserving format.

        Parameters
        ----------
        source_image_path : str or Path
            Source image path.
        new_filenames : list of str
            Filenames to create; appropriate extension is appended if needed.

        Returns
        -------
        None
            This method returns nothing.

        Raises
        ------
        ValueError
            If the source image format cannot be determined.
        """
        try:
            with Image.open(source_image_path) as source_image:
                image_type = source_image.format
                if not image_type:
                    raise ValueError("Cannot determine the source image format.")
                for filename in new_filenames:
                    extension = image_type.lower()
                    outname = (
                        filename
                        if filename.lower().endswith(f".{extension}")
                        else f"{filename}.{extension}"
                    )
                    source_image.save(outname, image_type)
                    logging.info(
                        f"Copied {source_image_path} to {outname} as {image_type}."
                    )
        except Exception as e:
            logging.error(f"Error copying {source_image_path}: {e}")

    def rename_images_to_extra(self, filepaths):
        """Append `.extra` to the end of existing image filenames.

        Parameters
        ----------
        filepaths : list of str
            Filenames (without extension) to rename in the managed directory.
        """
        default_dir = Path(self.directory)
        image_extension = None
        for file in default_dir.iterdir():
            if file.is_file() and file.suffix in [".jpg", ".jpeg", ".png", ".gif"]:
                image_extension = file.suffix
                break
        if image_extension is None:
            logging.error(
                "No image files found in the directory to determine the extension."
            )
            return
        for filename in filepaths:
            original_filepath = default_dir / (filename + image_extension)
            new_filepath = original_filepath.with_name(
                original_filepath.name + ".extra"
            )
            try:
                original_filepath.rename(new_filepath)
                logging.info(f"Renamed {original_filepath} to {new_filepath}")
            except Exception as e:
                logging.error(
                    f"Error renaming {original_filepath} to {new_filepath}: {e}"
                )
