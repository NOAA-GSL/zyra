"""Plot 2D arrays over basemaps using Cartopy + Matplotlib.

This module exposes :class:`PlotManager`, a renderer that composes a basemap
image and a 2D data array into a final plot. It supports optional coastlines,
borders, custom colormaps, and saving to file.
"""

import logging

from zyra.visualization.base import Renderer


class PlotManager(Renderer):
    """Render 2D data arrays over basemap images using Cartopy + Matplotlib.

    Visualization Type
    ------------------
    - Basemap overlay (JPEG/PNG) with a 2D data array on top.

    Parameters
    ----------
    basemap : str, optional
        Path to a basemap image.
    overlay : str, optional
        Path to an optional overlay image applied before drawing data.
    image_extent : list or tuple, optional
        Geographic extent of the basemap in PlateCarree (west, east, south, north).
    base_cmap : str, default="YlOrBr"
        Default colormap name used when a custom cmap is not provided.

    Examples
    --------
    Minimal usage::

        pm = PlotManager(basemap="/path/to/basemap.jpg")
        pm.configure(image_extent=[-180, 180, -90, 90])
        fig = pm.render(data)
        pm.save("./plot.png")
    """

    def __init__(
        self, basemap=None, overlay=None, image_extent=None, base_cmap="YlOrBr"
    ):
        if image_extent is None:
            image_extent = [-180, 180, -90, 90]
        self.basemap = basemap
        self.overlay = overlay
        self.image_extent = image_extent
        self.base_cmap = base_cmap
        self._fig = None
        self._ax = None

    # Renderer API
    def configure(self, **kwargs):
        """Update configuration (basemap, overlay, extent, base colormap).

        Parameters
        ----------
        basemap : str, optional
            Path to basemap image.
        overlay : str, optional
            Path to overlay image.
        image_extent : list or tuple, optional
            Geographic extent in PlateCarree (west, east, south, north).
        base_cmap : str, optional
            Default colormap name.
        """
        self.basemap = kwargs.get("basemap", self.basemap)
        self.overlay = kwargs.get("overlay", self.overlay)
        self.image_extent = kwargs.get("image_extent", self.image_extent)
        self.base_cmap = kwargs.get("base_cmap", self.base_cmap)

    def render(self, data, **kwargs):
        """Plot a single 2D array on the configured basemap.

        Parameters
        ----------
        data : numpy.ndarray
            2D array to plot.
        custom_cmap : Any, optional
            Colormap or name used for drawing the data layer.
        norm : Any, optional
            Normalizer for the colormap.
        vmin, vmax : float, optional
            Data range limits for colormap mapping.
        flip_data : bool, default=False
            If True, flip the array vertically before drawing.
        width, height : int, optional
            Output figure width and height in pixels (defaults 4096x2048).
        dpi : int, default=96
            Dots per inch for rendering.
        border_color, coastline_color : str, optional
            Colors for borders and coastlines.
        linewidth : float, optional
            Line width for borders/coastlines.

        Returns
        -------
        matplotlib.figure.Figure or None
            The created figure, or ``None`` on error.
        """
        try:
            width = int(kwargs.get("width", 4096))
            height = int(kwargs.get("height", 2048))
            dpi = int(kwargs.get("dpi", 96))
            custom_cmap = kwargs.get("custom_cmap", self.base_cmap)
            norm = kwargs.get("norm", None)
            vmin = kwargs.get("vmin", None)
            vmax = kwargs.get("vmax", None)
            flip_data = kwargs.get("flip_data", False)
            border_color = kwargs.get("border_color", None)
            coastline_color = kwargs.get("coastline_color", None)
            linewidth = kwargs.get("linewidth", None)

            # Lazy imports to avoid import-time heavy deps
            import cartopy.crs as ccrs
            import cartopy.feature as cfeature
            import matplotlib.pyplot as plt
            import numpy as np

            fig, ax = plt.subplots(
                figsize=(width / dpi, height / dpi),
                dpi=dpi,
                subplot_kw={"projection": ccrs.PlateCarree()},
            )
            self._fig, self._ax = fig, ax

            if self.basemap is not None:
                img = plt.imread(self.basemap)
                ax.imshow(
                    img,
                    origin="upper",
                    extent=self.image_extent,
                    transform=ccrs.PlateCarree(),
                )

            if flip_data:
                data = np.flipud(data)

            ax.imshow(
                data,
                transform=ccrs.PlateCarree(),
                cmap=custom_cmap,
                norm=norm,
                extent=self.image_extent,
                vmin=vmin,
                vmax=vmax,
                origin="lower",
                interpolation="bicubic",
            )

            if border_color and linewidth:
                ax.add_feature(
                    cfeature.BORDERS, edgecolor=border_color, linewidth=linewidth
                )
            if coastline_color and linewidth:
                ax.add_feature(
                    cfeature.COASTLINE, edgecolor=coastline_color, linewidth=linewidth
                )

            ax.set_global()
            ax.axis("off")
            fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
            return fig
        except Exception as e:
            logging.error(f"Error in plot: {e}")
            return None

    def save(self, output_path=None):
        """Save the most recently rendered figure to disk.

        Parameters
        ----------
        output_path : str, optional
            Destination path. Defaults to ``"plot.png"``.

        Returns
        -------
        str or None
            Output path on success; ``None`` if nothing to save.
        """
        if self._fig is None:
            return None
        if output_path is None:
            output_path = "plot.png"
        self._fig.savefig(output_path, bbox_inches="tight", pad_inches=0)
        return output_path

    # Compatibility helpers preserving prior API
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
        """Compatibility wrapper that calls :meth:`render` then :meth:`save`."""
        fig = self.render(
            data,
            custom_cmap=custom_cmap,
            width=width,
            height=height,
            dpi=dpi,
            flip_data=flip_data,
            border_color=border_color,
            coastline_color=coastline_color,
            linewidth=linewidth,
            vmin=vmin,
            vmax=vmax,
        )
        if fig is not None:
            self.save(output_path)

    @staticmethod
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
        """Static convenience for plotting using a one-off figure.

        Parameters
        ----------
        data_oc : numpy.ndarray
            Data array to plot (masked NaNs are handled).
        custom_cmap : Any
            Colormap for the data layer.
        norm : Any
            Normalization for colormap values.
        basemap_path : str
            Path to the basemap image file.
        overlay_path : str, optional
            Path to an overlay image (currently unused).
        date_str : str, optional
            Optional label for time annotation (currently unused).
        image_extent : list or tuple, optional
            Geographic extent in PlateCarree (west, east, south, north).
        output_path : str, default="plot.png"
            Destination file path.
        border_color, coastline_color : str, optional
            Colors for borders and coastlines.
        linewidth : float, default=2
            Line width for borders/coastlines.
        """
        # Lazy imports
        import cartopy.crs as ccrs
        import cartopy.feature as cfeature
        import matplotlib.pyplot as plt
        import numpy as np

        w = 4096
        h = 2048
        dpi = 96
        try:
            fig, ax = plt.subplots(
                figsize=(w / dpi, h / dpi),
                dpi=dpi,
                subplot_kw={"projection": ccrs.PlateCarree()},
            )
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
            data_oc = np.ma.masked_invalid(data_oc)
            ax.imshow(
                np.flipud(data_oc),
                transform=ccrs.PlateCarree(),
                cmap=custom_cmap,
                norm=norm,
                extent=image_extent,
                vmin=None,
                vmax=None,
                origin="upper",
                interpolation="bicubic",
            )
            if border_color and linewidth:
                ax.add_feature(
                    cfeature.BORDERS, edgecolor=border_color, linewidth=linewidth
                )
            if coastline_color and linewidth:
                ax.add_feature(
                    cfeature.COASTLINE, edgecolor=coastline_color, linewidth=linewidth
                )
            ax.set_global()
            ax.axis("off")
            fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
            plt.savefig(output_path, bbox_inches="tight", pad_inches=0, dpi=dpi)
        except Exception as e:
            logging.error(f"Error in plot: {e}")
