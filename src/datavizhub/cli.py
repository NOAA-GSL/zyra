import argparse
import sys
import re
from pathlib import Path
from typing import Optional, Tuple


def _parse_s3_url(url: str) -> Tuple[str, str]:
    m = re.match(r"^s3://([^/]+)/(.+)$", url)
    if not m:
        raise ValueError("Invalid s3 URL. Expected s3://bucket/key")
    return m.group(1), m.group(2)


def _read_bytes(path_or_url: str, *, idx_pattern: Optional[str] = None, unsigned: bool = False) -> bytes:
    # stdin
    if path_or_url == "-":
        return sys.stdin.buffer.read()

    p = Path(path_or_url)
    if p.exists():
        return p.read_bytes()

    # HTTP(S)
    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        try:
            from datavizhub.acquisition.http_manager import HTTPHandler

            http = HTTPHandler()
            if idx_pattern:
                lines = http.get_idx_lines(path_or_url)
                if lines:
                    ranges = http.idx_to_byteranges(lines, idx_pattern)
                    return http.download_byteranges(path_or_url, ranges.keys())
            # Fallback: full file
            import requests  # type: ignore

            r = requests.get(path_or_url, timeout=60)
            r.raise_for_status()
            return r.content
        except Exception as exc:  # pragma: no cover - optional dep
            raise SystemExit(f"Failed to fetch from URL: {exc}")

    # S3
    if path_or_url.startswith("s3://"):
        try:
            from datavizhub.acquisition.s3_manager import S3Manager

            bucket, key = _parse_s3_url(path_or_url)
            s3 = S3Manager(None, None, bucket_name=bucket, unsigned=unsigned)
            if idx_pattern:
                lines = s3.get_idx_lines(key)
                if lines:
                    ranges = s3.idx_to_byteranges(lines, idx_pattern)
                    return s3.download_byteranges(key, ranges.keys())
            # Fallback: full object using a single range
            size = s3.get_size(key)
            if size is None:
                raise SystemExit("Failed to determine S3 object size")
            rng = [f"bytes=0-{size}"]
            return s3.download_byteranges(key, rng)
        except Exception as exc:  # pragma: no cover - optional dep
            raise SystemExit(f"Failed to fetch from S3: {exc}")

    raise SystemExit(f"Input not found or unsupported scheme: {path_or_url}")


def cmd_decode_grib2(args: argparse.Namespace) -> int:
    from datavizhub.processing import grib_decode
    from datavizhub.processing.grib_utils import extract_metadata

    data = _read_bytes(args.file_or_url, idx_pattern=args.pattern, unsigned=args.unsigned)

    if getattr(args, "raw", False):
        # Emit the (optionally subsetted) raw GRIB2 bytes directly to stdout
        sys.stdout.buffer.write(data)
        return 0

    decoded = grib_decode(data, backend=args.backend)
    meta = extract_metadata(decoded)
    # Print variables and basic metadata
    print(meta)
    return 0


def cmd_extract_variable(args: argparse.Namespace) -> int:
    import os
    import shutil
    import subprocess
    import tempfile

    from datavizhub.processing import grib_decode
    from datavizhub.processing.grib_utils import (
        extract_variable,
        VariableNotFoundError,
        DecodedGRIB,
        convert_to_format,
    )

    data = _read_bytes(args.file_or_url)

    # If --stdout is requested, stream binary output of the selected variable
    if getattr(args, "stdout", False):
        out_fmt = (args.format or "netcdf").lower()
        if out_fmt not in ("netcdf", "grib2"):
            raise SystemExit("Unsupported --format for extract-variable: use 'netcdf' or 'grib2'")

        # Prefer wgrib2 for precise on-disk subsetting to GRIB2/NetCDF
        wgrib2 = shutil.which("wgrib2")
        if wgrib2 is not None:
            # Materialize input to a temp file for wgrib2
            fd, in_path = tempfile.mkstemp(suffix=".grib2")
            try:
                with os.fdopen(fd, "wb") as f:
                    f.write(data)
                suffix = ".grib2" if out_fmt == "grib2" else ".nc"
                out_tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
                out_path = out_tmp.name
                out_tmp.close()
                try:
                    args_list = [wgrib2, in_path, "-match", args.pattern]
                    if out_fmt == "grib2":
                        args_list += ["-grib", out_path]
                    else:
                        args_list += ["-netcdf", out_path]
                    res = subprocess.run(args_list, capture_output=True, text=True, check=False)
                    if res.returncode != 0:
                        # Gracefully fall back to Python conversion when wgrib2 lacks NetCDF support
                        print(res.stderr.strip() or "wgrib2 subsetting failed; falling back to Python conversion", file=sys.stderr)
                        # Do not return; continue to Python fallback below
                        # wgrib2 failed; will fall back to Python conversion after this block
                        print(res.stderr.strip() or "wgrib2 subsetting failed; falling back to Python conversion", file=sys.stderr)
                        # Continue to Python fallback below
                    else:
                        with open(out_path, "rb") as f:
                            sys.stdout.buffer.write(f.read())
                        return 0
                finally:
                    try:
                        os.remove(out_path)
                    except Exception:
                        pass
            finally:
                try:
                    os.remove(in_path)
                except Exception:
                    pass

        # Fallback: decode via Python and convert
        decoded = grib_decode(data, backend=args.backend)
        # For NetCDF, convert_to_format can handle DataArray/Dataset
        if out_fmt == "netcdf":
            out_bytes = convert_to_format(decoded, "netcdf", var=args.pattern)
            sys.stdout.buffer.write(out_bytes)
            return 0
        # For GRIB2 without wgrib2, try: extract -> to_netcdf -> external converter
        try:
            var_obj = extract_variable(decoded, args.pattern)
        except VariableNotFoundError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        # Export to NetCDF then convert to GRIB2 using NetCDF processor (may require CDO)
        try:
            import xarray as xr  # type: ignore
            from datavizhub.processing.netcdf_data_processor import convert_to_grib2

            ds = var_obj.to_dataset(name=getattr(var_obj, "name", "var")) if hasattr(var_obj, "to_dataset") else None
            if ds is None:
                print("Selected variable cannot be converted to GRIB2 without wgrib2", file=sys.stderr)
                return 2
            grib_bytes = convert_to_grib2(ds)
            sys.stdout.buffer.write(grib_bytes)
            return 0
        except Exception as exc:
            print(f"GRIB2 conversion failed: {exc}", file=sys.stderr)
            return 2

    # Default behavior: decode and summarize match
    decoded = grib_decode(data, backend=args.backend)
    try:
        var = extract_variable(decoded, args.pattern)
    except VariableNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    # Summarize output depending on backend/object type
    try:
        name = getattr(var, "name", None) or getattr(getattr(var, "attrs", {}), "get", lambda *_: None)("long_name")
    except Exception:
        name = None
    print(f"Matched variable: {name or args.pattern}")
    return 0


