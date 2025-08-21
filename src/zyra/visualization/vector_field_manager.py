"""Render 2D vector fields (U/V) as quivers over an optional basemap.

Use for winds, ocean currents, or any horizontal vector field on a lon/lat grid.
"""

from __future__ import annotations

from io import BytesIO
from typing import Any, Optional, Sequence

from zyra.utils.geo_utils import detect_crs_from_path, warn_if_mismatch

from .base import Renderer
from .basemap import add_basemap_cartopy, add_basemap_tile
from .styles import DEFAULT_EXTENT, FIGURE_DPI, MAP_STYLES, apply_matplotlib_style


class VectorFieldManager(Renderer):
    """Render vector fields (U/V) as arrows over a basemap.

    Parameters
    ----------
    basemap : str, optional
        Path to a background image drawn before quivers.
    extent : sequence of float, optional
        Geographic extent [west, east, south, north] in PlateCarree.
    color : str, default="#333333"
        Arrow color.
    density : float, default=0.2
        Sampling density in (0, 1]; lower values draw fewer arrows.
    scale : float, optional
        Quiver scale parameter controlling arrow length relative to data.
    """

    def __init__(
        self,
        *,
        basemap: Optional[str] = None,
        extent: Optional[Sequence[float]] = None,
        color: str = "#333333",
        density: float = 0.2,
        scale: Optional[float] = None,
        streamlines: bool = False,
    ) -> None:
        self.basemap = basemap
        self.extent = list(extent) if extent is not None else list(DEFAULT_EXTENT)
        self.color = color
        self.density = float(density)
        self.scale = scale
        self.streamlines = streamlines
        self._fig = None

    # Renderer API
    def configure(self, **kwargs: Any) -> None:
        self.basemap = kwargs.get("basemap", self.basemap)
        self.extent = list(kwargs.get("extent", self.extent))
        self.color = kwargs.get("color", self.color)
        self.density = float(kwargs.get("density", self.density))
        self.scale = kwargs.get("scale", self.scale)
        self.streamlines = bool(kwargs.get("streamlines", self.streamlines))

    def _resolve_uv(
        self,
        *,
        input_path: Optional[str] = None,
        uvar: Optional[str] = None,
        vvar: Optional[str] = None,
        u_path: Optional[str] = None,
        v_path: Optional[str] = None,
        xarray_engine: Optional[str] = None,
    ) -> tuple[Any, Any]:
        import numpy as np

        if u_path and v_path:
            U = np.load(u_path)
            V = np.load(v_path)
            return U, V
        if input_path and input_path.lower().endswith((".nc", ".nc4")):
            import xarray as xr

            if not uvar or not vvar:
                raise ValueError("NetCDF inputs require --uvar and --vvar")
            ds = (
                xr.open_dataset(input_path, engine=xarray_engine)
                if xarray_engine
                else xr.open_dataset(input_path)
            )
            try:
                U = ds[uvar].values
                V = ds[vvar].values
            finally:
                ds.close()
            return U, V
        raise ValueError(
            "Provide either --u/--v .npy paths or --input .nc with --uvar/--vvar"
        )

    def render(self, data: Any = None, **kwargs: Any):  # data unused
        width = int(kwargs.get("width", 1024))
        height = int(kwargs.get("height", 512))
        dpi = int(kwargs.get("dpi", FIGURE_DPI))
        color = kwargs.get("color", self.color)
        density = float(kwargs.get("density", self.density))
        scale = kwargs.get("scale", self.scale)
        input_path = kwargs.get("input_path")
        uvar = kwargs.get("uvar")
        vvar = kwargs.get("vvar")
        u_path = kwargs.get("u")
        v_path = kwargs.get("v")

        import numpy as np

        apply_matplotlib_style()
        import matplotlib.pyplot as plt

        try:
            import cartopy.crs as ccrs
        except Exception as e:  # pragma: no cover
            raise RuntimeError("Cartopy is required for VectorFieldManager") from e

        # CRS warn and transform
        data_transform = None
        try:
            from zyra.utils.geo_utils import to_cartopy_crs

            user_crs = kwargs.get("crs", None)
            reproject = bool(kwargs.get("reproject", False))
            in_crs = user_crs or (
                detect_crs_from_path(input_path) if input_path else None
            )
            warn_if_mismatch(in_crs, reproject=reproject, context="vector")
            data_transform = to_cartopy_crs(in_crs)
        except Exception:
            pass

        # Accept either arrays (U/V) or file paths/NetCDF inputs
        U = kwargs.get("u")
        V = kwargs.get("v")
        if (
            U is None
            or V is None
            or isinstance(U, (str, bytes))
            or isinstance(V, (str, bytes))
        ):
            U, V = self._resolve_uv(
                input_path=input_path,
                uvar=uvar,
                vvar=vvar,
                u_path=(U if isinstance(U, (str, bytes)) else u_path),
                v_path=(V if isinstance(V, (str, bytes)) else v_path),
                xarray_engine=kwargs.get("xarray_engine"),
            )
        else:
            import numpy as np

            U = np.asarray(U)
            V = np.asarray(V)
        # If 3D stacks are provided to the static vector renderer, use first time slice
        if hasattr(U, "ndim") and hasattr(V, "ndim") and U.ndim == 3 and V.ndim == 3:
            U = U[0]
            V = V[0]
        ny, nx = U.shape[-2], U.shape[-1]
        xs = np.linspace(self.extent[0], self.extent[1], nx)
        ys = np.linspace(self.extent[2], self.extent[3], ny)
        X, Y = np.meshgrid(xs, ys)

        # Convert density -> stride
        density = 1.0 if density <= 0 else density
        stride = max(1, int(round(1.0 / min(1.0, density))))

        fig, ax = plt.subplots(
            figsize=(width / dpi, height / dpi),
            dpi=dpi,
            subplot_kw={"projection": ccrs.PlateCarree()},
        )
        # Features override support and tile basemap
        features = kwargs.get("features", MAP_STYLES.get("features"))
        map_type = (kwargs.get("map_type") or "image").lower()
        tile_source = kwargs.get("tile_source", None)
        tile_zoom = int(kwargs.get("tile_zoom", 3))
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

        if self.streamlines:
            # Use Matplotlib's streamplot on PlateCarree axes
            ax.streamplot(
                X,
                Y,
                U,
                V,
                color=color,
                density=max(0.3, min(2.0, self.density * 2.0)),
                linewidth=1.0,
                arrowsize=1.5,
            )
        else:
            ax.quiver(
                X[::stride, ::stride],
                Y[::stride, ::stride],
                U[::stride, ::stride],
                V[::stride, ::stride],
                color=color,
                scale=scale,
                transform=(data_transform or ccrs.PlateCarree()),
                linewidths=0.5,
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
            output_path = "vector.png"
        self._fig.savefig(output_path, bbox_inches="tight", pad_inches=0)
        return output_path
