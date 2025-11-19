# SPDX-License-Identifier: Apache-2.0
from .animate_manager import AnimateManager
from .base import Renderer
from .basemap import add_basemap_cartopy, add_basemap_tile
from .colormap_manager import ColormapManager
from .contour_manager import ContourManager
from .heatmap_manager import HeatmapManager
from .interactive_manager import InteractiveManager
from .plot_manager import PlotManager
from .styles import (
    DEFAULT_CMAP,
    DEFAULT_EXTENT,
    FIGURE_DPI,
    MAP_STYLES,
    apply_matplotlib_style,
)
from .timeseries_manager import TimeSeriesManager
from .vector_field_manager import VectorFieldManager
from .vector_particles_manager import VectorParticlesManager

__all__ = [
    "Renderer",
    "ColormapManager",
    "PlotManager",
    "HeatmapManager",
    "ContourManager",
    "TimeSeriesManager",
    "VectorFieldManager",
    "AnimateManager",
    "VectorParticlesManager",
    "InteractiveManager",
    "add_basemap_cartopy",
    "add_basemap_tile",
    "DEFAULT_CMAP",
    "DEFAULT_EXTENT",
    "FIGURE_DPI",
    "MAP_STYLES",
    "apply_matplotlib_style",
    "register_cli",
]

from typing import Any

from .cli_register import register_cli as _register_cli


def register_cli(subparsers: Any) -> None:
    """Register visualization subcommands under a provided subparsers object."""
    _register_cli(subparsers)
