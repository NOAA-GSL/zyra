import logging
import os
from pathlib import Path

import numpy as np
from PIL import Image


class ImageManager:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.filepaths = [
            p
            for p in sorted(self.directory.glob("*"))
            if p.suffix.lower() in [".jpg", ".png", ".jpeg"]
        ]

    def load_image(self, filepath):
        """Load a single image from the specified filepath."""
        try:
            image = Image.open(filepath)
            return np.array(image)
        except Exception as e:
            logging.error(f"Error loading {filepath.name}: {e}")
            return None

    def calculate_delta(self, image1, image2):
        """Calculate the delta between two images."""
        if image1.shape != image2.shape:
            raise ValueError("Images must be of the same size")
        delta = np.abs(image1.astype("int16") - image2.astype("int16"))
        normalized_delta = np.mean(delta) / 255
        return normalized_delta

    def detect_significant_changes(self, threshold=0.1):
        flagged_images = []
        prev_image = None
        prev_filename = ""

        for filepath in self.filepaths:
            current_image = self.load_image(filepath)
            if current_image is None:  # Skip if the image couldn't be loaded
                continue

            if prev_image is not None:
                delta = self.calculate_delta(prev_image, current_image)
                if delta >= threshold:
                    flagged_images.append((prev_filename, filepath.name, delta))
                    # logging.info(f"Significant change detected between {prev_filename} and {filepath.name}: Delta={delta}")

            prev_image = current_image
            prev_filename = filepath.name

        return flagged_images

    def report_dimensions(self, filepath):
        """Report the dimensions of a single image."""
        try:
            with Image.open(filepath) as img:
                return img.size  # Returns a tuple (width, height)
        except Exception as e:
            logging.error(f"Error obtaining dimensions for {filepath.name}: {e}")
            return None

    def copy_image_to_new_files(self, source_image_path, new_filenames):
        """
        Copy an existing image to new files specified in the list of filenames, logging the process.
        The image type is determined from the source image.

        :param source_image_path: String, the file path of the source image to be copied.
        :param new_filenames: List of strings, where each string is a filename where the copied image will be saved.
        """
        try:
            # Open the source image
            with Image.open(source_image_path) as source_image:
                # Determine the image type from the source image file extension
                image_type = source_image.format

                if not image_type:  # In case the format cannot be determined
                    raise ValueError("Cannot determine the source image format.")

                for filename in new_filenames:
                    # Ensure the filename ends with the correct extension
                    extension = image_type.lower()
                    if not filename.lower().endswith(f".{extension}"):
                        filename += f".{extension}"

                    # Save a copy of the source image to the new filename
                    source_image.save(filename, image_type)
                    logging.info(
                        f"Copied {source_image_path} to {filename} as {image_type}."
                    )
        except Exception as e:
            logging.error(f"Error copying {source_image_path}: {e}")


    def rename_images_to_extra(self, filepaths):
        """
        Rename image files represented by filenames (without a full directory structure and extension)
        by appending '.extra' after the original filename and extension, based on the extension of the
        first found image file in the default directory.

        :param filepaths: List of strings, where each string is a filename (without extension)
                        of the image to be renamed.
        :param default_directory: String representing the directory where the files are located.
                                Defaults to the current directory.
        """
        default_dir = Path(self.directory)

        # Attempt to find the first image file in the directory to determine the extension
        image_extension = None
        for file in default_dir.iterdir():
            if file.is_file() and file.suffix in [
                ".jpg",
                ".jpeg",
                ".png",
                ".gif",
            ]:  # Add other image formats as needed
                image_extension = file.suffix
                break

        if image_extension is None:
            logging.error(
                "No image files found in the directory to determine the extension."
            )
            return

        for filename in filepaths:
            # Construct the full original filepath using the determined image extension
            original_filepath = default_dir / (filename + image_extension)
            # Create a new file name by appending '.extra' after the original filename including its extension
            new_filepath = original_filepath.with_name(original_filepath.name + ".extra")

            # Attempt to rename the file
            try:
                original_filepath.rename(new_filepath)
                logging.info(f"Renamed {original_filepath} to {new_filepath}")
            except Exception as e:
                logging.error(f"Error renaming {original_filepath} to {new_filepath}: {e}")
