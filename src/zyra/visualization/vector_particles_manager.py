"""Render particle advection frames over a vector field (U/V).

Supports NetCDF (time, lat, lon) variables or 3D NumPy stacks. Particles are
seeded on a grid, at random, or from a CSV and advected using Euler or RK2.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Optional, Sequence

from zyra.utils.geo_utils import detect_crs_from_path, warn_if_mismatch

from .base import Renderer
from .basemap import add_basemap_cartopy
from .styles import DEFAULT_EXTENT, FIGURE_DPI, MAP_STYLES, apply_matplotlib_style


@dataclass
class ParticleFrame:
    index: int
    path: str


class VectorParticlesManager(Renderer):
    def __init__(
        self,
        *,
        basemap: Optional[str] = None,
        extent: Optional[Sequence[float]] = None,
        color: str = "#333333",
        size: float = 0.5,
        method: str = "euler",
    ) -> None:
        self.basemap = basemap
        self.extent = list(extent) if extent is not None else list(DEFAULT_EXTENT)
        self.color = color
        self.size = size
        self.method = method
        self._manifest = {}

    def configure(self, **kwargs: Any) -> None:
        self.basemap = kwargs.get("basemap", self.basemap)
        self.extent = list(kwargs.get("extent", self.extent))
        self.color = kwargs.get("color", self.color)
        self.size = kwargs.get("size", self.size)
        self.method = kwargs.get("method", self.method)

    # Data handling
    def _load_stacks(
        self,
        *,
        input_path: Optional[str] = None,
        uvar: Optional[str] = None,
        vvar: Optional[str] = None,
        u_path: Optional[str] = None,
        v_path: Optional[str] = None,
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
            ds = xr.open_dataset(input_path)
            try:
                U = ds[uvar].values
                V = ds[vvar].values
            finally:
                ds.close()
            return U, V
        raise ValueError(
            "Provide either --u/--v .npy stacks or --input .nc with --uvar/--vvar"
        )

    # Seeding helpers
    def _seed_particles(self, seed: str, particles: int) -> tuple[Any, Any]:
        import numpy as np

        west, east, south, north = self.extent
        if seed == "grid":
            # Square grid close to requested count
            nx = int(max(2, round((particles) ** 0.5)))
            ny = nx
            xs = np.linspace(west, east, nx)
            ys = np.linspace(south, north, ny)
            X, Y = np.meshgrid(xs, ys)
            return X.ravel(), Y.ravel()
        elif seed == "random":
            X = np.random.uniform(west, east, size=particles)
            Y = np.random.uniform(south, north, size=particles)
            return X, Y
        else:
            raise ValueError(
                "custom seeding requires render(..., custom_seed=path_to_csv)"
            )

    def _seed_custom(self, csv_path: str) -> tuple[Any, Any]:
        import pandas as pd

        df = pd.read_csv(csv_path)
        if not {"lon", "lat"}.issubset(df.columns):
            raise ValueError("custom seed CSV must have columns 'lon' and 'lat'")
        return df["lon"].to_numpy(), df["lat"].to_numpy()

    # Velocity sampling (nearest neighbor for simplicity)
    def _sample_uv(self, U: Any, V: Any, lon: Any, lat: Any) -> tuple[Any, Any]:
        import numpy as np

        ny, nx = U.shape[-2], U.shape[-1]
        west, east, south, north = self.extent
        # Map lon/lat to fractional indices
        fx = (lon - west) / (east - west) * (nx - 1)
        fy = (lat - south) / (north - south) * (ny - 1)
        ix = np.clip(np.round(fx).astype(int), 0, nx - 1)
        iy = np.clip(np.round(fy).astype(int), 0, ny - 1)
        return U[iy, ix], V[iy, ix]

    def _step_euler(
        self, U: Any, V: Any, lon: Any, lat: Any, dt: float
    ) -> tuple[Any, Any]:
        u, v = self._sample_uv(U, V, lon, lat)
        return lon + u * dt, lat + v * dt

    def _step_rk2(
        self, U: Any, V: Any, lon: Any, lat: Any, dt: float
    ) -> tuple[Any, Any]:
        # Midpoint method
        u1, v1 = self._sample_uv(U, V, lon, lat)
        lon_mid = lon + 0.5 * dt * u1
        lat_mid = lat + 0.5 * dt * v1
        u2, v2 = self._sample_uv(U, V, lon_mid, lat_mid)
        return lon + dt * u2, lat + dt * v2

    def _wrap_clamp(self, lon: Any, lat: Any) -> tuple[Any, Any]:
        import numpy as np

        west, east, south, north = self.extent
        # Wrap lon at 180/-180 boundaries; assume world extent [-180, 180]
        span = east - west
        lon = ((lon - west) % span) + west
        lat = np.clip(lat, south, north)
        return lon, lat

    def render(self, data: Any = None, **kwargs: Any):
        # Rendering loop writes frames to disk and remembers a manifest
        # Inputs
        input_path = kwargs.get("input_path")
        uvar = kwargs.get("uvar")
        vvar = kwargs.get("vvar")
        u_kw = kwargs.get("u")
        v_kw = kwargs.get("v")
        seed = kwargs.get("seed", "grid")
        particles = int(kwargs.get("particles", 200))
        custom_seed = kwargs.get("custom_seed")
        dt = float(kwargs.get("dt", 0.01))
        steps_per_frame = int(kwargs.get("steps_per_frame", 1))
        method = kwargs.get("method", self.method)
        width = int(kwargs.get("width", 1024))
        height = int(kwargs.get("height", 512))
        dpi = int(kwargs.get("dpi", FIGURE_DPI))
        color = kwargs.get("color", self.color)
        size = float(kwargs.get("size", self.size))
        output_dir = Path(kwargs.get("output_dir", "."))
        filename_template = kwargs.get("filename_template", "frame_{index:04d}.png")

        import cartopy.crs as ccrs
        import matplotlib.pyplot as plt
        import numpy as np

        # CRS detection
        try:
            user_crs = kwargs.get("crs", None)
            reproject = bool(kwargs.get("reproject", False))
            in_path = (
                input_path
                or (u_kw if isinstance(u_kw, (str, bytes)) else None)
                or (v_kw if isinstance(v_kw, (str, bytes)) else None)
            )
            in_crs = user_crs or (detect_crs_from_path(in_path) if in_path else None)
            warn_if_mismatch(in_crs, reproject=reproject, context="particles")
        except Exception:
            pass

        # Load stacks or accept arrays directly
        if hasattr(u_kw, "ndim") and hasattr(v_kw, "ndim"):
            U = np.asarray(u_kw)
            V = np.asarray(v_kw)
            if U.ndim == 2 and V.ndim == 2:
                U = U[None, ...]
                V = V[None, ...]
        else:
            U, V = self._load_stacks(
                input_path=input_path,
                uvar=uvar,
                vvar=vvar,
                u_path=u_kw if isinstance(u_kw, (str, bytes)) else None,
                v_path=v_kw if isinstance(v_kw, (str, bytes)) else None,
            )
        U = np.asarray(U)
        V = np.asarray(V)
        if U.ndim == 2 and V.ndim == 2:
            U = U[None, ...]
            V = V[None, ...]
        if U.shape != V.shape or U.ndim != 3:
            raise ValueError("U/V must be 3D stacks [time, y, x] with matching shapes")
        T = U.shape[0]

        # Seed particles
        if seed == "custom":
            if not custom_seed:
                raise ValueError("Provide custom_seed path for seed='custom'")
            lon, lat = self._seed_custom(custom_seed)
        else:
            lon, lat = self._seed_particles(seed, particles)

        output_dir.mkdir(parents=True, exist_ok=True)
        frames: list[ParticleFrame] = []

        # Select integrator
        step_fn = (
            self._step_rk2
            if method.lower() in ("rk2", "midpoint")
            else self._step_euler
        )

        # Frame loop
        for i in range(T):
            # Integrate substeps within frame using current time slice
            for _ in range(max(1, steps_per_frame)):
                lon, lat = step_fn(U[i], V[i], lon, lat, dt)
                lon, lat = self._wrap_clamp(lon, lat)

            # Draw
            apply_matplotlib_style()
            fig, ax = plt.subplots(
                figsize=(width / dpi, height / dpi),
                dpi=dpi,
                subplot_kw={"projection": ccrs.PlateCarree()},
            )
            add_basemap_cartopy(
                ax,
                self.extent,
                image_path=self.basemap,
                features=MAP_STYLES.get("features"),
            )
            ax.scatter(
                lon,
                lat,
                s=size,
                c=color,
                transform=ccrs.PlateCarree(),
                alpha=0.9,
                linewidths=0,
            )
            ax.set_global()
            ax.axis("off")
            fig.subplots_adjust(left=0, right=1, top=1, bottom=0)

            fpath = output_dir / filename_template.format(index=i)
            fig.savefig(fpath, bbox_inches="tight", pad_inches=0)
            plt.close(fig)
            frames.append(ParticleFrame(index=i, path=str(fpath)))

        self._manifest = {
            "mode": "particles",
            "count": len(frames),
            "frames": [asdict(f) for f in frames],
            "params": {
                "seed": seed,
                "particles": particles,
                "dt": dt,
                "steps_per_frame": steps_per_frame,
                "method": method,
                "color": color,
                "size": size,
            },
        }
        return self._manifest

    def save(self, output_path: Optional[str] = None, *, as_buffer: bool = False):
        import json

        if not self._manifest:
            return None
        if as_buffer:
            bio = BytesIO()
            bio.write(json.dumps(self._manifest, indent=2).encode("utf-8"))
            bio.seek(0)
            return bio
        if output_path is None:
            # default manifest next to frames
            first = self._manifest.get("frames", [{}])[0].get("path")
            # Use current directory as explicit fallback when no frames exist
            base = Path(first).parent if first else Path(".")  # noqa: PTH201
            output_path = str(base / "manifest.json")
        Path(output_path).write_text(
            json.dumps(self._manifest, indent=2), encoding="utf-8"
        )
        return output_path
