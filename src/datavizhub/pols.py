import re
from pathlib import Path

import cartopy.crs as ccrs
import cartopy.feature as cfeature
import matplotlib

# import matplotlib.font_manager as font_manager
import matplotlib.pyplot as plt
import numpy as np
import xarray as xr
from cartopy.feature import NaturalEarthFeature
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.font_manager import FontProperties

# from scipy.ndimage import gaussian_filter
#polp = coarse pollen (ug/kg)
#Pols = fine pollen (ug/kg)
# Disable interactive mode
matplotlib.use("Agg")

# Constants for conversion
R = 287  # Gas constant for dry air, J/(kg·K)
rho_p = 1425  # Density of pollen, kg/m^3
radius_p_micrometers = 0.15  # Radius of pollen in micrometers
pi = np.pi

def convert_units(pols, T, P, PB):
    # Calculate the numerator and denominator
    numerator = pols * ((1 / R) * ((T + 300) / (P + PB))) * 1e9
    volume_pollen = (4/3) * pi * (radius_p_micrometers**3)
    mass_pollen = volume_pollen * rho_p
    denominator = mass_pollen

    return numerator / denominator

def extract_datetime_from_subtitle(filename):
    match = re.search(r"(\d{4}-\d{2}-\d{2})_(\d{2})_(\d{2})_(\d{2})", filename)
    if match:
        date, hour, minute, second = match.groups()
        return f"{date} {hour}:{minute} UTC"
    else:
        return "Date and time not found"


def extract_datetime_for_filename(filename):
    match = re.search(r"(\d{4}-\d{2}-\d{2})_(\d{2})_(\d{2})_(\d{2})", filename)
    if match:
        date, hour, minute, second = match.groups()
        return f"{date}_{hour}{minute}{second}"
    else:
        return "unknown_date_time"


def create_custom_cmap(
    base_cmap="viridis", transparent_range=1, blend_range=8, overall_alpha=1.0
):
    color_array = plt.get_cmap(base_cmap)(range(256))
    color_array[:transparent_range, -1] = 0
    color_array[transparent_range : transparent_range + blend_range, -1] = np.linspace(
        0.0, 1.0, blend_range
    )
    if overall_alpha < 1.0:
        color_array[:, -1] = color_array[:, -1] * overall_alpha
    return LinearSegmentedColormap.from_list("custom_cmap", colors=color_array)


# Directory containing the NetCDF files
directory = Path("/data/temp/pollen/")

# Define the projection
lambert_projection = ccrs.LambertConformal(
    central_longitude=-96, central_latitude=39, standard_parallels=(33, 45)
)

# Set non-interactive mode for matplotlib
plt.ioff()

# Directory containing NetCDF files
directory = Path("/data/temp/pollen/")
output_directory = directory / "images"
output_directory.mkdir(exist_ok=True)  # Ensure the output directory exists


# Process each file in the directory
for file_path in directory.glob("*.nc"):
    ds = xr.open_dataset(file_path)
    pols_data = ds["pols"]
    T = ds["T"]  # Assuming 'T' is the temperature variable
    P = ds["P"]  # Assuming 'P' is the pressure variable
    PB = ds["PB"]  # Assuming 'PB' is the base pressure variable

    # Convert units
    #pols_converted = convert_units(pols_data, T, P, PB)
    pols_converted = pols_data * ( (1/287) * ( (P+PB) / (T+300) ) )  * 1.e9 / ( 4./3. * 3.14 * 0.15**3 * 1425.)

    # Assuming you are working with a specific slice, like before
    pols_2d = pols_converted.isel(Time=0, bottom_top=0)
    xlong = ds.XLONG.isel(Time=0)
    xlat = ds.XLAT.isel(Time=0)

    subtitle = extract_datetime_from_subtitle(file_path.name)
    dynamic_filename_base = extract_datetime_for_filename(file_path.name)

    # Define custom font properties
    title_font = FontProperties(family="Lexend", size=20, weight="bold")
    subtitle_font = FontProperties(family="Lexend", size=20, weight="bold")
    label_font = FontProperties(family="Lexend", size=12)

    # Plotting setup
    fig, ax = plt.subplots(
        figsize=(12, 9), subplot_kw={"projection": ccrs.LambertConformal()}
    )
    ax.set_extent([-120, -70, 20, 60], crs=ccrs.PlateCarree())
    ax.add_feature(cfeature.LAND, facecolor="lightgray")
    ax.add_feature(cfeature.BORDERS, linewidth=1)
    ax.coastlines(resolution="10m")
    #ax.add_feature(cfeature.STATES, linestyle=":", edgecolor="black")

    # Add state borders using Natural Earth data
    states = NaturalEarthFeature(
        category="cultural",
        name="admin_1_states_provinces_lines",
        scale="50m",
        facecolor="none",
        edgecolor="gray",
    )
    ax.add_feature(states, linewidth=0.5)

    ax.gridlines(
        crs=ccrs.PlateCarree(),
        draw_labels=True,
        linewidth=1,
        color="gray",
        alpha=0.5,
        linestyle="--",
    )

    custom_cmap = create_custom_cmap()
    p = ax.pcolormesh(
        xlong,
        xlat,
        pols_2d,
        transform=ccrs.PlateCarree(),
        cmap=custom_cmap,
        edgecolors="none",
        vmin=0,
        vmax=300000
    )

    cbar = fig.colorbar(p, ax=ax, shrink=0.5, extend="max")
    cbar.set_label(r"$\text{grains/m}^{3}$", fontproperties=label_font)

    ax.set_title("Surface Sub-Pollen Forecast", fontproperties=title_font, pad=25)
    ax.text(
        0.5,
        1.01,
        subtitle,
        fontsize=12,
        color="gray",
        ha="center",
        va="bottom",
        transform=ax.transAxes,
        fontproperties=subtitle_font,
    )

    ax.set_xlabel("Longitude", fontproperties=label_font)
    ax.set_ylabel("Latitude", fontproperties=label_font)

    save_filename = f"surface_sub_pollen_forecast_{dynamic_filename_base}.png"
    plt.savefig(
        directory / "images" / save_filename,
        format="png",
        facecolor=fig.get_facecolor(),
        dpi=300,
        bbox_inches="tight",
        pad_inches=0.5,
        transparent=True,
    )
    print(f"Created {directory}/images/{save_filename}")
    plt.close(fig)

print("All files processed.")
