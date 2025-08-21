"""Interactive visualizations using Folium or Plotly.

This manager produces a standalone HTML document containing an interactive map
or figure. It supports lightweight overlays for gridded heatmaps/contours and
point layers from CSV. Optional engines are imported lazily.
"""

from __future__ import annotations

import base64
from io import BytesIO
from typing import Any, Optional, Sequence

from zyra.utils.geo_utils import (
    TARGET_CRS,
    detect_crs_from_csv,
    detect_crs_from_path,
    warn_if_mismatch,
)

from .base import Renderer
from .styles import DEFAULT_EXTENT, MAP_STYLES, timestamp_anchor


class InteractiveManager(Renderer):
    def __init__(
        self,
        *,
        engine: str = "folium",
        extent: Optional[Sequence[float]] = None,
        cmap: str = "YlOrBr",
    ) -> None:
        self.engine = engine
        self.extent = list(extent) if extent is not None else list(DEFAULT_EXTENT)
        self.cmap = cmap
        self._html: Optional[str] = None

    def configure(self, **kwargs: Any) -> None:
        self.engine = kwargs.get("engine", self.engine)
        self.extent = list(kwargs.get("extent", self.extent))
        self.cmap = kwargs.get("cmap", self.cmap)

    # --- Input helpers -----------------------------------------------------
    def _load_grid(
        self,
        *,
        input_path: str,
        var: Optional[str] = None,
        xarray_engine: Optional[str] = None,
    ):
        if input_path.lower().endswith((".nc", ".nc4")):
            import xarray as xr

            if not var:
                raise ValueError("--var is required for NetCDF inputs")
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
            raise ValueError("Unsupported grid input; use .nc or .npy")

    def _load_points(self, *, input_path: str):
        import pandas as pd

        df = pd.read_csv(input_path)
        if not {"lat", "lon"}.issubset(df.columns):
            raise ValueError("CSV points require 'lat' and 'lon' columns")
        return df

    def _load_vector(
        self,
        *,
        input_path: Optional[str] = None,
        uvar: Optional[str] = None,
        vvar: Optional[str] = None,
        u_path: Optional[str] = None,
        v_path: Optional[str] = None,
        xarray_engine: Optional[str] = None,
    ):
        import numpy as np

        if u_path and v_path:
            U = np.load(u_path)
            V = np.load(v_path)
        elif input_path and input_path.lower().endswith((".nc", ".nc4")):
            import xarray as xr

            if not uvar or not vvar:
                raise ValueError(
                    "--uvar and --vvar are required for NetCDF vector inputs"
                )
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
        else:
            raise ValueError(
                "Provide --u/--v .npy arrays or --input .nc with --uvar/--vvar"
            )
        U = np.asarray(U)
        V = np.asarray(V)
        if U.ndim == 3:
            U = U[0]
        if V.ndim == 3:
            V = V[0]
        if U.shape != V.shape:
            raise ValueError("U and V shapes must match")
        return U, V

    # --- Folium engine -----------------------------------------------------
    def _folium_heatmap(
        self,
        data,
        *,
        features,
        colorbar,
        label,
        units,
        timestamp,
        timestamp_loc,
        tiles,
        zoom,
        vmin=None,
        vmax=None,
        attribution=None,
        wms_url=None,
        wms_layers=None,
        wms_format="image/png",
        wms_transparent=True,
        layer_control=False,
        input_path=None,
        src_crs=None,
    ):
        import cartopy.crs as ccrs
        import folium
        import matplotlib.pyplot as plt
        from folium.raster_layers import ImageOverlay

        west, east, south, north = self.extent

        m = folium.Map(
            location=[(south + north) / 2, (west + east) / 2],
            zoom_start=zoom or 2,
            tiles=tiles or "OpenStreetMap",
        )

        # Render with Cartopy to allow transform-based reprojection
        fig = plt.figure(figsize=(6, 3))
        ax = plt.axes(projection=ccrs.PlateCarree())
        if not src_crs:
            from zyra.utils.geo_utils import detect_crs_from_path, to_cartopy_crs

            src_crs = to_cartopy_crs(
                detect_crs_from_path(input_path) if input_path else None
            )
        ax.set_extent([west, east, south, north], crs=ccrs.PlateCarree())
        ax.imshow(
            data,
            extent=[west, east, south, north],
            cmap=self.cmap,
            origin="lower",
            transform=(src_crs or ccrs.PlateCarree()),
        )
        ax.axis("off")
        bio = BytesIO()
        fig.savefig(bio, dpi=150, bbox_inches="tight", pad_inches=0)
        plt.close(fig)
        b64 = base64.b64encode(bio.getvalue()).decode("ascii")
        uri = f"data:image/png;base64,{b64}"
        ImageOverlay(
            image=uri, bounds=[[south, west], [north, east]], opacity=0.75
        ).add_to(m)

        # Timestamp overlay
        if timestamp:
            x, y, ha, va = timestamp_anchor(timestamp_loc)
            # simple top/bottom-right/left CSS placements
            pos = {
                ("left", "top"): "left:8px; top:8px;",
                ("right", "top"): "right:8px; top:8px;",
                ("left", "bottom"): "left:8px; bottom:8px;",
                ("right", "bottom"): "right:8px; bottom:8px;",
            }[(ha, va)]
            html = f"""
            <div style="position: absolute; {pos} z-index: 9999; background: rgba(0,0,0,0.5); color: #fff; padding: 2px 6px; border-radius: 4px; font-size: 12px;">
              {timestamp}
            </div>
            """
            m.get_root().html.add_child(folium.Element(html))

        # Colorbar (rendered from actual cmap)
        if colorbar:
            try:
                import matplotlib as mpl
                import numpy as np

                if vmin is None or vmax is None:
                    vmin = float(np.nanmin(data))
                    vmax = float(np.nanmax(data))
                cmap_obj = (
                    mpl.colormaps.get(self.cmap)
                    if isinstance(self.cmap, str)
                    else self.cmap
                )
                sm = mpl.cm.ScalarMappable(
                    cmap=cmap_obj, norm=mpl.colors.Normalize(vmin=vmin, vmax=vmax)
                )
                sm.set_array([])
                cfig, cax = plt.subplots(figsize=(3.0, 0.35))
                cbar = cfig.colorbar(sm, cax=cax, orientation="horizontal")
                title = (label or "") + (f" ({units})" if units else "")
                if title:
                    cax.set_xlabel(title)
                cfig.tight_layout()
                cbio = BytesIO()
                cfig.savefig(cbio, dpi=200, bbox_inches="tight", pad_inches=0.1)
                plt.close(cfig)
                cb64 = base64.b64encode(cbio.getvalue()).decode("ascii")
                cb_uri = f"data:image/png;base64,{cb64}"
                legend_html = f"""
                <div style="position: absolute; right: 8px; bottom: 8px; z-index: 9999; background: rgba(255,255,255,0.9); padding: 6px 8px; border-radius: 4px; font-size: 12px;">
                  <img src="{cb_uri}" style="display:block; max-width: 240px;">
                </div>
                """
                m.get_root().html.add_child(folium.Element(legend_html))
            except Exception:
                pass

        # Add optional base layers
        try:
            self._add_base_layers(
                m,
                tiles=tiles,
                attribution=attribution,
                wms_url=wms_url,
                wms_layers=wms_layers,
                wms_format=wms_format,
                wms_transparent=wms_transparent,
                add_control=layer_control,
            )
        except Exception:
            pass
        return m.get_root().render()

    def _folium_points(
        self,
        df,
        *,
        tiles,
        zoom,
        popup=None,
        tooltip=None,
        time_column: Optional[str] = None,
        period: str = "P1D",
        transition_ms: int = 200,
        attribution=None,
        wms_url=None,
        wms_layers=None,
        wms_format="image/png",
        wms_transparent=True,
        layer_control=False,
    ):
        import folium
        from folium.plugins import TimestampedGeoJson

        west, east, south, north = self.extent
        m = folium.Map(
            location=[(south + north) / 2, (west + east) / 2],
            zoom_start=zoom or 2,
            tiles=tiles or "OpenStreetMap",
        )
        if time_column and time_column in df.columns:
            # Build a simple GeoJSON with time properties
            features = []
            for _, row in df.iterrows():
                feat = {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [float(row["lon"]), float(row["lat"])],
                    },
                    "properties": {
                        "time": str(row[time_column]),
                        "popup": str(row.get(popup)) if popup and popup in row else "",
                        "tooltip": str(row.get(tooltip))
                        if tooltip and tooltip in row
                        else "",
                    },
                }
                features.append(feat)
            gj = {
                "type": "FeatureCollection",
                "features": features,
            }
            TimestampedGeoJson(
                gj,
                period=period,
                transition_time=transition_ms,
                add_last_point=True,
                auto_play=False,
                loop=False,
                duration="P0D",
            ).add_to(m)
        else:
            for _, row in df.iterrows():
                folium.CircleMarker(
                    location=[row["lat"], row["lon"]],
                    radius=4,
                    color="#2c7fb8",
                    fill=True,
                    fill_opacity=0.9,
                    popup=str(row.get(popup)) if popup and popup in row else None,
                    tooltip=str(row.get(tooltip))
                    if tooltip and tooltip in row
                    else None,
                ).add_to(m)
        try:
            self._add_base_layers(
                m,
                tiles=tiles,
                attribution=attribution,
                wms_url=wms_url,
                wms_layers=wms_layers,
                wms_format=wms_format,
                wms_transparent=wms_transparent,
                add_control=layer_control,
            )
        except Exception:
            pass
        return m.get_root().render()

    def _add_base_layers(
        self,
        m,
        *,
        tiles=None,
        attribution=None,
        wms_url=None,
        wms_layers=None,
        wms_format="image/png",
        wms_transparent=True,
        add_control=False,
    ):
        import folium

        # Tiles: custom URL or named tiles
        if tiles and ("{z}" in tiles or tiles.startswith("http")):
            folium.TileLayer(tiles=tiles, attr=attribution or "").add_to(m)
        # WMS layer
        if wms_url and wms_layers:
            folium.raster_layers.WmsTileLayer(
                url=wms_url,
                layers=wms_layers,
                fmt=wms_format,
                transparent=wms_transparent,
                attr=attribution or "",
            ).add_to(m)
        if add_control:
            folium.LayerControl().add_to(m)

    def _folium_vector_quiver(
        self,
        U,
        V,
        *,
        density=0.2,
        scale=1.0,
        color="#333333",
        tiles=None,
        zoom=None,
        attribution=None,
        wms_url=None,
        wms_layers=None,
        wms_format="image/png",
        wms_transparent=True,
        layer_control=False,
    ):
        import folium
        import numpy as np

        west, east, south, north = self.extent
        ny, nx = U.shape[-2], U.shape[-1]
        xs = np.linspace(west, east, nx)
        ys = np.linspace(south, north, ny)
        X, Y = np.meshgrid(xs, ys)

        # density -> stride
        density = 1.0 if density <= 0 else density
        stride = max(1, int(round(1.0 / min(1.0, density))))

        m = folium.Map(
            location=[(south + north) / 2, (west + east) / 2],
            zoom_start=zoom or 2,
            tiles=tiles or "OpenStreetMap",
        )
        for j in range(0, ny, stride):
            for i in range(0, nx, stride):
                x1 = float(X[j, i])
                y1 = float(Y[j, i])
                x2 = float(x1 + scale * U[j, i])
                y2 = float(y1 + scale * V[j, i])
                folium.PolyLine(
                    [[y1, x1], [y2, x2]], color=color, weight=1, opacity=0.8
                ).add_to(m)
        try:
            self._add_base_layers(
                m,
                tiles=tiles,
                attribution=attribution,
                wms_url=wms_url,
                wms_layers=wms_layers,
                wms_format=wms_format,
                wms_transparent=wms_transparent,
                add_control=layer_control,
            )
        except Exception:
            pass
        return m.get_root().render()

    def _folium_vector_streamlines(
        self,
        U,
        V,
        *,
        tiles=None,
        zoom=None,
        color="#333333",
        attribution=None,
        wms_url=None,
        wms_layers=None,
        wms_format="image/png",
        wms_transparent=True,
        layer_control=False,
    ):
        import cartopy.crs as ccrs
        import folium
        import matplotlib.pyplot as plt
        import numpy as np

        west, east, south, north = self.extent
        ny, nx = U.shape[-2], U.shape[-1]
        xs = np.linspace(west, east, nx)
        ys = np.linspace(south, north, ny)
        X, Y = np.meshgrid(xs, ys)

        fig = plt.figure(figsize=(6, 3))
        ax = plt.axes(projection=ccrs.PlateCarree())
        ax.set_extent([west, east, south, north], crs=ccrs.PlateCarree())
        ax.streamplot(X, Y, U, V, color=color, density=1.0, linewidth=0.6)
        ax.axis("off")
        bio = BytesIO()
        fig.savefig(bio, dpi=150, bbox_inches="tight", pad_inches=0)
        plt.close(fig)
        b64 = base64.b64encode(bio.getvalue()).decode("ascii")
        uri = f"data:image/png;base64,{b64}"

        m = folium.Map(
            location=[(south + north) / 2, (west + east) / 2],
            zoom_start=zoom or 2,
            tiles=tiles or "OpenStreetMap",
        )
        from folium.raster_layers import ImageOverlay

        ImageOverlay(
            image=uri, bounds=[[south, west], [north, east]], opacity=0.75
        ).add_to(m)
        try:
            self._add_base_layers(
                m,
                tiles=tiles,
                attribution=attribution,
                wms_url=wms_url,
                wms_layers=wms_layers,
                wms_format=wms_format,
                wms_transparent=wms_transparent,
                add_control=layer_control,
            )
        except Exception:
            pass
        return m.get_root().render()

    # --- Plotly engine -----------------------------------------------------
    def _plotly_heatmap(
        self, data, *, width, height, colorbar, label, units, timestamp
    ):
        import plotly.graph_objects as go

        fig = go.Figure(data=go.Heatmap(z=data, colorscale=self.cmap))
        if colorbar:
            title = (label or "") + (f" ({units})" if units else "")
            fig.update_layout(coloraxis_colorbar_title=title)
        if timestamp:
            fig.update_layout(title=str(timestamp))
        if width or height:
            fig.update_layout(width=width, height=height)
        return fig.to_html(full_html=True, include_plotlyjs="cdn")

    # --- Renderer API ------------------------------------------------------
    def render(self, data: Any = None, **kwargs: Any) -> Any:
        engine = (kwargs.get("engine") or self.engine or "folium").lower()
        mode = (kwargs.get("mode") or "heatmap").lower()
        input_path = kwargs.get("input_path") or kwargs.get("input")
        var = kwargs.get("var")
        features = kwargs.get("features") or MAP_STYLES.get("features")
        colorbar = bool(kwargs.get("colorbar", False))
        label = kwargs.get("label")
        units = kwargs.get("units")
        timestamp = kwargs.get("timestamp")
        timestamp_loc = kwargs.get("timestamp_loc", "lower_right")

        # Engine-specific pass-through
        tiles = kwargs.get("tiles")
        zoom = kwargs.get("zoom")
        width = kwargs.get("width")
        height = kwargs.get("height")

        html = ""
        if engine == "folium":
            if mode in ("heatmap", "contour"):
                arr = (
                    data
                    if data is not None
                    else self._load_grid(
                        input_path=input_path,
                        var=var,
                        xarray_engine=kwargs.get("xarray_engine"),
                    )
                )
                try:
                    in_crs = (
                        detect_crs_from_path(input_path) if input_path else TARGET_CRS
                    )
                    warn_if_mismatch(
                        in_crs,
                        reproject=bool(kwargs.get("reproject", False)),
                        context="interactive",
                    )
                except Exception:
                    pass
                html = self._folium_heatmap(
                    arr,
                    features=features,
                    colorbar=colorbar,
                    label=label,
                    units=units,
                    timestamp=timestamp,
                    timestamp_loc=timestamp_loc,
                    tiles=tiles,
                    zoom=zoom,
                    vmin=kwargs.get("vmin"),
                    vmax=kwargs.get("vmax"),
                    attribution=kwargs.get("attribution"),
                    wms_url=kwargs.get("wms_url"),
                    wms_layers=kwargs.get("wms_layers"),
                    wms_format=kwargs.get("wms_format", "image/png"),
                    wms_transparent=bool(kwargs.get("wms_transparent", True)),
                    layer_control=bool(kwargs.get("layer_control", False)),
                    input_path=input_path,
                )
                # Base layers are already handled in _folium_heatmap
                # (leftover block removed)
                try:
                    pass
                except Exception:
                    pass
            elif mode in ("points", "markers"):
                df = self._load_points(input_path=input_path)
                try:
                    in_crs = detect_crs_from_csv(df)
                    warn_if_mismatch(
                        in_crs,
                        reproject=bool(kwargs.get("reproject", False)),
                        context="interactive-points",
                    )
                except Exception:
                    pass
                html = self._folium_points(
                    df,
                    tiles=tiles,
                    zoom=zoom,
                    time_column=kwargs.get("time_column"),
                    period=kwargs.get("period", "P1D"),
                    transition_ms=int(kwargs.get("transition_ms", 200)),
                    attribution=kwargs.get("attribution"),
                    wms_url=kwargs.get("wms_url"),
                    wms_layers=kwargs.get("wms_layers"),
                    wms_format=kwargs.get("wms_format", "image/png"),
                    wms_transparent=bool(kwargs.get("wms_transparent", True)),
                    layer_control=bool(kwargs.get("layer_control", False)),
                )
            elif mode == "vector":
                U, V = self._load_vector(
                    input_path=input_path,
                    uvar=kwargs.get("uvar"),
                    vvar=kwargs.get("vvar"),
                    u_path=kwargs.get("u"),
                    v_path=kwargs.get("v"),
                    xarray_engine=kwargs.get("xarray_engine"),
                )
                if bool(kwargs.get("streamlines", False)):
                    html = self._folium_vector_streamlines(
                        U,
                        V,
                        tiles=tiles,
                        zoom=zoom,
                        color=kwargs.get("color", "#333333"),
                        attribution=kwargs.get("attribution"),
                        wms_url=kwargs.get("wms_url"),
                        wms_layers=kwargs.get("wms_layers"),
                        wms_format=kwargs.get("wms_format", "image/png"),
                        wms_transparent=bool(kwargs.get("wms_transparent", True)),
                        layer_control=bool(kwargs.get("layer_control", False)),
                    )
                else:
                    html = self._folium_vector_quiver(
                        U,
                        V,
                        density=kwargs.get("density", 0.2),
                        scale=kwargs.get("scale", 1.0),
                        color=kwargs.get("color", "#333333"),
                        tiles=tiles,
                        zoom=zoom,
                        attribution=kwargs.get("attribution"),
                        wms_url=kwargs.get("wms_url"),
                        wms_layers=kwargs.get("wms_layers"),
                        wms_format=kwargs.get("wms_format", "image/png"),
                        wms_transparent=bool(kwargs.get("wms_transparent", True)),
                        layer_control=bool(kwargs.get("layer_control", False)),
                    )
            else:
                raise ValueError(
                    "Unsupported folium interactive mode; use heatmap|contour|points"
                )
        elif engine == "plotly":
            if mode == "heatmap":
                arr = (
                    data
                    if data is not None
                    else self._load_grid(input_path=input_path, var=var)
                )
                html = self._plotly_heatmap(
                    arr,
                    width=width,
                    height=height,
                    colorbar=colorbar,
                    label=label,
                    units=units,
                    timestamp=timestamp,
                )
            else:
                raise ValueError("Unsupported plotly interactive mode; use heatmap")
        else:
            raise ValueError("Unknown engine; use 'folium' or 'plotly'")

        self._html = html
        return html

    def save(
        self, output_path: Optional[str] = None, *, as_buffer: bool = False
    ) -> Optional[str]:
        if not self._html:
            return None
        if as_buffer:
            return self._html
        if output_path is None:
            output_path = "interactive.html"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(self._html)
        return output_path
