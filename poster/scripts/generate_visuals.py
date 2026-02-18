# SPDX-License-Identifier: Apache-2.0
"""Generate poster-quality visualizations using Zyra's Python API.

Run from the repository root:
    poetry run python poster/scripts/generate_visuals.py

All inputs are in-repo sample data; no network access required.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from zyra.visualization import (
    ContourManager,
    HeatmapManager,
    TimeSeriesManager,
    VectorFieldManager,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SAMPLES = REPO_ROOT / "samples"
OUT_DIR = REPO_ROOT / "poster" / "assets" / "generated"

# Poster-quality render settings
DPI = 150
WIDTH = 600
HEIGHT = 300
EXTENT = [-180, 180, -90, 90]


def generate_heatmap() -> str:
    """Render a scalar heatmap from demo data."""
    arr = np.random.default_rng(42).random((10, 20)).astype("float32") * 20
    hm = HeatmapManager(extent=EXTENT)
    hm.render(
        arr,
        width=WIDTH,
        height=HEIGHT,
        dpi=DPI,
        colorbar=True,
        label="Value",
        units="K",
    )
    path = str(OUT_DIR / "heatmap.png")
    hm.save(path)
    print(f"  heatmap -> {path}")
    return path


def generate_contour() -> str:
    """Render filled contours from demo data."""
    arr = np.random.default_rng(42).random((10, 20)).astype("float32") * 20
    cm = ContourManager(extent=EXTENT, filled=True)
    cm.render(arr, width=WIDTH, height=HEIGHT, dpi=DPI, levels=10, colorbar=True)
    path = str(OUT_DIR / "contour.png")
    cm.save(path)
    print(f"  contour -> {path}")
    return path


def generate_vector() -> str:
    """Render a vector field (quiver) from sample U/V stacks."""
    u_path = SAMPLES / "u_stack.npy"
    v_path = SAMPLES / "v_stack.npy"
    if u_path.exists() and v_path.exists():
        u = np.load(u_path)[0]
        v = np.load(v_path)[0]
    else:
        # Fallback: generate synthetic wind vectors
        ny, nx = 10, 20
        u = np.ones((ny, nx), dtype="float32") * 0.5
        v = np.zeros((ny, nx), dtype="float32")
    vf = VectorFieldManager(extent=EXTENT, density=0.3)
    vf.render(u=u, v=v, width=WIDTH, height=HEIGHT, dpi=DPI)
    path = str(OUT_DIR / "vector.png")
    vf.save(path)
    print(f"  vector  -> {path}")
    return path


def generate_timeseries() -> str:
    """Render a time-series line chart from sample CSV."""
    csv_path = SAMPLES / "timeseries.csv"
    if not csv_path.exists():
        print("  timeseries: skipped (samples/timeseries.csv not found)")
        return ""
    ts = TimeSeriesManager(
        title="Sample Time Series", xlabel="Time Step", ylabel="Value"
    )
    ts.render(
        input_path=str(csv_path),
        x="time",
        y="value",
        width=WIDTH,
        height=HEIGHT,
        dpi=DPI,
    )
    path = str(OUT_DIR / "timeseries.png")
    ts.save(path)
    print(f"  timeseries -> {path}")
    return path


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("Generating poster visuals...")
    generate_heatmap()
    generate_contour()
    generate_vector()
    generate_timeseries()
    print("Done. All outputs in poster/assets/generated/")


if __name__ == "__main__":
    main()
