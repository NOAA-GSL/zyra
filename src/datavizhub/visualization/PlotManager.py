import logging

import cartopy.crs as ccrs
import cartopy.feature as cfeature
import matplotlib.pyplot as plt
import numpy as np


class PlotManager:
    def __init__(self, basemap=None, overlay=None, image_extent=None, base_cmap="YlOrBr"):
        """
        Initializes the PlotManager with the path and extent of the basemap image and the default colormap.

        :param image_path: Path to the basemap image.
        :param image_extent: Geographic extent of the basemap image (west, east, south, north).
        :param base_cmap: Default base colormap name.
        """
        if image_extent is None:
            image_extent = [-180, 180, -90, 90]
        self.basemap = basemap
        self.overlay = overlay
        self.image_extent = image_extent
        self.base_cmap = base_cmap

    def sos_plot_data(
        self,
        data,
        custom_cmap,
        output_path="plot.png",
        width=4096,
        height=2048,
        dpi=96,
        flip_data=False,
        border_color=None,
        coastline_color=None,
        linewidth=None,
        vmin=None,
        vmax=None,
    ):
        """
        Plots a 2D numpy array representing a specific variable at a single time step.
        """
        try:
            # Create figure and axis with Cartopy
            fig, ax = plt.subplots(
                figsize=(width / dpi, height / dpi),
                dpi=dpi,
                subplot_kw={"projection": ccrs.PlateCarree()},
            )

            # Overlay the basemap image
            img = plt.imread(self.basemap)
            ax.imshow(
                img,
                origin="upper",
                extent=self.image_extent,
                transform=ccrs.PlateCarree(),
            )

            if flip_data:
                data = np.flipup(data)

            # Plot the data
            ax.imshow(
                data,
                transform=ccrs.PlateCarree(),
                cmap=custom_cmap,
                extent=self.image_extent,
                vmin=vmin,
                vmax=vmax,
                origin="lower",
                interpolation="bicubic",
            )

            if border_color and linewidth:
                # Add political borders and coastlines
                ax.add_feature(
                    cfeature.BORDERS, edgecolor=border_color, linewidth=linewidth
                )
            if coastline_color and linewidth:
                ax.add_feature(
                    cfeature.COASTLINE, edgecolor=coastline_color, linewidth=linewidth
                )

            # Remove border and axis
            ax.set_global()
            ax.axis("off")
            fig.subplots_adjust(left=0, right=1, top=1, bottom=0)

            # Save the plot with the specified output path
            plt.savefig(output_path, bbox_inches="tight", pad_inches=0, dpi=dpi)

        except Exception as e:
            logging.error(f"Error in plot: {e}")

    def plot_data_array(
        data_oc,
        custom_cmap,
        norm,
        basemap_path,
        overlay_path=None,
        date_str=None,
        image_extent=None,
        output_path="plot.png",
        border_color="#333333CC",
        coastline_color="#333333CC",
        linewidth=2,
    ):
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
            fig, ax = plt.subplots(
                figsize=(w / dpi, h / dpi),
                dpi=dpi,
                subplot_kw={"projection": ccrs.PlateCarree()},
            )

            # Overlay the basemap image
            basemap_img = plt.imread(basemap_path)
            if image_extent:
                ax.imshow(
                    basemap_img,
                    origin="upper",
                    extent=image_extent,
                    transform=ccrs.PlateCarree(),
                    alpha=1.0,
                )
            else:
                ax.imshow(
                    basemap_img, origin="upper", transform=ccrs.PlateCarree(), alpha=1.0
                )

            # Plot the shifted Organic Carbon GRIB data
            data_oc = np.ma.masked_invalid(data_oc)  # Mask NaN values if any
            ax.imshow(
                np.flipud(data_oc),
                transform=ccrs.PlateCarree(),
                cmap=custom_cmap,
                norm=norm,
                extent=[-180, 180, -90, 90],
                origin="lower",
                interpolation="bicubic",
                alpha=1.0,
            )

            # Overlay the secondary image if provided
            if overlay_path:
                overlay_img = plt.imread(overlay_path)
                ax.imshow(
                    overlay_img,
                    origin="upper",
                    extent=image_extent,
                    transform=ccrs.PlateCarree(),
                    alpha=0.5,
                )  # Adjust alpha as needed

            # Add political borders
            ax.add_feature(
                cfeature.BORDERS, edgecolor=border_color, linewidth=linewidth
            )

            # Add coastlines
            ax.add_feature(
                cfeature.COASTLINE, edgecolor=coastline_color, linewidth=linewidth
            )

            # Add the date string to the bottom of the plot if provided
            if date_str:
                plt.text(
                    0.01,
                    0.04,
                    date_str,
                    ha="left",
                    va="center",
                    transform=ax.transAxes,
                    fontsize=60,
                    color="white",
                    bbox=dict(facecolor="white", alpha=0, edgecolor="none"),
                )

            # Remove border and axis
            ax.set_global()
            ax.axis("off")
            fig.subplots_adjust(left=0, right=1, top=1, bottom=0)

            # Save the plot with the specified output path
            plt.savefig(output_path, bbox_inches="tight", pad_inches=0, dpi=dpi)

            # Close the figure
            plt.close(fig)

        except Exception as e:
            print(f"Error creating plot: {e}")
