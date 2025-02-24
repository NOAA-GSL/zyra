#!/usr/bin/env python3

from siphon.catalog import TDSCatalog
import os
import requests
import subprocess
from datetime import datetime, timedelta
import pygrib
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, BoundaryNorm
#from mpl_toolkits.axes_grid1 import make_axes_locatable
import numpy as np
import cartopy.crs as ccrs
import cartopy.feature as cfeature
import ffmpeg
import glob
import sys
from scipy.interpolate import interp1d
#import matplotlib.font_manager as fm
import argparse
import logging

from datavizhub.utils.CredentialManager import CredentialManager
from datavizhub.datatransfer.S3Manager import S3Manager
from pathlib import Path

# Specify the directory containing the GRIB files and the directory for the output images
grib_directory = '/data/grib/fv3'
output_directory = '/data/images/fv3'
output_grib = '/data/grib/fv3/oc.grib'
image_path = '/data/tmp/eic-smoke-basemap.jpg'
overlay_path = '/data/tmp/eic-smoke-overlay.png'
image_extent = (-180.0, 180.0, -90.0, 90.0)

url = "https://gsl.noaa.gov/thredds/catalog/catalog.xml"
sub_catalog_url = "https://gsl.noaa.gov/thredds/catalog/fv3-chem-0p25deg-grib2/catalog.xml"

# Set the global font to Helvetica Regular
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['Helvetica']
plt.rcParams['font.size'] = 74

# Define the colormap data
colormap_data = [
    {"Label": 0.05, "Upper Bound": 5e-07, "Color": [255, 255, 229, 0]},
    {"Label": 0.1, "Upper Bound": 1e-06, "Color": [255, 250, 205, 51]},
    {"Label": 0.2, "Upper Bound": 2e-06, "Color": [254, 244, 181, 102]},
    {"Label": 0.5, "Upper Bound": 5e-06, "Color": [254, 232, 157, 153]},
    {"Label": 1.0, "Upper Bound": 1e-05, "Color": [254, 218, 126, 204]},
    {"Label": 2.0, "Upper Bound": 2e-05, "Color": [254, 200, 88, 240]},
    {"Label": 3.0, "Upper Bound": 3e-05, "Color": [254, 177, 62, 240]},
    {"Label": 4.0, "Upper Bound": 4e-05, "Color": [254, 153, 41, 240]},
    {"Label": 5.0, "Upper Bound": 5e-05, "Color": [243, 129, 29, 240]},
    {"Label": 7.5, "Upper Bound": 7.5e-05, "Color": [231, 106, 17, 240]},
    {"Label": 10.0, "Upper Bound": 0.0001, "Color": [213, 86, 7, 240]},
    {"Label": 20.0, "Upper Bound": 0.0002, "Color": [189, 69, 2, 240]},
    {"Label": 30.0, "Upper Bound": 0.0003, "Color": [131, 45, 4, 240]},
    {"Label": 40.0, "Upper Bound": 0.0004, "Color": [102, 37, 6, 240]},
]

# # Rebuild the font manager to recognize new fonts
# fm._load_fontmanager(try_read_cache=False)

# # Verify if the font is found
# print("Helvetica" in [f.name for f in fm.fontManager.ttflist])

# # Check if the font is found
# if "Roboto" in [f.name for f in fm.fontManager.ttflist]:
#     print("Roboto font successfully installed.")
# else:
#     print("Roboto font installation failed.")

# # Rebuild the font manager to recognize new fonts
# fm._load_fontmanager(try_read_cache=False)

# # Verify if the font is found
# print("Helvetica" in [f.name for f in fm.fontManager.ttflist])


"""# Functions"""

def setup_arg_parser():
    """Set up and return the argument parser for command-line options."""
    parser = argparse.ArgumentParser(
        description="Create a global smoke animation video and upload to S3."
    )

    parser.add_argument(
        "-o",
        "--output_file",
        dest="output_file",
        required=False,
        default="/data/output/smoke.mp4",
        help="output RT video file",
    )

    parser.add_argument(
        "-aws-key",
        "--aws_access_key",
        dest="aws_access_key",
        default=None,
        help="the AWS access key required for s3 transfers",
    )

    parser.add_argument(
        "-aws-secret",
        "--aws_secret_key",
        dest="aws_secret_key",
        default=None,
        help="the AWS secret key required for s3 transfers",
    )

    parser.add_argument(
        "-s3",
        "--s3_bucket",
        dest="s3_bucket",
        required=False,
        help="the S3 bucket to store smoke animation in",
        default="sos-explorer-s3",
    )

    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose logging."
    )

    return parser