def cmd_convert_format(args: argparse.Namespace) -> int:
    """Convert decoded data to a requested format.

    Notes on NetCDF pass-through:
    - When the input stream is already NetCDF and the requested format is also
      NetCDF, and no variable selection ("--var") is provided, this command
      performs a byte-for-byte pass-through without decoding. This skips any
      validation of dataset contents.
    - If users expect validation or modification (e.g., selecting a variable
      or transforming coordinates), they must request a variable extraction or
      a conversion that decodes the data (e.g., specify "--var" or convert to
      another format).
    """
    from datavizhub.processing import grib_decode
    from datavizhub.processing.grib_utils import convert_to_format, DecodedGRIB

    if not args.output and not args.stdout:
        raise SystemExit("--output or --stdout is required for convert-format")

    data = _read_bytes(args.file_or_url, idx_pattern=args.pattern, unsigned=args.unsigned)

    # Fast-path: if input is already NetCDF and requested format is NetCDF with no var selection,
    # just pass bytes through. This avoids optional xarray dependency for a no-op conversion and
    # intentionally skips validation. Use --var or another conversion to force decoding/validation.
    if (
        args.format == "netcdf"
        and args.var is None
        and (data.startswith(b"\x89HDF\r\n\x1a\n") or data.startswith(b"CDF"))
    ):
        if args.stdout:
            sys.stdout.buffer.write(data)
        else:
            Path(args.output).write_bytes(data)
            print(f"Wrote {args.output}")
        return 0

    # Detect input type: GRIB2 vs NetCDF (classic CDF or HDF5-based NetCDF4)
    decoded = None
    try:
        if data.startswith(b"GRIB"):
            decoded = grib_decode(data, backend=args.backend)
        elif data.startswith(b"\x89HDF\r\n\x1a\n") or data.startswith(b"CDF"):
            # Load NetCDF and immediately convert within the context
            from datavizhub.processing.netcdf_data_processor import load_netcdf

            with load_netcdf(data) as ds:
                decoded = DecodedGRIB(backend="cfgrib", dataset=ds)  # reuse xarray-based conversions
                out_bytes = convert_to_format(decoded, args.format, var=args.var)
                if args.stdout:
                    sys.stdout.buffer.write(out_bytes)
                else:
                    Path(args.output).write_bytes(out_bytes)
                    print(f"Wrote {args.output}")
                return 0
        else:
            # Fallback: assume GRIB2 and try to decode
            decoded = grib_decode(data, backend=args.backend)
    except Exception as exc:
        raise SystemExit(f"Failed to open input: {exc}")

    out_bytes = convert_to_format(decoded, args.format, var=args.var)
    if args.stdout:
        sys.stdout.buffer.write(out_bytes)
    else:
        Path(args.output).write_bytes(out_bytes)
        print(f"Wrote {args.output}")
    return 0


