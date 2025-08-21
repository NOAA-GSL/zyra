"""Generate animation frames (PNG sequence) for heatmap/contour modes.

This manager writes a numbered frame sequence and a small JSON manifest. It
does not invoke FFmpeg; composing video is left to downstream tools.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Sequence

from .base import Renderer
from .contour_manager import ContourManager
from .heatmap_manager import HeatmapManager
from .styles import DEFAULT_EXTENT, FIGURE_DPI
from .vector_field_manager import VectorFieldManager


@dataclass
class FrameInfo:
    index: int
    path: str
    timestamp: str | None = None


class AnimateManager(Renderer):
    """Create PNG frames for time-lapse heatmaps or contours.

    Parameters
    ----------
    mode : str, default="heatmap"
        One of {"heatmap", "contour", "vector"}.
    basemap : str, optional
        Background image to draw before data.
    extent : sequence of float, optional
        Geographic extent [west, east, south, north] in PlateCarree.
    output_dir : str, optional
        Directory to write frames and manifest (defaults to working dir if not set).
    filename_template : str, default="frame_{index:04d}.png"
        Template for frame filenames.
    """

    def __init__(
        self,
        *,
        mode: str = "heatmap",
        basemap: str | None = None,
        extent: Sequence[float] | None = None,
        output_dir: str | None = None,
        filename_template: str = "frame_{index:04d}.png",
    ) -> None:
        self.mode = mode
        self.basemap = basemap
        self.extent = list(extent) if extent is not None else list(DEFAULT_EXTENT)
        self.output_dir = Path(output_dir) if output_dir else None
        self.filename_template = filename_template
        self._manifest: dict[str, Any] = {}

    # Renderer API
    def configure(self, **kwargs: Any) -> None:
        self.mode = kwargs.get("mode", self.mode)
        self.basemap = kwargs.get("basemap", self.basemap)
        self.extent = list(kwargs.get("extent", self.extent))
        out = kwargs.get("output_dir", None)
        if out is not None:
            self.output_dir = Path(out)
        self.filename_template = kwargs.get("filename_template", self.filename_template)

    def _resolve_stack(
        self,
        data: Any = None,
        *,
        input_path: str | None = None,
        var: str | None = None,
        xarray_engine: str | None = None,
    ) -> tuple[Any, list[str | None]]:
        import numpy as np

        timestamps: list[str | None] = []
        if data is not None:
            arr = np.asarray(data)
            if arr.ndim != 3:
                raise ValueError("data must be a 3D array [time, y, x]")
            return arr, timestamps
        if input_path is None:
            raise ValueError("Either data or input_path must be provided")
        if input_path.lower().endswith(".npy"):
            arr = np.load(input_path)
            # Accept 2D arrays by promoting to a single-frame stack
            if arr.ndim == 2:
                arr = arr[None, ...]
            if arr.ndim != 3:
                raise ValueError(
                    ".npy stack must be 2D or 3D; 3D required as [time, y, x]"
                )
            return arr, timestamps
        if input_path.lower().endswith((".nc", ".nc4")):
            import xarray as xr

            if not var:
                raise ValueError("var is required for NetCDF inputs")
            ds = (
                xr.open_dataset(input_path, engine=xarray_engine)
                if xarray_engine
                else xr.open_dataset(input_path)
            )
            try:
                da = ds[var]
                if da.ndim < 3:
                    raise ValueError("NetCDF variable must be at least 3D with time")
                # Assume time is first non-spatial dimension
                time_coord = None
                for c in da.coords:
                    if c.lower() == "time":
                        time_coord = c
                        break
                if time_coord is not None:
                    ts = da[time_coord].values
                    timestamps = [str(t) for t in ts]
                arr = da.values
            finally:
                ds.close()
            # Squeeze to [t,y,x]
            arr = np.asarray(arr)
            if arr.ndim > 3:
                # Take first indices of extra dims
                while arr.ndim > 3:
                    arr = arr[0]
            if arr.ndim != 3:
                raise ValueError("Resolved array is not 3D after selection")
            return arr, timestamps
        raise ValueError("Unsupported input; use .npy or .nc for animation")

    def render(self, data: Any = None, **kwargs: Any):
        import matplotlib.pyplot as plt
        import numpy as np

        width = int(kwargs.get("width", 1024))
        height = int(kwargs.get("height", 512))
        dpi = int(kwargs.get("dpi", FIGURE_DPI))
        mode = kwargs.get("mode", self.mode)
        cmap = kwargs.get("cmap", "YlOrBr")
        levels = kwargs.get("levels", 10)
        vmin = kwargs.get("vmin", None)
        vmax = kwargs.get("vmax", None)
        add_colorbar = bool(kwargs.get("colorbar", False))
        cbar_label = kwargs.get("label", None)
        cbar_units = kwargs.get("units", None)
        show_timestamp = bool(kwargs.get("show_timestamp", False))
        timestamp_loc = kwargs.get("timestamp_loc", "lower_right")
        timestamps_csv = kwargs.get("timestamps_csv", None)
        input_path = kwargs.get("input_path", None)
        var = kwargs.get("var", None)
        # Basemap tiles for static frames
        map_type = (kwargs.get("map_type") or "image").lower()
        tile_source = kwargs.get("tile_source", None)
        tile_zoom = int(kwargs.get("tile_zoom", 3))
        # Vector-specific kwargs
        u_input = kwargs.get("u", None)
        v_input = kwargs.get("v", None)
        uvar = kwargs.get("uvar", None)
        vvar = kwargs.get("vvar", None)
        density = kwargs.get("density", 0.2)
        scale = kwargs.get("scale", None)
        color = kwargs.get("color", "#333333")
        output_dir = Path(kwargs.get("output_dir", self.output_dir or "."))
        user_crs = kwargs.get("crs", None)
        reproject = bool(kwargs.get("reproject", False))

        output_dir.mkdir(parents=True, exist_ok=True)
        frames: list[FrameInfo] = []
        if mode == "vector":
            import numpy as np

            # Resolve U/V stacks
            if u_input and v_input:
                U = np.load(u_input)
                V = np.load(v_input)
                if U.ndim != 3 or V.ndim != 3:
                    raise ValueError("U/V .npy stacks must be 3D [time, y, x]")
                if U.shape != V.shape:
                    raise ValueError("U and V stacks must have the same shape")
                t_count = U.shape[0]
                timestamps: list[str | None] = [None] * t_count
            elif input_path and (str(input_path).lower().endswith((".nc", ".nc4"))):
                import xarray as xr

                if not uvar or not vvar:
                    raise ValueError(
                        "--uvar and --vvar are required for NetCDF vector animation"
                    )
                ds = xr.open_dataset(input_path)
                try:
                    U = ds[uvar].values
                    V = ds[vvar].values
                    ts = None
                    for c in ds[uvar].coords:
                        if c.lower() == "time":
                            ts = ds[uvar][c].values
                            break
                    timestamps = [str(t) for t in ts] if ts is not None else []
                finally:
                    ds.close()
                U = np.asarray(U)
                V = np.asarray(V)
                if U.ndim == 2 and V.ndim == 2:
                    U = U[None, ...]
                    V = V[None, ...]
                if U.ndim != 3 or V.ndim != 3:
                    raise ValueError("U/V NetCDF variables must be 3D [time, y, x]")
                if U.shape != V.shape:
                    raise ValueError("U and V shapes must match")
                t_count = U.shape[0]
            else:
                raise ValueError(
                    "Provide --u/--v .npy stacks or --input .nc with --uvar/--vvar for vector mode"
                )

            for i in range(t_count):
                mgr = VectorFieldManager(
                    basemap=self.basemap,
                    extent=self.extent,
                )
                mgr.render(
                    u=U[i],
                    v=V[i],
                    width=width,
                    height=height,
                    dpi=dpi,
                    density=density,
                    scale=scale,
                    color=color,
                    map_type=map_type,
                    tile_source=tile_source,
                    tile_zoom=tile_zoom,
                )
                fname = self.filename_template.format(index=i)
                fpath = output_dir / fname
                mgr.save(str(fpath))
                plt.close("all")
                frames.append(
                    FrameInfo(
                        index=i,
                        path=str(fpath),
                        timestamp=(timestamps[i] if i < len(timestamps) else None),
                    )
                )
        else:
            stack, timestamps = self._resolve_stack(
                data,
                input_path=input_path,
                var=var,
                xarray_engine=kwargs.get("xarray_engine"),
            )
            # Allow external timestamps override via CSV (one per line)
            if timestamps_csv:
                try:
                    from pathlib import Path as _P

                    with _P(timestamps_csv).open(encoding="utf-8") as f:
                        timestamps = [line.strip() for line in f if line.strip()]
                except Exception:
                    pass
            # CRS detection/warn for grid stacks
            try:
                from zyra.utils.geo_utils import (
                    detect_crs_from_path,
                    warn_if_mismatch,
                )

                in_crs = user_crs or (
                    detect_crs_from_path(input_path) if input_path else None
                )
                warn_if_mismatch(in_crs, reproject=reproject, context="animate")
            except Exception:
                pass
            for i in range(stack.shape[0]):
                arr = stack[i]
                if mode == "contour":
                    mgr = ContourManager(
                        basemap=self.basemap, extent=self.extent, cmap=cmap, filled=True
                    )
                    mgr.render(
                        arr,
                        width=width,
                        height=height,
                        dpi=dpi,
                        levels=levels,
                        colorbar=add_colorbar,
                        label=cbar_label,
                        units=cbar_units,
                        timestamp=(
                            timestamps[i]
                            if (show_timestamp and i < len(timestamps))
                            else None
                        ),
                        timestamp_loc=timestamp_loc,
                        map_type=map_type,
                        tile_source=tile_source,
                        tile_zoom=tile_zoom,
                    )
                else:  # heatmap
                    mgr = HeatmapManager(
                        basemap=self.basemap, extent=self.extent, cmap=cmap
                    )
                    mgr.render(
                        arr,
                        width=width,
                        height=height,
                        dpi=dpi,
                        vmin=vmin,
                        vmax=vmax,
                        colorbar=add_colorbar,
                        label=cbar_label,
                        units=cbar_units,
                        timestamp=(
                            timestamps[i]
                            if (show_timestamp and i < len(timestamps))
                            else None
                        ),
                        timestamp_loc=timestamp_loc,
                        map_type=map_type,
                        tile_source=tile_source,
                        tile_zoom=tile_zoom,
                    )

                fname = self.filename_template.format(index=i)
                fpath = output_dir / fname
                mgr.save(str(fpath))
                plt.close("all")
                frames.append(
                    FrameInfo(
                        index=i,
                        path=str(fpath),
                        timestamp=timestamps[i] if i < len(timestamps) else None,
                    )
                )

        self._manifest = {
            "mode": mode,
            "count": len(frames),
            "frames": [asdict(f) for f in frames],
        }
        return self._manifest

    def save(self, output_path: str | None = None, *, as_buffer: bool = False):
        import json

        if not self._manifest:
            return None
        if as_buffer:
            bio = BytesIO()
            bio.write(json.dumps(self._manifest, indent=2).encode("utf-8"))
            bio.seek(0)
            return bio
        if output_path is None:
            # default alongside frames
            out_dir = (
                Path(self._manifest["frames"][0]["path"]).parent
                if self._manifest.get("frames")
                else Path()
            )
            output_path = str(Path(out_dir) / "manifest.json")
        Path(output_path).write_text(
            json.dumps(self._manifest, indent=2), encoding="utf-8"
        )
        return output_path