def initialize_credential_manager(expected_keys):
    """
    Initialize the CredentialManager with credentials from the ~/.rtvideo/credentials file,
    and check for the presence of expected keys.

    Args:
        expected_keys (list of str): A list of expected keys to be found in the credentials.

    Returns:
        CredentialManager: An instance of the CredentialManager loaded with credentials.

    Raises:
        FileNotFoundError: If the credentials file is not found.
        KeyError: If any of the expected keys are missing.
    """
    home_directory = Path.home()
    credentials_file = home_directory / ".global_smoke" / "credentials"

    # Ensure credentials file exists
    if not credentials_file.exists():
        raise FileNotFoundError(f"Credentials file not found at {credentials_file}")

    # Initialize CredentialManager with the credentials file
    credential_manager = CredentialManager(str(credentials_file))
    credential_manager.read_credentials(expected_keys=expected_keys)

    # Additionally, check if all expected keys are available as environment variables
    # as a fallback or supplement
    for key in expected_keys:
        if not credential_manager.get_credential(key):
            raise KeyError(f"Missing expected key: {key}")

    return credential_manager

def remove_all_files_in_directory(directory):
    files = glob.glob(os.path.join(directory, '*'))
    for file in files:
        try:
            if os.path.isfile(file) or os.path.islink(file):
                os.unlink(file)
            elif os.path.isdir(file):
                for subfile in os.listdir(file):
                    os.unlink(os.path.join(file, subfile))
                os.rmdir(file)
        except Exception as e:
            print(f'Failed to delete {file}. Reason: {e}')

def list_datasets(catalog_url):
    catalog = TDSCatalog(catalog_url)

    for ref in catalog.catalog_refs:
        print(f"Catalog: {ref}")
        sub_catalog = catalog.catalog_refs[ref].follow()
        for dataset in sub_catalog.datasets:
            print(f" - Dataset: {dataset}")

def convert_to_yyjjj(date_str):
    date = datetime.strptime(date_str, '%Y%m%d')
    year = date.year % 100
    julian_day = date.timetuple().tm_yday
    return f"{year:02d}{julian_day:03d}"

def download_file(url, output_path):
    response = requests.get(url)
    if response.status_code == 200:
        with open(output_path, 'wb') as file:
            file.write(response.content)
    else:
        print(f"Failed to download {os.path.basename(output_path)}")

def process_grib_files(grib_dir, output_file):
    # Get a sorted list of GRIB files
    files = sorted([f for f in os.listdir(grib_dir)])

    for file in files:
        file_path = os.path.join(grib_dir, file)
        print(f"Processing {file_path}...")

        # Define the command and arguments
        command = [
            'wgrib2', file_path,
            '-match', 'COLMD',
            '-match', 'organic',
            '-append',
            '-grib_out', output_grib
        ]

        result = subprocess.run(command, capture_output=True, text=True)

        # Print the output
        print(result.stdout)