def _viz_heatmap_cmd(ns: argparse.Namespace) -> int:
    # Local import to avoid importing visualization deps unless used
    from datavizhub.visualization.heatmap_manager import HeatmapManager

    mgr = HeatmapManager(basemap=ns.basemap, cmap=ns.cmap)
    mgr.configure(extent=ns.extent)
    # Build features list with negations
    features = None
    if getattr(ns, "features", None):
        features = [f.strip() for f in (ns.features.split(",")) if f.strip()]
    else:
        features = None
    if features is None:
        # use default from styles
        from datavizhub.visualization.styles import MAP_STYLES

        features = list(MAP_STYLES.get("features", []) or [])
    # Apply negations
    if getattr(ns, "no_coastline", False) and "coastline" in features:
        features = [f for f in features if f != "coastline"]
    if getattr(ns, "no_borders", False) and "borders" in features:
        features = [f for f in features if f != "borders"]
    if getattr(ns, "no_gridlines", False) and "gridlines" in features:
        features = [f for f in features if f != "gridlines"]
    mgr.render(
        input_path=ns.input,
        var=ns.var,
        width=ns.width,
        height=ns.height,
        dpi=ns.dpi,
        # CRS handling
        crs=getattr(ns, "crs", None),
        reproject=getattr(ns, "reproject", False),
        colorbar=getattr(ns, "colorbar", False),
        label=getattr(ns, "label", None),
        units=getattr(ns, "units", None),
        features=features,
        timestamp=getattr(ns, "timestamp", None),
        timestamp_loc=getattr(ns, "timestamp_loc", "lower_right"),
        map_type=getattr(ns, "map_type", "image"),
        tile_source=getattr(ns, "tile_source", None),
        tile_zoom=getattr(ns, "tile_zoom", 3),
    )
    out = mgr.save(ns.output)
    print(out or "")
    return 0


def _viz_contour_cmd(ns: argparse.Namespace) -> int:
    from datavizhub.visualization.contour_manager import ContourManager

    levels = ns.levels
    if not isinstance(levels, int):
        try:
            # If provided as a simple integer string (e.g., "5"), treat as count
            levels = int(str(levels))
        except Exception:
            try:
                # Otherwise, parse comma-separated explicit level values
                s = str(levels)
                levels = [float(x) for x in s.split(",") if x.strip()]
            except Exception:
                levels = 10

    mgr = ContourManager(basemap=ns.basemap, cmap=ns.cmap, filled=ns.filled)
    mgr.configure(extent=ns.extent)
    features = None
    if getattr(ns, "features", None):
        features = [f.strip() for f in (ns.features.split(",")) if f.strip()]
    else:
        features = None
    if features is None:
        from datavizhub.visualization.styles import MAP_STYLES

        features = list(MAP_STYLES.get("features", []) or [])
    if getattr(ns, "no_coastline", False) and "coastline" in features:
        features = [f for f in features if f != "coastline"]
    if getattr(ns, "no_borders", False) and "borders" in features:
        features = [f for f in features if f != "borders"]
    if getattr(ns, "no_gridlines", False) and "gridlines" in features:
        features = [f for f in features if f != "gridlines"]
    mgr.render(
        input_path=ns.input,
        var=ns.var,
        width=ns.width,
        height=ns.height,
        dpi=ns.dpi,
        levels=levels,
        # CRS handling
        crs=getattr(ns, "crs", None),
        reproject=getattr(ns, "reproject", False),
        colorbar=getattr(ns, "colorbar", False),
        label=getattr(ns, "label", None),
        units=getattr(ns, "units", None),
        features=features,
        timestamp=getattr(ns, "timestamp", None),
        timestamp_loc=getattr(ns, "timestamp_loc", "lower_right"),
        map_type=getattr(ns, "map_type", "image"),
        tile_source=getattr(ns, "tile_source", None),
        tile_zoom=getattr(ns, "tile_zoom", 3),
    )
    out = mgr.save(ns.output)
    print(out or "")
    return 0


def _viz_timeseries_cmd(ns: argparse.Namespace) -> int:
    from datavizhub.visualization.timeseries_manager import TimeSeriesManager

    mgr = TimeSeriesManager(title=ns.title, xlabel=ns.xlabel, ylabel=ns.ylabel, style=ns.style)
    mgr.render(
        input_path=ns.input,
        x=ns.x,
        y=ns.y,
        var=ns.var,
        width=ns.width,
        height=ns.height,
        dpi=ns.dpi,
    )
    out = mgr.save(ns.output)
    print(out or "")
    return 0


def _viz_vector_cmd(ns: argparse.Namespace) -> int:
    from datavizhub.visualization.vector_field_manager import VectorFieldManager

    mgr = VectorFieldManager(basemap=ns.basemap, color=ns.color, density=ns.density, scale=ns.scale, streamlines=getattr(ns, "streamlines", False))
    mgr.configure(extent=ns.extent)
    features = None
    if getattr(ns, "features", None):
        features = [f.strip() for f in (ns.features.split(",")) if f.strip()]
    else:
        features = None
    if features is None:
        from datavizhub.visualization.styles import MAP_STYLES

        features = list(MAP_STYLES.get("features", []) or [])
    if getattr(ns, "no_coastline", False) and "coastline" in features:
        features = [f for f in features if f != "coastline"]
    if getattr(ns, "no_borders", False) and "borders" in features:
        features = [f for f in features if f != "borders"]
    if getattr(ns, "no_gridlines", False) and "gridlines" in features:
        features = [f for f in features if f != "gridlines"]
    mgr.render(
        input_path=ns.input,
        uvar=ns.uvar,
        vvar=ns.vvar,
        u=ns.u,
        v=ns.v,
        width=ns.width,
        height=ns.height,
        dpi=ns.dpi,
        # CRS handling
        crs=getattr(ns, "crs", None),
        reproject=getattr(ns, "reproject", False),
        features=features,
        map_type=getattr(ns, "map_type", "image"),
        tile_source=getattr(ns, "tile_source", None),
        tile_zoom=getattr(ns, "tile_zoom", 3),
    )
    out = mgr.save(ns.output)
    print(out or "")
    return 0


