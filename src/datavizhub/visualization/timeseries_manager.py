"""Render time series from CSV or NetCDF as simple line charts."""

from __future__ import annotations

from io import BytesIO
from typing import Any, Optional

from .base import Renderer
from .styles import FIGURE_DPI, apply_matplotlib_style


class TimeSeriesManager(Renderer):
    """Render a time series chart from CSV or NetCDF inputs.

    Parameters
    ----------
    title : str, optional
        Figure title.
    xlabel, ylabel : str, optional
        Axis labels.
    style : str, default="line"
        One of {"line", "marker", "line_marker"}.
    """

    def __init__(
        self,
        *,
        title: Optional[str] = None,
        xlabel: Optional[str] = None,
        ylabel: Optional[str] = None,
        style: str = "line",
    ) -> None:
        self.title = title
        self.xlabel = xlabel
        self.ylabel = ylabel
        self.style = style
        self._fig = None

    # Renderer API
    def configure(self, **kwargs: Any) -> None:
        self.title = kwargs.get("title", self.title)
        self.xlabel = kwargs.get("xlabel", self.xlabel)
        self.ylabel = kwargs.get("ylabel", self.ylabel)
        self.style = kwargs.get("style", self.style)

    def _resolve_series(
        self,
        *,
        input_path: str,
        x: Optional[str] = None,
        y: Optional[str] = None,
        var: Optional[str] = None,
    ):
        if input_path.lower().endswith(".csv"):
            import pandas as pd

            df = pd.read_csv(input_path)
            if not x or not y:
                raise ValueError("CSV inputs require --x and --y column names")
            xs = df[x]
            ys = df[y]
            return xs, ys
        elif input_path.lower().endswith((".nc", ".nc4")):
            import xarray as xr

            if not var:
                raise ValueError("NetCDF inputs require --var for the data variable")
            ds = xr.open_dataset(input_path)
            try:
                da = ds[var]
                # Use 'time' coord when available, else the first coordinate
                if "time" in da.coords:
                    xs = da["time"].values
                else:
                    first_dim = list(da.coords)[0] if da.coords else da.dims[0]
                    xs = (
                        da[first_dim].values
                        if first_dim in da.coords
                        else range(da.shape[0])
                    )
                ys = da.values
            finally:
                ds.close()
            return xs, ys
        else:
            raise ValueError("Unsupported input file; use .csv or .nc for timeseries")

    def render(self, data: Any = None, **kwargs: Any):  # data unused for now
        width = int(kwargs.get("width", 1024))
        height = int(kwargs.get("height", 512))
        dpi = int(kwargs.get("dpi", FIGURE_DPI))
        input_path = kwargs.get("input_path")
        x = kwargs.get("x")
        y = kwargs.get("y")
        var = kwargs.get("var")
        style = kwargs.get("style", self.style)

        if not input_path:
            raise ValueError("input_path is required")

        xs, ys = self._resolve_series(input_path=input_path, x=x, y=y, var=var)

        apply_matplotlib_style()
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(width / dpi, height / dpi), dpi=dpi)
        if style == "marker":
            ax.plot(xs, ys, linestyle="", marker="o", markersize=3)
        elif style == "line_marker":
            ax.plot(xs, ys, linestyle="-", marker="o", markersize=3)
        else:
            ax.plot(xs, ys, linestyle="-")

        if self.title:
            ax.set_title(self.title)
        if self.xlabel:
            ax.set_xlabel(self.xlabel)
        if self.ylabel:
            ax.set_ylabel(self.ylabel)
        ax.grid(True, linestyle=":", alpha=0.5)
        fig.tight_layout()
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
            output_path = "timeseries.png"
        self._fig.savefig(output_path, bbox_inches="tight", pad_inches=0)
        return output_path