def read_grib_to_numpy(grib_file_path):
    # Open the GRIB file
    grbs = pygrib.open(grib_file_path)

    # Initialize an empty list to store data arrays
    data_list = []
    dates = []

    # Loop through each time step
    for grb in grbs:
        # Extract the data from the GRIB message
        data = grb.values
        date = grb.validDate

        # Rotate the data by 180 degrees
        data = np.roll(data, data.shape[1] // 2, axis=1)

        # Append the data array to the list
        data_list.append(data)
        dates.append(date)

    # Close the GRIB file
    grbs.close()

    # Convert the list of data arrays to a NumPy array
    data_array = np.array(data_list)

    return data_array, dates

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

def create_custom_classified_cmap(colormap_data):
    """
    Creates a custom classified colormap and normalizer from the provided colormap data.

    Parameters:
    - colormap_data (list of dict): A list of dictionaries where each dictionary contains
                                    "Color" (RGBA values) and "Upper Bound" (upper boundary value).

    Returns:
    - cmap (ListedColormap): A matplotlib ListedColormap object.
    - norm (BoundaryNorm): A matplotlib BoundaryNorm object.
    """
    # Extract the colors and boundaries
    colors = [entry["Color"] for entry in colormap_data]  # Use RGBA values
    bounds = [entry["Upper Bound"] for entry in colormap_data]

    # Normalize the colors (from 0-255 range to 0-1 range)
    norm_colors = [[c / 255 for c in color] for color in colors]

    # Create the colormap and the normalizer
    cmap = ListedColormap(norm_colors, name='custom_colormap')
    norm = BoundaryNorm(bounds, len(bounds) - 1)  # Correctly set the number of boundaries

    return cmap, norm

def plot_data_array(data_oc, custom_cmap, norm, basemap_path, overlay_path=None, date_str=None, image_extent=None, output_path='plot.png', border_color='#333333CC', coastline_color='#333333CC', linewidth=2):
    """
    Plots a 2D numpy array representing a specific variable at a single time step.

    :param data_oc: 2D numpy array with the organic carbon data to plot.
    :param custom_cmap: Custom colormap for plotting.
    :param norm: Normalization for the colormap.
    :param basemap_path: Path to the basemap image.
    :param overlay_path: Path to the overlay image (optional).
    :param date_str: Date string to be displayed on the plot (optional).
    :param image_extent: Geographic extent of the basemap image (west, east, south, north) (optional).
    :param output_path: Path to save the output image (default is 'plot.png').
    :param border_color: Color of political borders (default is '#333333CC').
    :param coastline_color: Color of coastlines (default is '#333333CC').
    :param linewidth: Line width for borders and coastlines (default is 2).
    """
    w = 4096
    h = 2048
    dpi = 96

    try:
        # Create figure and axis with Cartopy
        fig, ax = plt.subplots(figsize=(w/dpi, h/dpi), dpi=dpi, subplot_kw={'projection': ccrs.PlateCarree()})

        # Overlay the basemap image
        basemap_img = plt.imread(basemap_path)
        if image_extent:
            ax.imshow(basemap_img, origin='upper', extent=image_extent, transform=ccrs.PlateCarree(), alpha=1.0)
        else:
            ax.imshow(basemap_img, origin='upper', transform=ccrs.PlateCarree(), alpha=1.0)

        # Plot the shifted Organic Carbon GRIB data
        data_oc = np.ma.masked_invalid(data_oc)  # Mask NaN values if any
        ax.imshow(np.flipud(data_oc), transform=ccrs.PlateCarree(), cmap=custom_cmap, norm=norm, extent=[-180, 180, -90, 90], origin='lower', interpolation='bicubic', alpha=1.0)

        # Overlay the secondary image if provided
        if overlay_path:
            overlay_img = plt.imread(overlay_path)
            ax.imshow(overlay_img, origin='upper', extent=image_extent, transform=ccrs.PlateCarree(), alpha=0.5)  # Adjust alpha as needed

        # Add political borders
        ax.add_feature(cfeature.BORDERS, edgecolor=border_color, linewidth=linewidth)

        # Add coastlines
        ax.add_feature(cfeature.COASTLINE, edgecolor=coastline_color, linewidth=linewidth)

        # Add the date string to the bottom of the plot if provided
        if date_str:
            plt.text(0.01, 0.04, date_str, ha='left', va='center', transform=ax.transAxes, fontsize=60, color='white', bbox=dict(facecolor='white', alpha=0, edgecolor='none'))

        # Remove border and axis
        ax.set_global()
        ax.axis('off')
        fig.subplots_adjust(left=0, right=1, top=1, bottom=0)

        # Save the plot with the specified output path
        plt.savefig(output_path, bbox_inches='tight', pad_inches=0, dpi=dpi)

        # Close the figure
        plt.close(fig)

    except Exception as e:
        print(f"Error creating plot: {e}")

def plot_sos_data(data_oc, custom_cmap, norm, basemap_path, overlay_path=None, date_str=None, image_extent=None, output_path='plot.png', border_color='#333333CC', coastline_color='#333333CC', linewidth=2):
    """
    Plots a 2D numpy array representing a specific variable at a single time step.

    :param data_oc: 2D numpy array with the organic carbon data to plot.
    :param custom_cmap: Custom colormap for plotting.
    :param norm: Normalization for the colormap.
    :param basemap_path: Path to the basemap image.
    :param overlay_path: Path to the overlay image (optional).
    :param date_str: Date string to be displayed on the plot (optional).
    :param image_extent: Geographic extent of the basemap image (west, east, south, north) (optional).
    :param output_path: Path to save the output image (default is 'plot.png').
    :param border_color: Color of political borders (default is '#333333CC').
    :param coastline_color: Color of coastlines (default is '#333333CC').
    :param linewidth: Line width for borders and coastlines (default is 2).
    """
    w = 4096
    h = 2048
    dpi = 96

    try:
        # Create figure and axis with Cartopy
        fig, ax = plt.subplots(figsize=(w/dpi, h/dpi), dpi=dpi, subplot_kw={'projection': ccrs.PlateCarree()})

        # Overlay the basemap image
        basemap_img = plt.imread(basemap_path)
        if image_extent:
            ax.imshow(basemap_img, origin='upper', extent=image_extent, transform=ccrs.PlateCarree(), alpha=1.0)
        else:
            ax.imshow(basemap_img, origin='upper', transform=ccrs.PlateCarree(), alpha=1.0)

        # Plot the shifted Organic Carbon GRIB data
        data_oc = np.ma.masked_invalid(data_oc)  # Mask NaN values if any
        ax.imshow(np.flipud(data_oc), transform=ccrs.PlateCarree(), cmap=custom_cmap, norm=norm, extent=[-180, 180, -90, 90], origin='lower', interpolation='bicubic', alpha=1.0)

        # Overlay the secondary image if provided
        # if overlay_path:
        #    overlay_img = plt.imread(overlay_path)
        #    ax.imshow(overlay_img, origin='upper', extent=image_extent, transform=ccrs.PlateCarree(), alpha=0.5)  # Adjust alpha as needed

        # Add political borders
        ax.add_feature(cfeature.BORDERS, edgecolor=border_color, linewidth=linewidth)

        # Add coastlines
        ax.add_feature(cfeature.COASTLINE, edgecolor=coastline_color, linewidth=linewidth)

        # Add the date string to the bottom of the plot if provided
        # if date_str:
        #    plt.text(0.01, 0.04, date_str, ha='left', va='center', transform=ax.transAxes, fontsize=60, color='white', bbox=dict(facecolor='white', alpha=0, edgecolor='none'))

        # Remove border and axis
        ax.set_global()
        ax.axis('off')
        fig.subplots_adjust(left=0, right=1, top=1, bottom=0)

        # Save the plot with the specified output path
        plt.savefig(output_path, bbox_inches='tight', pad_inches=0, dpi=dpi)

        # Close the figure
        plt.close(fig)

    except Exception as e:
        print(f"Error creating plot: {e}")

def create_movie(input_dir, output_file, fps=2):
    """
    Create a movie from images in a directory.

    :param input_dir: Directory containing sorted images to compile into a movie.
    :param output_file: Path to the output movie file.
    :param fps: Frames per second for the movie.
    """
    # Sort files in the directory
    files = sorted(os.listdir(input_dir))
    if not files:
        print("No files found in the directory.")
        return

    try:
      # Use ffmpeg to compile the images into a movie
      (
          ffmpeg
          .input(f'{input_dir}/*.png', pattern_type='glob', framerate=fps)
          .output(output_file, pix_fmt='yuv420p')
          .run(overwrite_output=True)
      )
    except ffmpeg.Error as e:
      # Safely print stderr if it's not None
      if e.stderr:
          print("FFmpeg error:", e.stderr.decode())
      else:
          print("FFmpeg error occurred, but no stderr available to decode.")

def upload_to_s3(
    aws_access_key, aws_secret_key, aws_bucket_name, output_file
):
    """
    Update metadata based on the latest video and upload it to S3.

    Returns:
        bool: True if the operation was successful, False otherwise.
    """
    try:
        s3_manager = S3Manager(aws_access_key, aws_secret_key, aws_bucket_name)
        s3_manager.upload_file(output_file, "/rt-animations/smoke.mp4")

        return True
    except Exception as e:
        logging.error(f"S3 video upload failed: {e}")
        return False
        
"""# Main"""

# Set up and parse command-line arguments first
parser = setup_arg_parser()
args = parser.parse_args()

# Set logging level based on verbose argument immediately after parsing arguments
log_level = logging.DEBUG if args.verbose else logging.INFO
logging.basicConfig(
    level=log_level, format="%(asctime)s - %(levelname)s - %(message)s"
)

try:
    # Retrieve secrets from credentials file
    expected_keys = [
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
    ]
    credential_manager = initialize_credential_manager(expected_keys)

    args.aws_access_key = args.aws_access_key or credential_manager.get_credential(
        "AWS_ACCESS_KEY_ID"
    )
    args.aws_secret_key = args.aws_secret_key or credential_manager.get_credential(
        "AWS_SECRET_ACCESS_KEY"
    )

except KeyError as e:
    logging.error(f"Missing credential: {e}")
    sys.exit(1)


# Get today's date
today = datetime.today()

# Calculate yesterday's date
yesterday = today - timedelta(days=1)

# Format yesterday's date as YYYYMMDD
date_input = yesterday.strftime('%Y%m%d')

prefix = convert_to_yyjjj(date_input)

# Grab base map
url = 'https://s3.us-east-1.amazonaws.com/metadata.sosexplorer.gov/assets/eic-smoke-basemap.jpg'
r = requests.get(url)
with open(image_path, 'wb') as f:
    f.write(r.content)

# Grab overlay
url = 'https://s3.us-east-1.amazonaws.com/metadata.sosexplorer.gov/assets/eic-smoke-overlay.png'
r = requests.get(url)
with open(overlay_path, 'wb') as f:
    f.write(r.content)

# Access the sub-catalog
sub_catalog = TDSCatalog(sub_catalog_url)

# Retrieve and list the titles of each dataset available
logging.debug("Datasets available in the sub-catalog:")
for dataset in sub_catalog.datasets:
    logging.debug(dataset)

# Ensure the output directory exists
os.makedirs(grib_directory, exist_ok=True)

remove_all_files_in_directory(grib_directory)

# Iterate over each dataset in the catalog and download it
for dataset_name, dataset in sub_catalog.datasets.items():
    if 'HTTPServer' in dataset.access_urls and dataset_name.startswith(prefix):
        file_url = dataset.access_urls['HTTPServer']
        output_path = os.path.join(grib_directory, dataset_name)  # Construct the file path
        logging.debug(f"Downloading {dataset_name} from {file_url}")
        download_file(file_url, output_path)

# Process the GRIB files
process_grib_files(grib_directory, output_grib)
logging.info(f"Extraction and concatenation complete. Output file: {output_grib}")

organic_carbon_combined_data, associated_dates = read_grib_to_numpy(output_grib)

logging.debug(f"Combined organic carbon data shape: {organic_carbon_combined_data.shape}")
logging.debug("Associated Dates:", associated_dates)

# Temporally interpolating the data to every hour
#organic_carbon_interpolated_data = interpolate_time_steps(organic_carbon_combined_data)
#print(f"Original organic carbon shape: {organic_carbon_combined_data.shape}")
#print(f"Interpolated organic carbon shape: {organic_carbon_interpolated_data.shape}")

custom_cmap, norm = create_custom_classified_cmap(colormap_data)

# Ensure the output directory exists
os.makedirs(output_directory, exist_ok=True)

remove_all_files_in_directory(output_directory)

for i, (data_oc_slice, date) in enumerate(zip(organic_carbon_combined_data, associated_dates)):
    # Pad the time step index with leading zeros. Adjust the '03' to change the padding length as necessary.
    padded_index = str(i).zfill(3)

    # Subtract 4 hours
    edt_date = date - timedelta(hours=4)

    # Construct the output filename using the padded index and the date
    date_str = edt_date.strftime('%d %b %Y %H:%M EDT')
    output_filename = f"time_step_{padded_index}.png"
    output_path = os.path.join(output_directory, output_filename)

    try:
        # Assuming plot_data_array is defined to take data, lats, lons, and other plotting parameters...
        plot_data_array(data_oc_slice, custom_cmap, norm, image_path, overlay_path, date_str, image_extent, output_path)
        logging.info(f"Processed and saved: {output_path}")
    except Exception as e:
        logging.error(f"Failed to process time step {i}: {e}")
    finally:
        # Ensure that the current figure is closed to free up memory
        plt.close('all')  # Closes all figures

create_movie(output_directory, args.output_file, fps=5)

# Upload video to AWS S3
if not upload_to_s3(
    args.aws_access_key,
    args.aws_secret_key,
    args.s3_bucket,
    args.output_file
):
    sys.exit(1)

logging.info(f"{args.output_file} smoke animation updated on {args.s3_bucket}.")
sys.exit(0)