"""Render contour or filled contour plots with optional basemap."""

from __future__ import annotations

from io import BytesIO
from typing import Any, Optional, Sequence

from zyra.utils.geo_utils import detect_crs_from_path, warn_if_mismatch

from .base import Renderer
from .basemap import add_basemap_cartopy, add_basemap_tile
from .styles import (
    DEFAULT_CMAP,
    DEFAULT_EXTENT,
    FIGURE_DPI,
    MAP_STYLES,
    apply_matplotlib_style,
    timestamp_anchor,
)


class ContourManager(Renderer):
    """Render contour or filled contours over a basemap.

    Parameters
    ----------
    basemap : str, optional
        Path to a background image drawn before contours.
    extent : sequence of float, optional
        Geographic extent [west, east, south, north] in PlateCarree.
    cmap : str or Colormap, default=DEFAULT_CMAP
        Colormap used for filled contours.
    filled : bool, default=True
        Whether to draw filled contours (``contourf``) or lines (``contour``).
    """

    def __init__(
        self,
        *,
        basemap: Optional[str] = None,
        extent: Optional[Sequence[float]] = None,
        cmap: Any = DEFAULT_CMAP,
        filled: bool = True,
    ) -> None:
        self.basemap = basemap
        self.extent = list(extent) if extent is not None else list(DEFAULT_EXTENT)
        self.cmap = cmap
        self.filled = filled
        self._fig = None

    # Renderer API
    def configure(self, **kwargs: Any) -> None:
        self.basemap = kwargs.get("basemap", self.basemap)
        self.extent = list(kwargs.get("extent", self.extent))
        self.cmap = kwargs.get("cmap", self.cmap)
        self.filled = bool(kwargs.get("filled", self.filled))

    def _resolve_data(
        self,
        data: Any = None,
        *,
        input_path: Optional[str] = None,
        var: Optional[str] = None,
        xarray_engine: Optional[str] = None,
    ):
        if data is not None:
            return data
        if input_path is None:
            raise ValueError("Either data or input_path must be provided")
        if input_path.lower().endswith((".nc", ".nc4")):
            import xarray as xr

            if not var:
                raise ValueError("var is required when reading from NetCDF")
            ds = (
                xr.open_dataset(input_path, engine=xarray_engine)
                if xarray_engine
                else xr.open_dataset(input_path)
            )
            try:
                arr = ds[var].values
            finally:
                ds.close()
            return arr
        elif input_path.lower().endswith(".npy"):
            import numpy as np

            return np.load(input_path)
        else:
            raise ValueError(
                "Unsupported input file; use .nc or .npy for this increment"
            )

    def render(self, data: Any = None, **kwargs: Any):
        width = int(kwargs.get("width", 1024))
        height = int(kwargs.get("height", 512))
        dpi = int(kwargs.get("dpi", FIGURE_DPI))
        levels = kwargs.get("levels", 10)
        cmap = kwargs.get("cmap", self.cmap)
        linewidths = kwargs.get("linewidths", 1.0)
        colors = kwargs.get("colors", None)
        alpha = kwargs.get("alpha", 1.0)
        features = kwargs.get("features", MAP_STYLES.get("features"))
        # Basemap type and tiles
        map_type = (kwargs.get("map_type") or "image").lower()
        tile_source = kwargs.get("tile_source", None)
        tile_zoom = int(kwargs.get("tile_zoom", 3))
        add_colorbar = bool(kwargs.get("colorbar", False))
        cbar_label = kwargs.get("label", None)
        cbar_units = kwargs.get("units", None)
        timestamp = kwargs.get("timestamp", None)
        timestamp_loc = kwargs.get("timestamp_loc", "lower_right")
        input_path = kwargs.get("input_path", None)
        var = kwargs.get("var", None)
        user_crs = kwargs.get("crs", None)
        reproject = bool(kwargs.get("reproject", False))

        arr = self._resolve_data(
            data,
            input_path=input_path,
            var=var,
            xarray_engine=kwargs.get("xarray_engine"),
        )

        # CRS detection
        data_transform = None
        try:
            from zyra.utils.geo_utils import to_cartopy_crs

            in_crs = user_crs or (
                detect_crs_from_path(input_path, var=var) if input_path else None
            )
            warn_if_mismatch(in_crs, reproject=reproject, context="contour")
            data_transform = to_cartopy_crs(in_crs)
        except Exception:
            pass

        # Lazy imports
        apply_matplotlib_style()
        import matplotlib.pyplot as plt
        import numpy as np

        try:
            import cartopy.crs as ccrs
        except Exception as e:  # pragma: no cover
            raise RuntimeError("Cartopy is required for ContourManager") from e

        fig, ax = plt.subplots(
            figsize=(width / dpi, height / dpi),
            dpi=dpi,
            subplot_kw={"projection": ccrs.PlateCarree()},
        )
        if map_type == "tile":
            add_basemap_tile(ax, self.extent, tile_source=tile_source, zoom=tile_zoom)
            add_basemap_cartopy(ax, self.extent, image_path=None, features=features)
        else:
            add_basemap_cartopy(
                ax,
                self.extent,
                image_path=self.basemap,
                features=features,
            )

        ny, nx = arr.shape[-2], arr.shape[-1]
        xs = np.linspace(self.extent[0], self.extent[1], nx)
        ys = np.linspace(self.extent[2], self.extent[3], ny)
        X, Y = np.meshgrid(xs, ys)

        if self.filled:
            cf = ax.contourf(
                X,
                Y,
                arr,
                levels=levels,
                cmap=cmap,
                alpha=alpha,
                transform=(data_transform or ccrs.PlateCarree()),
            )
        else:
            cf = ax.contour(
                X,
                Y,
                arr,
                levels=levels,
                colors=colors,
                linewidths=linewidths,
                alpha=alpha,
                transform=(data_transform or ccrs.PlateCarree()),
            )
        if add_colorbar:
            cbar = fig.colorbar(
                cf, ax=ax, orientation="vertical", fraction=0.025, pad=0.02
            )
            if cbar_label or cbar_units:
                label = cbar_label or ""
                if cbar_units:
                    label = f"{label} ({cbar_units})" if label else f"({cbar_units})"
                cbar.set_label(label)

        if timestamp:
            x, y, ha, va = timestamp_anchor(timestamp_loc)
            ax.text(
                x,
                y,
                str(timestamp),
                transform=ax.transAxes,
                ha=ha,
                va=va,
                color="#ffffff",
                fontsize=10,
                bbox=dict(
                    facecolor="#00000066", edgecolor="none", boxstyle="round,pad=0.2"
                ),
            )
        ax.set_global()
        ax.axis("off")
        fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
        self._fig = fig
        return fig

    def save(self, output_path: Optional[str] = None, *, as_buffer: bool = False):
        if self._fig is None:
            return None
        if as_buffer:
            bio = BytesIO()
            self._fig.savefig(bio, format="png", bbox_inches="tight", pad_inches=0)
            bio.seek(0)
            return bio
        if output_path is None:
            output_path = "contour.png"
        self._fig.savefig(output_path, bbox_inches="tight", pad_inches=0)
        return output_path
