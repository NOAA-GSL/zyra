#!/usr/bin/env python
"""Generate tiny U/V stacks for vector and particle demos.

Creates small 3D arrays shaped [time, y, x] with a simple, recognizable
motion pattern and saves them as .npy and NetCDF files.

Usage (from repo root or samples/):
  - Default (uniform eastward flow):
      python samples/generate_uv_stacks.py
  - Rotation pattern, 5 timesteps, 10x10 grid into samples/:
      python samples/generate_uv_stacks.py --pattern rotation --t 5 --ny 10 --nx 10 --outdir samples
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np


def make_grid(ny: int, nx: int, extent=(-180.0, 180.0, -90.0, 90.0)):
    west, east, south, north = extent
    lons = np.linspace(west, east, nx)
    lats = np.linspace(south, north, ny)
    LON, LAT = np.meshgrid(lons, lats)
    return LON, LAT, lons, lats


def pattern_uniform(t: int, ny: int, nx: int, speed: float = 0.5):
    # Eastward flow of constant speed (degrees per step)
    U = np.ones((t, ny, nx), dtype=np.float32) * speed
    V = np.zeros((t, ny, nx), dtype=np.float32)
    return U, V


def pattern_rotation(t: int, ny: int, nx: int, omega: float = 0.5):
    # Solid-body rotation around the origin. Use normalized grid to keep magnitudes small.
    lons = np.linspace(-1.0, 1.0, nx)
    lats = np.linspace(-1.0, 1.0, ny)
    X, Y = np.meshgrid(lons, lats)
    U0 = -omega * Y  # dlon/dt
    V0 = omega * X  # dlat/dt
    U = np.repeat(U0[None, ...], t, axis=0).astype(np.float32)
    V = np.repeat(V0[None, ...], t, axis=0).astype(np.float32)
    return U, V


def write_npy(outdir: Path, U: np.ndarray, V: np.ndarray):
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "u_stack.npy").write_bytes(
        np.save.__wrapped__(None, U) if hasattr(np.save, "__wrapped__") else b""
    )
    np.save(outdir / "u_stack.npy", U)
    np.save(outdir / "v_stack.npy", V)


def write_netcdf(outdir: Path, U: np.ndarray, V: np.ndarray):
    try:
        import xarray as xr
    except Exception:
        return  # skip if xarray not available

    t, ny, nx = U.shape
    _, _, lons, lats = make_grid(ny, nx)
    ds = xr.Dataset(
        {
            "U": ("time", "lat", "lon", U.astype("float32")),
            "V": ("time", "lat", "lon", V.astype("float32")),
        },
        coords={
            "time": np.arange(t),
            "lat": lats.astype("float32"),
            "lon": lons.astype("float32"),
        },
        attrs={"title": "Sample U/V stacks"},
    )
    # Use scipy engine if netCDF4 not present (visualization extra includes scipy)
    ds.to_netcdf(outdir / "uv_stack.nc")


def main():
    p = argparse.ArgumentParser(description="Generate tiny U/V stacks for demos")
    p.add_argument("--pattern", choices=["uniform", "rotation"], default="uniform")
    p.add_argument("--t", type=int, default=5, help="Timesteps")
    p.add_argument("--ny", type=int, default=10)
    p.add_argument("--nx", type=int, default=10)
    p.add_argument("--outdir", default="samples")
    args = p.parse_args()

    if args.pattern == "uniform":
        U, V = pattern_uniform(args.t, args.ny, args.nx)
    else:
        U, V = pattern_rotation(args.t, args.ny, args.nx)

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    np.save(outdir / "u_stack.npy", U)
    np.save(outdir / "v_stack.npy", V)
    try:
        write_netcdf(outdir, U, V)
    except Exception:
        pass
    print(
        f"Wrote: {outdir/'u_stack.npy'}, {outdir/'v_stack.npy'} and uv_stack.nc (if supported)"
    )


if __name__ == "__main__":
    main()
