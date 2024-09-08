import argparse
import logging

from datavizhub.utils.ImageManager import ImageManager


def main():
    # Set up argument parsing
    parser = argparse.ArgumentParser(
        description="Detect significant changes between consecutive images in a directory."
    )
    parser.add_argument(
        "--directory", type=str, help="The directory containing the images to analyze."
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.1,
        help="The threshold for detecting significant changes (default: 0.1).",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose logging."
    )
    # Parse arguments
    args = parser.parse_args()

    # Set logging level based on verbose argument immediately after parsing arguments
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    # Create an instance of ImageManager and detect significant changes
    manager = ImageManager(args.directory)
    significant_changes = manager.detect_significant_changes(args.threshold)

    # Output the results
    if significant_changes:
        logging.warning("Significant changes detected between the following pairs of images:")
        for change in significant_changes:
            logging.warning(
                f"Significant change: {change[0]} and {change[1]} (Delta: {change[2]})"
            )

    else:
        logging.info("No significant changes detected between the images.")


if __name__ == "__main__":
    main()
