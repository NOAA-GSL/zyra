"""Basemap helpers for Cartopy/Matplotlib renderers.

Functions here are intentionally lightweight and avoid hard dependencies
on optional tile providers. Tile support is stubbed and only enabled if
the dependency is available at runtime.
"""

from __future__ import annotations

from typing import Iterable, Optional


def add_basemap_cartopy(
    ax,
    extent: Optional[Iterable[float]] = None,
    *,
    image_path: Optional[str] = None,
    features: Optional[Iterable[str]] = None,
    alpha: float = 1.0,
):
    """Add a simple basemap to a Cartopy axis.

    Parameters
    ----------
    ax : cartopy.mpl.geoaxes.GeoAxesSubplot
        Target axes with a geographic projection (PlateCarree recommended).
    extent : iterable of float, optional
        [west, east, south, north] in PlateCarree coordinates.
    image_path : str, optional
        Path to a background image to draw via ``imshow``.
    features : iterable of str, optional
        Feature names to add: any of {"coastline", "borders", "gridlines"}.
    alpha : float, default=1.0
        Opacity for the background image.
    """
    # Lazy imports to avoid heavy deps at import-time
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature
    import matplotlib.pyplot as plt

    if extent is not None:
        try:
            ax.set_extent(extent, crs=ccrs.PlateCarree())
        except Exception:
            pass

    if image_path:
        try:
            img = plt.imread(image_path)
            ax.imshow(
                img,
                origin="upper",
                extent=extent or [-180, 180, -90, 90],
                transform=ccrs.PlateCarree(),
                alpha=alpha,
            )
        except Exception:
            # Swallow image read failures; caller may still draw data
            pass

    if features:
        for feat in features:
            f = (feat or "").lower()
            if f == "coastline":
                ax.add_feature(cfeature.COASTLINE, linewidth=0.5, edgecolor="#333333CC")
            elif f == "borders":
                ax.add_feature(cfeature.BORDERS, linewidth=0.5, edgecolor="#33333380")
            elif f == "gridlines":
                try:
                    gl = ax.gridlines(
                        draw_labels=False, linewidth=0.2, color="#00000033"
                    )
                    gl.xlocator = None  # let Cartopy choose
                    gl.ylocator = None
                except Exception:
                    pass


def add_basemap_tile(
    ax,
    extent: Optional[Iterable[float]] = None,
    *,
    tile_source: str | None = None,
    zoom: int = 3,
):
    """Add a tile basemap using contextily, if available.

    Notes
    -----
    - This is a best-effort helper. If ``contextily`` is not installed
      or tiles cannot be fetched (e.g., no network), the function returns
      without raising.
    - The axis is expected to use PlateCarree.
    """
    try:
        import cartopy.crs as ccrs
        import contextily as cx  # type: ignore
    except Exception:
        return  # graceful no-op

    if extent is not None:
        try:
            ax.set_extent(extent, crs=ccrs.PlateCarree())
        except Exception:
            pass

    try:
        # contextily expects Web Mercator typically; let it handle reprojection.
        # We draw into the Matplotlib axis backing the Cartopy GeoAxes.
        if tile_source is None:
            cx.add_basemap(ax, zoom=zoom)
        else:
            cx.add_basemap(ax, source=tile_source, zoom=zoom)
    except Exception:
        # Network or provider errors are ignored.
        return