def _viz_wind_cmd(ns: argparse.Namespace) -> int:
    # Back-compat alias for vector
    import sys

    print("[deprecated] 'wind' is deprecated; use 'vector' instead", file=sys.stderr)
    return _viz_vector_cmd(ns)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="datavizhub")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_dec = sub.add_parser("decode-grib2", help="Decode GRIB2 and print metadata")
    p_dec.add_argument("file_or_url")
    p_dec.add_argument("--backend", default="cfgrib", choices=["cfgrib", "pygrib", "wgrib2"])
    p_dec.add_argument("--pattern", help="Regex for .idx-based subsetting when using HTTP/S3")
    p_dec.add_argument("--unsigned", action="store_true", help="Use unsigned S3 access for public buckets")
    p_dec.add_argument("--raw", action="store_true", help="Emit raw (optionally .idx-subset) GRIB2 bytes to stdout")
    p_dec.set_defaults(func=cmd_decode_grib2)

    p_ext = sub.add_parser("extract-variable", help="Extract a variable using a regex pattern")
    p_ext.add_argument("file_or_url")
    p_ext.add_argument("pattern")
    p_ext.add_argument("--backend", default="cfgrib", choices=["cfgrib", "pygrib", "wgrib2"])
    p_ext.add_argument("--stdout", action="store_true", help="Write selected variable as bytes to stdout")
    p_ext.add_argument("--format", default="netcdf", choices=["netcdf", "grib2"], help="Output format for --stdout")
    p_ext.set_defaults(func=cmd_extract_variable)

    p_conv = sub.add_parser("convert-format", help="Convert decoded data to a format")
    p_conv.add_argument("file_or_url")
    p_conv.add_argument("format", choices=["netcdf", "geotiff"])  # bytes outputs
    p_conv.add_argument("-o", "--output", dest="output")
    p_conv.add_argument("--stdout", action="store_true", help="Write binary output to stdout instead of a file")
    p_conv.add_argument("--backend", default="cfgrib", choices=["cfgrib", "pygrib", "wgrib2"])
    p_conv.add_argument("--var", help="Variable name or regex for multi-var datasets")
    p_conv.add_argument("--pattern", help="Regex for .idx-based subsetting when using HTTP/S3")
    p_conv.add_argument("--unsigned", action="store_true", help="Use unsigned S3 access for public buckets")
    p_conv.set_defaults(func=cmd_convert_format)

    # Visualization subcommands
    p_hm = sub.add_parser("heatmap", help="Visualization: render 2D heatmap")
    p_hm.add_argument("--input", required=True, help="Path to .nc or .npy input")
    p_hm.add_argument("--var", help="Variable name for NetCDF inputs")
    p_hm.add_argument("--basemap", help="Path to background image")
    p_hm.add_argument("--extent", nargs=4, type=float, default=[-180, 180, -90, 90], help="west east south north")
    p_hm.add_argument("--output", required=True, help="Output PNG path")
    p_hm.add_argument("--width", type=int, default=1024)
    p_hm.add_argument("--height", type=int, default=512)
    p_hm.add_argument("--dpi", type=int, default=96)
    p_hm.add_argument("--cmap", default="YlOrBr")
    p_hm.add_argument("--colorbar", action="store_true")
    p_hm.add_argument("--label")
    p_hm.add_argument("--units")
    p_hm.add_argument("--features", help="Comma-separated features: coastline,borders,gridlines")
    p_hm.add_argument("--map-type", choices=["image", "tile"], default="image", help="Basemap type: image (default) or tile")
    p_hm.add_argument("--tile-source", help="Contextily tile source name or URL (when --map-type=tile)")
    p_hm.add_argument("--tile-zoom", dest="tile_zoom", type=int, default=3, help="Tile source zoom level")
    p_hm.add_argument("--timestamp", help="Overlay timestamp string")
    p_hm.add_argument("--crs", help="Force input CRS (e.g., EPSG:3857)")
    p_hm.add_argument("--reproject", action="store_true", help="Attempt reprojection to EPSG:4326 (limited support)")
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
    p_hm.set_defaults(func=_viz_heatmap_cmd)

    p_ct = sub.add_parser("contour", help="Visualization: render contour/filled contours")
    p_ct.add_argument("--input", required=True, help="Path to .nc or .npy input")
    p_ct.add_argument("--var", help="Variable name for NetCDF inputs")
    p_ct.add_argument("--basemap", help="Path to background image")
    p_ct.add_argument("--extent", nargs=4, type=float, default=[-180, 180, -90, 90], help="west east south north")
    p_ct.add_argument("--output", required=True, help="Output PNG path")
    p_ct.add_argument("--width", type=int, default=1024)
    p_ct.add_argument("--height", type=int, default=512)
    p_ct.add_argument("--dpi", type=int, default=96)
    p_ct.add_argument("--cmap", default="YlOrBr")
    p_ct.add_argument("--filled", action="store_true", help="Use filled contours")
    p_ct.add_argument("--levels", default=10, help="Count or comma-separated levels")
    p_ct.add_argument("--colorbar", action="store_true")
    p_ct.add_argument("--label")
    p_ct.add_argument("--units")
    p_ct.add_argument("--features", help="Comma-separated features: coastline,borders,gridlines")
    p_ct.add_argument("--map-type", choices=["image", "tile"], default="image")
    p_ct.add_argument("--tile-source", help="Contextily tile source (when --map-type=tile)")
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
    p_ct.set_defaults(func=_viz_contour_cmd)

    p_ts = sub.add_parser("timeseries", help="Visualization: render a time series from CSV or NetCDF")
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
    p_ts.add_argument("--style", choices=["line", "marker", "line_marker"], default="line")
    p_ts.set_defaults(func=_viz_timeseries_cmd)

    p_vector = sub.add_parser("vector", help="Visualization: render vector fields (e.g., wind, currents)")
    p_vector.add_argument("--input", help="Path to .nc input (alternative to --u/--v .npy)")
    p_vector.add_argument("--uvar", help="NetCDF: U variable name")
    p_vector.add_argument("--vvar", help="NetCDF: V variable name")
    p_vector.add_argument("--u", help="Path to U .npy file (alternative input)")
    p_vector.add_argument("--v", help="Path to V .npy file (alternative input)")
    p_vector.add_argument("--basemap", help="Path to background image")
    p_vector.add_argument("--extent", nargs=4, type=float, default=[-180, 180, -90, 90], help="west east south north")
    p_vector.add_argument("--output", required=True, help="Output PNG path")
    p_vector.add_argument("--width", type=int, default=1024)
    p_vector.add_argument("--height", type=int, default=512)
    p_vector.add_argument("--dpi", type=int, default=96)
    p_vector.add_argument("--density", type=float, default=0.2, help="Arrow sampling density (0<d<=1)")
    p_vector.add_argument("--scale", type=float, help="Quiver scale controlling arrow length")
    p_vector.add_argument("--color", default="#333333", help="Arrow color")
    p_vector.add_argument("--features", help="Comma-separated features: coastline,borders,gridlines")
    p_vector.add_argument("--map-type", choices=["image", "tile"], default="image")
    p_vector.add_argument("--tile-source", help="Contextily tile source (when --map-type=tile)")
    p_vector.add_argument("--tile-zoom", dest="tile_zoom", type=int, default=3)
    p_vector.add_argument("--streamlines", action="store_true", help="Render streamlines instead of quiver")
    p_vector.add_argument("--crs", help="Force input CRS (e.g., EPSG:3857)")
    p_vector.add_argument("--reproject", action="store_true")
    p_vector.add_argument("--no-coastline", action="store_true")
    p_vector.add_argument("--no-borders", action="store_true")
    p_vector.add_argument("--no-gridlines", action="store_true")
    p_vector.set_defaults(func=_viz_vector_cmd)

    # Deprecated alias: wind
    p_wind = sub.add_parser("wind", help="[deprecated] use 'vector' instead")
    p_wind.add_argument("--input", help="Path to .nc input (alternative to --u/--v .npy)")
    p_wind.add_argument("--uvar", help="NetCDF: U variable name")
    p_wind.add_argument("--vvar", help="NetCDF: V variable name")
    p_wind.add_argument("--u", help="Path to U .npy file (alternative input)")
    p_wind.add_argument("--v", help="Path to V .npy file (alternative input)")
    p_wind.add_argument("--basemap", help="Path to background image")
    p_wind.add_argument("--extent", nargs=4, type=float, default=[-180, 180, -90, 90], help="west east south north")
    p_wind.add_argument("--output", required=True, help="Output PNG path")
    p_wind.add_argument("--width", type=int, default=1024)
    p_wind.add_argument("--height", type=int, default=512)
    p_wind.add_argument("--dpi", type=int, default=96)
    p_wind.add_argument("--density", type=float, default=0.2, help="Arrow sampling density (0<d<=1)")
    p_wind.add_argument("--scale", type=float, help="Quiver scale controlling arrow length")
    p_wind.add_argument("--color", default="#333333", help="Arrow color")
    p_wind.set_defaults(func=_viz_wind_cmd)

    # Animate frames
    from argparse import ArgumentTypeError

    def _levels_arg(val):
        try:
            return int(val)
        except ValueError:
            try:
                return [float(x) for x in val.split(",") if x.strip()]
            except Exception as e:
                raise ArgumentTypeError("levels must be int or comma-separated floats") from e

    def _viz_animate_cmd(ns: argparse.Namespace) -> int:
        if ns.mode == "particles":
            from datavizhub.visualization.vector_particles_manager import VectorParticlesManager

            mgr = VectorParticlesManager(basemap=ns.basemap, extent=ns.extent)
            manifest = mgr.render(
                input_path=ns.input,
                uvar=ns.uvar,
                vvar=ns.vvar,
                u=ns.u,
                v=ns.v,
                seed=ns.seed,
                particles=ns.particles,
                custom_seed=ns.custom_seed,
                dt=ns.dt,
                steps_per_frame=ns.steps_per_frame,
                method=ns.method,
                color=ns.color,
                size=ns.size,
                width=ns.width,
                height=ns.height,
                dpi=ns.dpi,
                # CRS handling
                crs=getattr(ns, "crs", None),
                reproject=getattr(ns, "reproject", False),
                output_dir=ns.output_dir,
            )
            out = mgr.save(ns.manifest)
            print(out or "")
            # Optional: compose video
            if ns.to_video:
                from datavizhub.processing.video_processor import VideoProcessor

                frames_dir = ns.output_dir
                vp = VideoProcessor(input_directory=frames_dir, output_file=ns.to_video, fps=ns.fps)
                if not vp.validate():
                    # Gracefully skip if ffmpeg missing
                    print("ffmpeg/ffprobe not available; skipping video composition", file=sys.stderr)
                else:
                    vp.process(fps=ns.fps)
                    vp.save(ns.to_video)
                    print(ns.to_video)
            return 0
        else:
            from datavizhub.visualization.animate_manager import AnimateManager

            mgr = AnimateManager(mode=ns.mode, basemap=ns.basemap, extent=ns.extent, output_dir=ns.output_dir)
            # Features for heatmap/contour frames
            features = None
            if getattr(ns, "features", None):
                features = [f.strip() for f in (ns.features.split(",")) if f.strip()]
            else:
                from datavizhub.visualization.styles import MAP_STYLES

                features = list(MAP_STYLES.get("features", []) or [])
            if getattr(ns, "no_coastline", False) and "coastline" in features:
                features = [f for f in features if f != "coastline"]
            if getattr(ns, "no_borders", False) and "borders" in features:
                features = [f for f in features if f != "borders"]
            if getattr(ns, "no_gridlines", False) and "gridlines" in features:
                features = [f for f in features if f != "gridlines"]

            manifest = mgr.render(
                input_path=ns.input,
                var=ns.var,
                mode=ns.mode,
                cmap=ns.cmap,
                levels=ns.levels,
                vmin=ns.vmin,
                vmax=ns.vmax,
                width=ns.width,
                height=ns.height,
                dpi=ns.dpi,
                output_dir=ns.output_dir,
                colorbar=getattr(ns, "colorbar", False),
                label=getattr(ns, "label", None),
                units=getattr(ns, "units", None),
                show_timestamp=getattr(ns, "show_timestamp", False),
                timestamps_csv=getattr(ns, "timestamps_csv", None),
                timestamp_loc=getattr(ns, "timestamp_loc", "lower_right"),
                # Vector-specific config (passed-through; ignored by heatmap/contour)
                u=ns.u,
                v=ns.v,
                uvar=ns.uvar,
                vvar=ns.vvar,
                density=getattr(ns, "density", 0.2),
                scale=getattr(ns, "scale", None),
                color=getattr(ns, "color", "#333333"),
                features=features,
                map_type=getattr(ns, "map_type", "image"),
                tile_source=getattr(ns, "tile_source", None),
                tile_zoom=getattr(ns, "tile_zoom", 3),
                # CRS handling
                crs=getattr(ns, "crs", None),
                reproject=getattr(ns, "reproject", False),
            )
            out = mgr.save(ns.manifest)
            print(out or "")
            if ns.to_video:
                from datavizhub.processing.video_processor import VideoProcessor

                frames_dir = ns.output_dir
                vp = VideoProcessor(input_directory=frames_dir, output_file=ns.to_video, fps=ns.fps)
                if not vp.validate():
                    print("ffmpeg/ffprobe not available; skipping video composition", file=sys.stderr)
                else:
                    vp.process(fps=ns.fps)
                    vp.save(ns.to_video)
                    print(ns.to_video)
            return 0

    p_anim = sub.add_parser("animate", help="Generate PNG frames from a time-varying dataset")
    p_anim.add_argument("--mode", choices=["heatmap", "contour", "vector", "particles"], default="heatmap")
    p_anim.add_argument("--input", help="Path to .nc 3D var or 3D .npy stack (for heatmap/contour/vector)")
    p_anim.add_argument("--var", help="NetCDF variable name (heatmap/contour)")
    # Vector-specific inputs
    p_anim.add_argument("--uvar", help="NetCDF: U variable name (vector/particles mode)")
    p_anim.add_argument("--vvar", help="NetCDF: V variable name (vector/particles mode)")
    p_anim.add_argument("--u", help="Path to U .npy stack (vector/particles mode)")
    p_anim.add_argument("--v", help="Path to V .npy stack (vector/particles mode)")
    p_anim.add_argument("--output-dir", required=True, help="Directory to write frames")
    p_anim.add_argument("--manifest", help="Optional manifest output path (JSON)")
    p_anim.add_argument("--cmap", default="YlOrBr")
    p_anim.add_argument("--levels", type=_levels_arg, default=10, help="Contour levels: count or comma-separated")
    p_anim.add_argument("--vmin", type=float)
    p_anim.add_argument("--vmax", type=float)
    p_anim.add_argument("--basemap", help="Path to background image")
    p_anim.add_argument("--extent", nargs=4, type=float, default=[-180, 180, -90, 90], help="west east south north")
    p_anim.add_argument("--width", type=int, default=1024)
    p_anim.add_argument("--height", type=int, default=512)
    p_anim.add_argument("--dpi", type=int, default=96)
    p_anim.add_argument("--density", type=float, default=0.2, help="Vector mode: arrow sampling density (0<d<=1)")
    p_anim.add_argument("--scale", type=float, help="Vector mode: quiver scale controlling arrow length")
    p_anim.add_argument("--color", default="#333333", help="Vector/particles color")
    p_anim.add_argument("--colorbar", action="store_true", help="Heatmap/contour: draw colorbar")
    p_anim.add_argument("--label", help="Heatmap/contour colorbar label")
    p_anim.add_argument("--units", help="Heatmap/contour units for colorbar")
    p_anim.add_argument("--show-timestamp", action="store_true", help="Overlay timestamps per frame if available")
    p_anim.add_argument("--timestamps-csv", dest="timestamps_csv", help="CSV with one timestamp per line (overrides auto)")
    p_anim.add_argument(
        "--timestamp-loc",
        dest="timestamp_loc",
        choices=["upper_left", "upper_right", "lower_left", "lower_right"],
        default="lower_right",
        help="Timestamp placement (axes-relative)",
    )
    p_anim.add_argument("--features", help="Heatmap/contour: comma-separated features")
    p_anim.add_argument("--map-type", choices=["image", "tile"], default="image")
    p_anim.add_argument("--tile-source", help="Contextily tile source (when --map-type=tile)")
    p_anim.add_argument("--tile-zoom", dest="tile_zoom", type=int, default=3)
    p_anim.add_argument("--no-coastline", action="store_true")
    p_anim.add_argument("--no-borders", action="store_true")
    p_anim.add_argument("--no-gridlines", action="store_true")
    # Particles-specific
    p_anim.add_argument("--seed", choices=["grid", "random", "custom"], default="grid", help="Particles: seeding strategy")
    p_anim.add_argument("--particles", type=int, default=200, help="Particles: count for grid/random seeding")
    p_anim.add_argument("--custom-seed", dest="custom_seed", help="Particles: CSV with lon,lat columns")
    p_anim.add_argument("--dt", type=float, default=0.01, help="Particles: integration step")
    p_anim.add_argument("--steps-per-frame", type=int, default=1, help="Particles: substeps per frame")
    p_anim.add_argument("--size", type=float, default=0.5, help="Particles: marker size")
    p_anim.add_argument("--method", choices=["euler", "rk2", "midpoint"], default="euler", help="Particles: integrator")
    p_anim.add_argument("--crs", help="Force input CRS for heatmap/contour/vector")
    p_anim.add_argument("--reproject", action="store_true")
    p_anim.add_argument("--to-video", dest="to_video", help="Optional: compose frames to MP4 using ffmpeg")
    p_anim.add_argument("--fps", type=int, default=30, help="Frames per second for video composition")
    p_anim.set_defaults(func=_viz_animate_cmd)

    # Compose frames to video
    def _compose_video_cmd(ns: argparse.Namespace) -> int:
        from datavizhub.processing.video_processor import VideoProcessor

        vp = VideoProcessor(input_directory=ns.frames, output_file=ns.output, basemap=ns.basemap, fps=ns.fps)
        if not vp.validate():
            print("ffmpeg/ffprobe not available; skipping video composition", file=sys.stderr)
            return 0
        vp.process(fps=ns.fps)
        vp.save(ns.output)
        print(ns.output)
        return 0

    p_vid = sub.add_parser("compose-video", help="Compose a directory of frames into MP4 (requires ffmpeg)")
    p_vid.add_argument("--frames", required=True, help="Directory containing frame_*.png files")
    p_vid.add_argument("-o", "--output", required=True, help="Output MP4 path")
    p_vid.add_argument("--basemap", help="Optional background image to overlay under frames")
    p_vid.add_argument("--fps", type=int, default=30)
    p_vid.set_defaults(func=_compose_video_cmd)

    # Interactive HTML
    def _viz_interactive_cmd(ns: argparse.Namespace) -> int:
        from datavizhub.visualization.interactive_manager import InteractiveManager

        mgr = InteractiveManager(engine=ns.engine, extent=ns.extent, cmap=ns.cmap)
        # Build features with negations
        features = None
        if getattr(ns, "features", None):
            features = [f.strip() for f in (ns.features.split(",")) if f.strip()]
        else:
            from datavizhub.visualization.styles import MAP_STYLES

            features = list(MAP_STYLES.get("features", []) or [])
        if getattr(ns, "no_coastline", False) and "coastline" in features:
            features = [f for f in features if f != "coastline"]
        if getattr(ns, "no_borders", False) and "borders" in features:
            features = [f for f in features if f != "borders"]
        if getattr(ns, "no_gridlines", False) and "gridlines" in features:
            features = [f for f in features if f != "gridlines"]

        # Vector-specific passthrough
        extra = {}
        if ns.mode == "vector":
            extra.update({
                "uvar": getattr(ns, "uvar", None),
                "vvar": getattr(ns, "vvar", None),
                "u": getattr(ns, "u", None),
                "v": getattr(ns, "v", None),
                "density": getattr(ns, "density", 0.2),
                "scale": getattr(ns, "scale", 1.0),
                "color": getattr(ns, "color", "#333333"),
                "streamlines": getattr(ns, "streamlines", False),
            })

        mgr.render(
            input_path=ns.input,
            var=ns.var,
            mode=ns.mode,
            engine=ns.engine,
            cmap=ns.cmap,
            features=features,
            colorbar=ns.colorbar,
            label=ns.label,
            units=ns.units,
            timestamp=ns.timestamp,
            timestamp_loc=ns.timestamp_loc,
            tiles=ns.tiles,
            zoom=ns.zoom,
            width=ns.width,
            height=ns.height,
            **extra,
        )
        out = mgr.save(ns.output)
        print(out or "")
        return 0

    p_int = sub.add_parser("interactive", help="Render interactive HTML (folium or plotly)")
    p_int.add_argument("--input", required=True, help="Path to .npy/.nc/.csv input")
    p_int.add_argument("--var", help="NetCDF variable name (for .nc inputs)")
    p_int.add_argument("--mode", choices=["heatmap", "contour", "points", "vector"], default="heatmap")
    p_int.add_argument("--engine", choices=["folium", "plotly"], default="folium")
    p_int.add_argument("--output", required=True, help="Output HTML path")
    p_int.add_argument("--extent", nargs=4, type=float, default=[-180, 180, -90, 90])
    p_int.add_argument("--cmap", default="YlOrBr")
    p_int.add_argument("--features", help="Heatmap/contour only: features (may be ignored depending on engine)")
    p_int.add_argument("--no-coastline", action="store_true")
    p_int.add_argument("--no-borders", action="store_true")
    p_int.add_argument("--no-gridlines", action="store_true")
    p_int.add_argument("--colorbar", action="store_true")
    p_int.add_argument("--label")
    p_int.add_argument("--units")
    p_int.add_argument("--timestamp")
    p_int.add_argument("--timestamp-loc", dest="timestamp_loc", choices=["upper_left", "upper_right", "lower_left", "lower_right"], default="lower_right")
    # Engine-specific
    p_int.add_argument("--tiles", help="Folium: tile layer name/URL", default="OpenStreetMap")
    p_int.add_argument("--zoom", type=int, help="Folium: initial zoom")
    p_int.add_argument("--attribution", help="Folium: attribution for custom tiles/WMS")
    p_int.add_argument("--wms-url", dest="wms_url", help="Folium: WMS base URL")
    p_int.add_argument("--wms-layers", dest="wms_layers", help="Folium: WMS layer names")
    p_int.add_argument("--wms-format", dest="wms_format", default="image/png")
    p_int.add_argument("--wms-transparent", dest="wms_transparent", action="store_true")
    p_int.add_argument("--layer-control", dest="layer_control", action="store_true", help="Add a layer control switcher")
    p_int.add_argument("--width", type=int, help="Plotly: width")
    p_int.add_argument("--height", type=int, help="Plotly: height")
    p_int.add_argument("--crs", help="Force input CRS")
    p_int.add_argument("--reproject", action="store_true")
    # Points timedimension
    p_int.add_argument("--time-column", help="CSV points: column containing ISO8601 time strings")
    p_int.add_argument("--period", default="P1D", help="TimeDimension period (e.g., P1D)")
    p_int.add_argument("--transition-ms", dest="transition_ms", type=int, default=200, help="TimeDimension transition time (ms)")
    # Vector-specific (interactive)
    p_int.add_argument("--uvar", help="NetCDF: U variable name (vector mode)")
    p_int.add_argument("--vvar", help="NetCDF: V variable name (vector mode)")
    p_int.add_argument("--u", help="Path to U .npy array (vector mode)")
    p_int.add_argument("--v", help="Path to V .npy array (vector mode)")
    p_int.add_argument("--density", type=float, default=0.2, help="Vector: arrow sampling density (0<d<=1)")
    p_int.add_argument("--scale", type=float, default=1.0, help="Vector: arrow length scale in degrees")
    p_int.add_argument("--color", default="#333333", help="Vector: arrow/line color")
    p_int.add_argument("--streamlines", action="store_true", help="Vector: render streamlines image overlay")
    p_int.set_defaults(func=_viz_interactive_cmd)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
