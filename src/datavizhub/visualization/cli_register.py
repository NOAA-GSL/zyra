from __future__ import annotations

from typing import Any

# Import only lightweight CLI handler modules. Heavy managers are imported lazily
# within each handler, minimizing startup cost.
from .cli_animate import handle_animate
from .cli_compose_video import handle_compose_video
from .cli_contour import handle_contour
from .cli_heatmap import handle_heatmap
from .cli_interactive import handle_interactive
from .cli_timeseries import handle_timeseries
from .cli_vector import handle_vector


def register_cli(subparsers: Any) -> None:
    """Register visualization subcommands using lightweight CLI modules.

    This avoids importing the visualization package root (which pulls heavy
    plotting stacks) unless commands are actually invoked.
    """

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
    p_ts = subparsers.add_parser("timeseries", help="Visualization: time series plots")
    p_ts.add_argument("--input", required=True)
    p_ts.add_argument("--x")
    p_ts.add_argument("--y")
    p_ts.add_argument("--var")
    p_ts.add_argument("--output", required=True)
    p_ts.add_argument("--title")
    p_ts.add_argument("--xlabel")
    p_ts.add_argument("--ylabel")
    p_ts.add_argument("--style", default="line", choices=["line", "scatter"])
    p_ts.add_argument("--width", type=int, default=1024)
    p_ts.add_argument("--height", type=int, default=512)
    p_ts.add_argument("--dpi", type=int, default=96)
    p_ts.set_defaults(func=handle_timeseries)

    # vector
    p_vec = subparsers.add_parser(
        "vector", help="Visualization: vector/quiver/streamlines"
    )
    p_vec.add_argument("--input")
    p_vec.add_argument("--inputs", nargs="+")
    p_vec.add_argument("--output")
    p_vec.add_argument("--output-dir")
    p_vec.add_argument("--uvar")
    p_vec.add_argument("--vvar")
    p_vec.add_argument("--u")
    p_vec.add_argument("--v")
    p_vec.add_argument("--basemap")
    p_vec.add_argument("--extent", nargs=4, type=float, default=[-180, 180, -90, 90])
    p_vec.add_argument("--width", type=int, default=1024)
    p_vec.add_argument("--height", type=int, default=512)
    p_vec.add_argument("--dpi", type=int, default=96)
    p_vec.add_argument("--crs")
    p_vec.add_argument("--reproject", action="store_true")
    p_vec.add_argument("--map-type", choices=["image", "tile"], default="image")
    p_vec.add_argument("--tile-source")
    p_vec.add_argument("--tile-zoom", dest="tile_zoom", type=int, default=3)
    p_vec.add_argument("--density", type=float, default=0.2)
    p_vec.add_argument("--scale", type=float)
    p_vec.add_argument("--color", default="#333333")
    p_vec.add_argument("--streamlines", action="store_true")
    p_vec.add_argument("--features")
    p_vec.add_argument("--no-coastline", action="store_true")
    p_vec.add_argument("--no-borders", action="store_true")
    p_vec.add_argument("--no-gridlines", action="store_true")
    p_vec.set_defaults(func=handle_vector)

    # animate + compose-video
    p_anim = subparsers.add_parser(
        "animate", help="Visualization: frame generation + videos"
    )
    p_anim.add_argument("--input")
    p_anim.add_argument("--inputs", nargs="+")
    p_anim.add_argument("--output")
    p_anim.add_argument("--output-dir")
    p_anim.add_argument(
        "--mode",
        choices=["heatmap", "contour", "vector", "particles"],
        default="heatmap",
    )
    p_anim.add_argument("--var")
    p_anim.add_argument("--uvar")
    p_anim.add_argument("--vvar")
    p_anim.add_argument("--u")
    p_anim.add_argument("--v")
    p_anim.add_argument("--density", type=float, default=0.2)
    p_anim.add_argument("--scale")
    p_anim.add_argument("--color", default="#333333")
    p_anim.add_argument("--basemap")
    p_anim.add_argument("--extent", nargs=4, type=float, default=[-180, 180, -90, 90])
    p_anim.add_argument("--width", type=int, default=1024)
    p_anim.add_argument("--height", type=int, default=512)
    p_anim.add_argument("--dpi", type=int, default=96)
    p_anim.add_argument("--cmap", default="YlOrBr")
    p_anim.add_argument("--levels")
    p_anim.add_argument("--vmin")
    p_anim.add_argument("--vmax")
    p_anim.add_argument("--colorbar", action="store_true")
    p_anim.add_argument("--label")
    p_anim.add_argument("--units")
    p_anim.add_argument("--show-timestamp", action="store_true")
    p_anim.add_argument("--timestamps-csv")
    p_anim.add_argument(
        "--timestamp-loc",
        choices=["upper_left", "upper_right", "lower_left", "lower_right"],
        default="lower_right",
    )
    p_anim.add_argument("--map-type", choices=["image", "tile"], default="image")
    p_anim.add_argument("--tile-source")
    p_anim.add_argument("--tile-zoom", type=int, default=3)
    p_anim.add_argument("--xarray-engine")
    p_anim.add_argument("--crs")
    p_anim.add_argument("--reproject", action="store_true")
    p_anim.add_argument("--to-video")
    p_anim.add_argument("--fps", type=int, default=30)
    p_anim.add_argument(
        "--grid-mode", default="grid", choices=["grid", "hstack", "vstack"]
    )  # compose multiple videos
    p_anim.add_argument("--grid-cols", type=int, default=2)
    p_anim.add_argument("--combine-to")
    p_anim.add_argument("--seed", type=int, default=0)
    p_anim.add_argument("--particles", type=int, default=2000)
    p_anim.add_argument("--custom-seed", action="store_true")
    p_anim.add_argument("--dt", type=float, default=0.5)
    p_anim.add_argument("--steps-per-frame", type=int, default=1)
    p_anim.add_argument(
        "--method", default="RK4-SPH", choices=["RK4-SPH", "RK4-Grid"]
    )  # particles
    p_anim.set_defaults(func=handle_animate)

    p_cv = subparsers.add_parser(
        "compose-video", help="Compose videos from frame directories"
    )
    p_cv.add_argument("--frames", required=True, help="Frames directory")
    p_cv.add_argument("-o", "--output", required=True, help="Output MP4 path")
    p_cv.add_argument("--fps", type=int, default=30)
    p_cv.add_argument("--basemap")
    p_cv.set_defaults(func=handle_compose_video)

    # interactive
    p_int = subparsers.add_parser(
        "interactive", help="Interactive visualizations (HTML)"
    )
    p_int.add_argument("--input", required=True)
    p_int.add_argument("--var")
    p_int.add_argument(
        "--mode", default="heatmap", choices=["heatmap", "vector", "points"]
    )  # noqa: E501
    p_int.add_argument("--engine", default="plotly", choices=["plotly", "folium"])  # noqa: E501
    p_int.add_argument("--cmap", default="YlOrBr")
    p_int.add_argument("--colorbar", action="store_true")
    p_int.add_argument("--label")
    p_int.add_argument("--units")
    p_int.add_argument("--timestamp")
    p_int.add_argument("--timestamp-loc", default="lower_right")
    p_int.add_argument("--tiles", default="OpenStreetMap")
    p_int.add_argument("--zoom", type=int, default=3)
    p_int.add_argument("--extent", nargs=4, type=float, default=[-180, 180, -90, 90])
    p_int.add_argument("--width", type=int, default=1024)
    p_int.add_argument("--height", type=int, default=512)
    p_int.add_argument("--output", required=True)
    p_int.add_argument("--uvar")
    p_int.add_argument("--vvar")
    p_int.add_argument("--u")
    p_int.add_argument("--v")
    p_int.add_argument("--density", type=float, default=0.2)
    p_int.add_argument("--scale", type=float, default=1.0)
    p_int.add_argument("--color", default="#333333")
    p_int.add_argument("--streamlines", action="store_true")
    p_int.add_argument("--features")
    p_int.set_defaults(func=handle_interactive)
