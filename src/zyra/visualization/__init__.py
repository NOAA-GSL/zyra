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
]

# ---- CLI registration ---------------------------------------------------------------

from typing import Any

from zyra.visualization.cli_animate import handle_animate
from zyra.visualization.cli_compose_video import handle_compose_video
from zyra.visualization.cli_contour import handle_contour
from zyra.visualization.cli_heatmap import handle_heatmap
from zyra.visualization.cli_interactive import handle_interactive
from zyra.visualization.cli_timeseries import handle_timeseries
from zyra.visualization.cli_vector import handle_vector


def register_cli(subparsers: Any) -> None:
    """Register visualization subcommands under a provided subparsers object.

    Adds: heatmap, contour, timeseries, vector, wind, animate, compose-video, interactive
    Reuses existing CLI handlers where possible to avoid duplication.
    """

    # Removed duplicate per-command handlers in favor of dedicated modules

    # heatmap
    p_hm = subparsers.add_parser("heatmap", help="Visualization: render 2D heatmap")
    p_hm.add_argument("--input", required=True, help="Path to .nc or .npy input")
    p_hm.add_argument("--var", help="Variable name for NetCDF inputs")
    p_hm.add_argument("--basemap", help="Path to background image")
    p_hm.add_argument(
        "--extent",
        nargs=4,
        type=float,
        default=[-180, 180, -90, 90],
        help="west east south north",
    )
    p_hm.add_argument(
        "--output",
        help="Output PNG path (required when using --input; for --inputs use --output-dir)",
    )
    p_hm.add_argument(
        "--inputs", nargs="+", help="Multiple input paths for batch rendering"
    )
    p_hm.add_argument(
        "--output-dir",
        dest="output_dir",
        help="Directory to write outputs for --inputs",
    )
    p_hm.add_argument("--width", type=int, default=1024)
    p_hm.add_argument("--height", type=int, default=512)
    p_hm.add_argument("--dpi", type=int, default=96)
    p_hm.add_argument("--cmap", default="YlOrBr")
    p_hm.add_argument("--colorbar", action="store_true")
    p_hm.add_argument("--label")
    p_hm.add_argument("--units")
    p_hm.add_argument(
        "--features", help="Comma-separated features: coastline,borders,gridlines"
    )
    p_hm.add_argument(
        "--xarray-engine",
        dest="xarray_engine",
        help="xarray engine for NetCDF inputs (e.g., netcdf4, h5netcdf, scipy)",
    )
    p_hm.add_argument(
        "--map-type",
        choices=["image", "tile"],
        default="image",
        help="Basemap type: image (default) or tile",
    )
    p_hm.add_argument(
        "--tile-source",
        help="Contextily tile source name or URL (when --map-type=tile)",
    )
    p_hm.add_argument(
        "--tile-zoom",
        dest="tile_zoom",
        type=int,
        default=3,
        help="Tile source zoom level",
    )
    p_hm.add_argument("--timestamp", help="Overlay timestamp string")
    p_hm.add_argument("--crs", help="Force input CRS (e.g., EPSG:3857)")
    p_hm.add_argument(
        "--reproject",
        action="store_true",
        help="Attempt reprojection to EPSG:4326 (limited support)",
    )
    p_hm.add_argument(
        "--timestamp-loc",
        dest="timestamp_loc",
        choices=["upper_left", "upper_right", "lower_left", "lower_right"],
        default="lower_right",
        help="Timestamp placement (axes-relative)",
    )
    # Feature negations
    p_hm.add_argument("--no-coastline", action="store_true")
    p_hm.add_argument("--no-borders", action="store_true")
    p_hm.add_argument("--no-gridlines", action="store_true")
    p_hm.set_defaults(func=handle_heatmap)

    # contour
    p_ct = subparsers.add_parser(
        "contour", help="Visualization: render contour/filled contours"
    )
    p_ct.add_argument("--input", help="Path to .nc or .npy input")
    p_ct.add_argument("--inputs", nargs="+", help="Multiple inputs for batch rendering")
    p_ct.add_argument(
        "--output-dir",
        dest="output_dir",
        help="Directory to write outputs for --inputs",
    )
    p_ct.add_argument("--var", help="Variable name for NetCDF inputs")
    p_ct.add_argument("--basemap", help="Path to background image")
    p_ct.add_argument(
        "--extent",
        nargs=4,
        type=float,
        default=[-180, 180, -90, 90],
        help="west east south north",
    )
    p_ct.add_argument(
        "--output",
        required=True,
        help="Output PNG path (required for single --input; when using --inputs, prefer --output-dir)",
    )
    p_ct.add_argument("--width", type=int, default=1024)
    p_ct.add_argument("--height", type=int, default=512)
    p_ct.add_argument("--dpi", type=int, default=96)
    p_ct.add_argument("--cmap", default="YlOrBr")
    p_ct.add_argument("--filled", action="store_true", help="Use filled contours")
    p_ct.add_argument("--levels", default=10, help="Count or comma-separated levels")
    p_ct.add_argument("--colorbar", action="store_true")
    p_ct.add_argument("--label")
    p_ct.add_argument("--units")
    p_ct.add_argument(
        "--features", help="Comma-separated features: coastline,borders,gridlines"
    )
    p_ct.add_argument(
        "--xarray-engine",
        dest="xarray_engine",
        help="xarray engine for NetCDF inputs (e.g., netcdf4, h5netcdf, scipy)",
    )
    p_ct.add_argument("--map-type", choices=["image", "tile"], default="image")
    p_ct.add_argument(
        "--tile-source", help="Contextily tile source (when --map-type=tile)"
    )
    p_ct.add_argument("--tile-zoom", dest="tile_zoom", type=int, default=3)
    p_ct.add_argument("--timestamp", help="Overlay timestamp string")
    p_ct.add_argument("--crs", help="Force input CRS (e.g., EPSG:3857)")
    p_ct.add_argument("--reproject", action="store_true")
    p_ct.add_argument(
        "--timestamp-loc",
        dest="timestamp_loc",
        choices=["upper_left", "upper_right", "lower_left", "lower_right"],
        default="lower_right",
        help="Timestamp placement (axes-relative)",
    )
    p_ct.add_argument("--no-coastline", action="store_true")
    p_ct.add_argument("--no-borders", action="store_true")
    p_ct.add_argument("--no-gridlines", action="store_true")
    p_ct.set_defaults(func=handle_contour)

    # timeseries
    p_ts = subparsers.add_parser(
        "timeseries", help="Visualization: render a time series from CSV or NetCDF"
    )
    p_ts.add_argument("--input", required=True, help="Path to .csv or .nc input")
    p_ts.add_argument("--x", help="CSV: X column name (e.g., time)")
    p_ts.add_argument("--y", help="CSV: Y column name (value)")
    p_ts.add_argument("--var", help="NetCDF: variable name to plot")
    p_ts.add_argument("--output", required=True, help="Output PNG path")
    p_ts.add_argument("--width", type=int, default=1024)
    p_ts.add_argument("--height", type=int, default=512)
    p_ts.add_argument("--dpi", type=int, default=96)
    p_ts.add_argument("--title")
    p_ts.add_argument("--xlabel")
    p_ts.add_argument("--ylabel")
    p_ts.add_argument(
        "--style", choices=["line", "marker", "line_marker"], default="line"
    )
    p_ts.set_defaults(func=handle_timeseries)

    # vector
    p_vector = subparsers.add_parser(
        "vector", help="Visualization: render vector fields (e.g., wind, currents)"
    )
    p_vector.add_argument(
        "--input", help="Path to .nc input (alternative to --u/--v .npy)"
    )
    p_vector.add_argument(
        "--inputs", nargs="+", help="Multiple inputs for batch rendering"
    )
    p_vector.add_argument(
        "--output-dir",
        dest="output_dir",
        help="Directory to write outputs for --inputs",
    )
    p_vector.add_argument("--uvar", help="NetCDF: U variable name")
    p_vector.add_argument("--vvar", help="NetCDF: V variable name")
    p_vector.add_argument("--u", help="Path to U .npy file (alternative input)")
    p_vector.add_argument("--v", help="Path to V .npy file (alternative input)")
    p_vector.add_argument("--basemap", help="Path to background image")
    p_vector.add_argument(
        "--extent",
        nargs=4,
        type=float,
        default=[-180, 180, -90, 90],
        help="west east south north",
    )
    p_vector.add_argument(
        "--output",
        required=True,
        help="Output PNG path (required for single --input/--u/--v; when using --inputs, prefer --output-dir)",
    )
    p_vector.add_argument("--width", type=int, default=1024)
    p_vector.add_argument("--height", type=int, default=512)
    p_vector.add_argument("--dpi", type=int, default=96)
    p_vector.add_argument(
        "--density", type=float, default=0.2, help="Arrow sampling density (0<d<=1)"
    )
    p_vector.add_argument(
        "--scale", type=float, help="Quiver scale controlling arrow length"
    )
    p_vector.add_argument("--color", default="#333333", help="Arrow color")
    p_vector.add_argument(
        "--features", help="Comma-separated features: coastline,borders,gridlines"
    )
    p_vector.add_argument(
        "--xarray-engine",
        dest="xarray_engine",
        help="xarray engine for NetCDF inputs (e.g., netcdf4, h5netcdf, scipy)",
    )
    p_vector.add_argument("--map-type", choices=["image", "tile"], default="image")
    p_vector.add_argument(
        "--tile-source", help="Contextily tile source (when --map-type=tile)"
    )
    p_vector.add_argument("--tile-zoom", dest="tile_zoom", type=int, default=3)
    p_vector.add_argument(
        "--streamlines",
        action="store_true",
        help="Render streamlines instead of quiver",
    )
    p_vector.add_argument("--crs", help="Force input CRS (e.g., EPSG:3857)")
    p_vector.add_argument("--reproject", action="store_true")
    p_vector.add_argument("--no-coastline", action="store_true")
    p_vector.add_argument("--no-borders", action="store_true")
    p_vector.add_argument("--no-gridlines", action="store_true")
    p_vector.set_defaults(func=handle_vector)

    # deprecated alias
    # Optional: drop legacy 'wind' alias entirely to reduce surface area

    # local wrapper: animate

    def _levels_arg(val):
        from argparse import ArgumentTypeError

        try:
            return int(val)
        except ValueError:
            try:
                return [float(x) for x in val.split(",") if x.strip()]
            except Exception as e:
                raise ArgumentTypeError(
                    "levels must be int or comma-separated floats"
                ) from e

    p_anim = subparsers.add_parser(
        "animate", help="Generate PNG frames from a time-varying dataset"
    )
    p_anim.add_argument(
        "--mode",
        choices=["heatmap", "contour", "vector", "particles"],
        default="heatmap",
    )
    p_anim.add_argument(
        "--input",
        help="Path to .nc 3D var or 3D .npy stack (for heatmap/contour/vector)",
    )
    p_anim.add_argument(
        "--inputs", nargs="+", help="Multiple inputs for batch animations"
    )
    p_anim.add_argument("--var", help="NetCDF variable name (heatmap/contour)")
    # Vector-specific inputs
    p_anim.add_argument(
        "--uvar", help="NetCDF: U variable name (vector/particles mode)"
    )
    p_anim.add_argument(
        "--vvar", help="NetCDF: V variable name (vector/particles mode)"
    )
    p_anim.add_argument("--u", help="Path to U .npy stack (vector/particles mode)")
    p_anim.add_argument("--v", help="Path to V .npy stack (vector/particles mode)")
    p_anim.add_argument("--output-dir", required=True, help="Directory to write frames")
    p_anim.add_argument("--manifest", help="Optional manifest output path (JSON)")
    p_anim.add_argument("--cmap", default="YlOrBr")
    p_anim.add_argument(
        "--levels",
        type=_levels_arg,
        default=10,
        help="Contour levels: count or comma-separated",
    )
    p_anim.add_argument("--vmin", type=float)
    p_anim.add_argument("--vmax", type=float)
    p_anim.add_argument("--basemap", help="Path to background image")
    p_anim.add_argument(
        "--extent",
        nargs=4,
        type=float,
        default=[-180, 180, -90, 90],
        help="west east south north",
    )
    p_anim.add_argument("--width", type=int, default=1024)
    p_anim.add_argument("--height", type=int, default=512)
    p_anim.add_argument("--dpi", type=int, default=96)
    p_anim.add_argument(
        "--density",
        type=float,
        default=0.2,
        help="Vector mode: arrow sampling density (0<d<=1)",
    )
    p_anim.add_argument(
        "--scale", type=float, help="Vector mode: quiver scale controlling arrow length"
    )
    p_anim.add_argument("--color", default="#333333", help="Vector/particles color")
    p_anim.add_argument(
        "--colorbar", action="store_true", help="Heatmap/contour: draw colorbar"
    )
    p_anim.add_argument("--label", help="Heatmap/contour colorbar label")
    p_anim.add_argument("--units", help="Heatmap/contour units for colorbar")
    p_anim.add_argument(
        "--show-timestamp",
        action="store_true",
        help="Overlay timestamps per frame if available",
    )
    p_anim.add_argument(
        "--timestamps-csv",
        dest="timestamps_csv",
        help="CSV with one timestamp per line (overrides auto)",
    )
    p_anim.add_argument(
        "--timestamp-loc",
        dest="timestamp_loc",
        choices=["upper_left", "upper_right", "lower_left", "lower_right"],
        default="lower_right",
        help="Timestamp placement (axes-relative)",
    )
    p_anim.add_argument("--features", help="Heatmap/contour: comma-separated features")
    p_anim.add_argument("--map-type", choices=["image", "tile"], default="image")
    p_anim.add_argument(
        "--tile-source", help="Contextily tile source (when --map-type=tile)"
    )
    p_anim.add_argument("--tile-zoom", dest="tile_zoom", type=int, default=3)
    p_anim.add_argument(
        "--xarray-engine",
        dest="xarray_engine",
        help="xarray engine for NetCDF inputs (e.g., netcdf4, h5netcdf, scipy)",
    )
    p_anim.add_argument("--no-coastline", action="store_true")
    p_anim.add_argument("--no-borders", action="store_true")
    p_anim.add_argument("--no-gridlines", action="store_true")
    # Particles-specific
    p_anim.add_argument(
        "--seed",
        choices=["grid", "random", "custom"],
        default="grid",
        help="Particles: seeding strategy",
    )
    p_anim.add_argument(
        "--particles",
        type=int,
        default=200,
        help="Particles: count for grid/random seeding",
    )
    p_anim.add_argument(
        "--custom-seed", dest="custom_seed", help="Particles: CSV with lon,lat columns"
    )
    p_anim.add_argument(
        "--dt", type=float, default=0.01, help="Particles: integration step"
    )
    p_anim.add_argument(
        "--steps-per-frame", type=int, default=1, help="Particles: substeps per frame"
    )
    p_anim.add_argument(
        "--size", type=float, default=0.5, help="Particles: marker size"
    )
    p_anim.add_argument(
        "--method",
        choices=["euler", "rk2", "midpoint"],
        default="euler",
        help="Particles: integrator",
    )
    p_anim.add_argument("--crs", help="Force input CRS for heatmap/contour/vector")
    p_anim.add_argument("--reproject", action="store_true")
    p_anim.add_argument(
        "--to-video",
        dest="to_video",
        help="Optional: compose frames to MP4 using ffmpeg (single or per-input when using --inputs)",
    )
    p_anim.add_argument(
        "--combine-to",
        dest="combine_to",
        help="Optional: compose per-input videos into a single MP4 grid",
    )
    p_anim.add_argument(
        "--grid-cols",
        dest="grid_cols",
        type=int,
        default=2,
        help="Grid columns for --combine-to (default 2)",
    )
    p_anim.add_argument(
        "--grid-mode",
        dest="grid_mode",
        choices=["grid", "hstack"],
        default="grid",
        help=(
            "Composition mode for --combine-to. 'grid' uses ffmpeg xstack (inputs must share the same width/height); "
            "if sizes differ, pre-scale inputs or use '--grid-mode hstack' to compose horizontally."
        ),
    )
    p_anim.add_argument(
        "--fps", type=int, default=30, help="Frames per second for video composition"
    )
    p_anim.set_defaults(func=handle_animate)

    # compose-video

    p_vid = subparsers.add_parser(
        "compose-video", help="Compose a directory of frames into MP4 (requires ffmpeg)"
    )
    p_vid.add_argument(
        "--frames", required=True, help="Directory containing frame_*.png files"
    )
    p_vid.add_argument("-o", "--output", required=True, help="Output MP4 path")
    p_vid.add_argument(
        "--basemap", help="Optional background image to overlay under frames"
    )
    p_vid.add_argument("--fps", type=int, default=30)
    p_vid.set_defaults(func=handle_compose_video)

    # interactive

    p_int = subparsers.add_parser(
        "interactive", help="Render interactive HTML (folium or plotly)"
    )
    p_int.add_argument("--input", required=True, help="Path to .npy/.nc/.csv input")
    p_int.add_argument("--var", help="NetCDF variable name (for .nc inputs)")
    p_int.add_argument(
        "--mode", choices=["heatmap", "contour", "points", "vector"], default="heatmap"
    )
    p_int.add_argument("--engine", choices=["folium", "plotly"], default="folium")
    p_int.add_argument("--output", required=True, help="Output HTML path")
    p_int.add_argument("--extent", nargs=4, type=float, default=[-180, 180, -90, 90])
    p_int.add_argument("--cmap", default="YlOrBr")
    p_int.add_argument(
        "--features",
        help="Heatmap/contour only: features (may be ignored depending on engine)",
    )
    p_int.add_argument("--no-coastline", action="store_true")
    p_int.add_argument("--no-borders", action="store_true")
    p_int.add_argument("--no-gridlines", action="store_true")
    p_int.add_argument("--colorbar", action="store_true")
    p_int.add_argument("--label")
    p_int.add_argument("--units")
    p_int.add_argument("--timestamp")
    p_int.add_argument(
        "--timestamp-loc",
        dest="timestamp_loc",
        choices=["upper_left", "upper_right", "lower_left", "lower_right"],
        default="lower_right",
    )
    # Engine-specific
    p_int.add_argument(
        "--tiles", help="Folium: tile layer name/URL", default="OpenStreetMap"
    )
    p_int.add_argument("--zoom", type=int, help="Folium: initial zoom")
    p_int.add_argument("--attribution", help="Folium: attribution for custom tiles/WMS")
    p_int.add_argument("--wms-url", dest="wms_url", help="Folium: WMS base URL")
    p_int.add_argument(
        "--wms-layers", dest="wms_layers", help="Folium: WMS layer names"
    )
    p_int.add_argument("--wms-format", dest="wms_format", default="image/png")
    p_int.add_argument("--wms-transparent", dest="wms_transparent", action="store_true")
    p_int.add_argument(
        "--layer-control",
        dest="layer_control",
        action="store_true",
        help="Add a layer control switcher",
    )
    p_int.add_argument("--width", type=int, help="Plotly: width")
    p_int.add_argument("--height", type=int, help="Plotly: height")
    p_int.add_argument("--crs", help="Force input CRS")
    p_int.add_argument("--reproject", action="store_true")
    # Points timedimension
    p_int.add_argument(
        "--time-column", help="CSV points: column containing ISO8601 time strings"
    )
    p_int.add_argument(
        "--period", default="P1D", help="TimeDimension period (e.g., P1D)"
    )
    p_int.add_argument(
        "--transition-ms",
        dest="transition_ms",
        type=int,
        default=200,
        help="TimeDimension transition time (ms)",
    )
    # Vector-specific (interactive)
    p_int.add_argument("--uvar", help="NetCDF: U variable name (vector mode)")
    p_int.add_argument("--vvar", help="NetCDF: V variable name (vector mode)")
    p_int.add_argument("--u", help="Path to U .npy array (vector mode)")
    p_int.add_argument("--v", help="Path to V .npy array (vector mode)")
    p_int.add_argument(
        "--density",
        type=float,
        default=0.2,
        help="Vector: arrow sampling density (0<d<=1)",
    )
    p_int.add_argument(
        "--scale", type=float, default=1.0, help="Vector: arrow length scale in degrees"
    )
    p_int.add_argument("--color", default="#333333", help="Vector: arrow/line color")
    p_int.add_argument(
        "--streamlines",
        action="store_true",
        help="Vector: render streamlines image overlay",
    )
    p_int.set_defaults(func=handle_interactive)
