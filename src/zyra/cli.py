# SPDX-License-Identifier: Apache-2.0
"""Zyra CLI entrypoint and command wiring.

Organizes commands into groups that mirror the 8-stage pipeline hierarchy:

- import (alias: acquire/ingest): ingress from HTTP/S3/FTP/Vimeo backends
- process (alias: transform): GRIB/NetCDF decoding, extraction, format conversion, and metadata helpers
- simulate: simulation under uncertainty (skeleton)
- decide (alias: optimize): decision/optimization (skeleton)
- visualize (alias: render): static and animated rendering
- narrate: AI-driven storytelling/reporting (skeleton)
- verify: evaluation and metrics (skeleton)
- export (alias: disseminate; legacy: decimate): egress (local, S3, FTP, HTTP POST, Vimeo)
- run: run a config-driven pipeline (YAML/JSON)

Internal helpers support streaming bytes via stdin/stdout, GRIB ``.idx``
subsetting, and S3 URL parsing.
"""

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Tuple

from zyra import __version__ as ZYRA_VERSION


def _print_version_banner(mode: str = "short") -> None:
    """Print version banner.

    Modes:
    - short: ASCII logo (when found) + version + repo URL
    - long: adds runtime diagnostics (tools, libs, env, platform)
    - json: machine-readable diagnostics only (no logo)
    """
    logo_text: str | None = None
    # Candidate locations in order of preference
    candidates: list[str] = []
    env_logo = os.environ.get("ZYRA_ASCII_LOGO")
    if env_logo:
        candidates.append(env_logo)
    # Project-relative (useful in dev checkouts)
    candidates.append("branding/logos/ascii/logo_ascii_tree_tiny.txt")
    # Downstream absolute hint (best-effort)
    candidates.append("/branding/logos/ascii/logo_ascii_tree_tiny.txt")
    # Packaged asset under zyra.assets/ascii if available
    try:
        try:
            from importlib import resources as importlib_resources  # type: ignore
        except Exception:  # pragma: no cover
            import importlib_resources  # type: ignore
        res = (
            importlib_resources.files("zyra.assets")
            .joinpath("ascii")
            .joinpath("logo_ascii_tree_tiny.txt")
        )
        if getattr(res, "is_file", None) and res.is_file():  # type: ignore[attr-defined]
            with importlib_resources.as_file(res) as p:
                logo_text = Path(str(p)).read_text(encoding="utf-8", errors="ignore")
        else:
            # Fallback: older packaging may place the logo at the root of assets
            res2 = importlib_resources.files("zyra.assets").joinpath(
                "logo_ascii_tree_tiny.txt"
            )
            if getattr(res2, "is_file", None) and res2.is_file():  # type: ignore[attr-defined]
                with importlib_resources.as_file(res2) as p:
                    logo_text = Path(str(p)).read_text(
                        encoding="utf-8", errors="ignore"
                    )
    except importlib_metadata.PackageNotFoundError:
        # Package metadata not available (editable install or runtime env);
        # ignore gracefully.
        pass
    except Exception as exc:  # pragma: no cover - unexpected metadata error
        # Avoid hard-failing version banner; log at debug level if possible.
        try:
            import logging as _log

            _log.getLogger(__name__).debug(
                "distribution() metadata read failed: %s", exc
            )
        except Exception:
            pass
    if logo_text is None:
        for c in candidates:
            try:
                p = Path(c)
                if p.exists() and p.is_file():
                    logo_text = p.read_text(encoding="utf-8", errors="ignore")
                    break
            except Exception:
                pass
    if mode == "json":
        print(json.dumps(_collect_version_info(), indent=2, sort_keys=True))
        return
    info = _collect_version_info()
    lines = []
    if logo_text and mode == "short":
        lines.append(logo_text.rstrip("\n"))
    lines.append(f"Zyra {info.get('version', ZYRA_VERSION)}")
    lines.append("https://github.com/NOAA-GSL/zyra")
    if mode == "long":
        lines.append("")
        lines.append(
            f"Python: {info['python']['version']} ({info['python']['implementation']})"
        )
        lines.append(
            f"Platform: {info['platform']['system']}/{info['platform']['machine']}"
        )
        try:
            inst = info.get("install", {})
            lines.append(
                f"Install: {inst.get('module_path','')}\nExec: {inst.get('executable','')}"
            )
        except Exception:
            pass
        git = info.get("git") or {}
        if git.get("commit") or git.get("date"):
            commit = git.get("commit", "unknown")
            date = git.get("date", "unknown")
            lines.append(f"Git: {commit} ({date})")
        tools = info.get("tools", {})
        lines.append(
            f"FFmpeg: {tools.get('ffmpeg','not found')}; FFprobe: {tools.get('ffprobe','not found')}"
        )
        lines.append(f"wgrib2: {tools.get('wgrib2','not found')}")
        libs = info.get("libs", {})
        # Group core libs concisely
        core_a = []
        for k in ["xarray", "netcdf4", "cfgrib", "eccodes", "pygrib"]:
            v = libs.get(k)
            core_a.append(f"{k}: {v if v is not None else 'not installed'}")
        lines.append("; ".join(core_a))
        geo_a = []
        for k in ["rasterio", "gdal", "rioxarray", "cartopy", "matplotlib"]:
            v = libs.get(k)
            geo_a.append(f"{k}: {v if v is not None else 'not installed'}")
        lines.append("; ".join(geo_a))
        env = info.get("env", {})
        lines.append(
            f"DATA_DIR: {env.get('DATA_DIR') or ''}; LOG_LEVEL: {env.get('LOG_LEVEL') or ''}"
        )
    print("\n".join(lines))


def _get_tool_version(cmd: str) -> str | None:
    exe = shutil.which(cmd)
    if not exe:
        return None
    try:
        proc = subprocess.run(
            [exe, "-version"], capture_output=True, text=True, timeout=3
        )
    except Exception:
        return None
    out = (proc.stdout or proc.stderr or "").strip().splitlines()
    return out[0] if out else None


def _collect_version_info() -> dict:
    # Basic metadata
    import sys as _sys

    info: dict = {
        "version": ZYRA_VERSION,
        "repo": "https://github.com/NOAA-GSL/zyra",
        "python": {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
        },
        "platform": {
            "system": platform.system().lower() or sys.platform,
            "machine": platform.machine().lower(),
        },
        "install": {
            "module_path": str(Path(__file__).resolve()),
            "executable": _sys.executable,
        },
        "env": {
            "DATA_DIR": os.environ.get("DATA_DIR"),
            "LOG_LEVEL": os.environ.get("LOG_LEVEL"),
        },
    }
    # Distribution info (best-effort)
    try:
        dist = importlib_metadata.distribution("zyra")
        info["distribution"] = {
            "name": dist.metadata.get("Name", "zyra"),
            "version": dist.version,
        }
    except Exception:
        pass
    # Git metadata via env (optional)
    git_commit = os.environ.get("ZYRA_GIT_COMMIT")
    git_date = os.environ.get("ZYRA_BUILD_DATE")
    if git_commit or git_date:
        info["git"] = {"commit": git_commit, "date": git_date}
    # External tool versions
    info["tools"] = {
        "ffmpeg": _get_tool_version("ffmpeg") or "not found",
        "ffprobe": _get_tool_version("ffprobe") or "not found",
        "wgrib2": _get_tool_version("wgrib2") or "not found",
    }
    # Library versions
    libs: dict[str, str | None] = {}

    def ver(mod: str, attr: str = "__version__") -> str | None:
        try:
            m = __import__(mod, fromlist=["_"])
            v = getattr(m, attr, None)
            return str(v) if v is not None else None
        except Exception:
            return None

    libs["xarray"] = ver("xarray")
    libs["netcdf4"] = ver("netCDF4") or ver("netcdf4")
    libs["cfgrib"] = ver("cfgrib")
    libs["eccodes"] = ver("eccodes")
    libs["pygrib"] = ver("pygrib")
    # Raster/GDAL stack
    try:
        import rasterio  # type: ignore

        libs["rasterio"] = getattr(rasterio, "__version__", None)
        libs["gdal"] = getattr(rasterio, "__gdal_version__", None)
    except Exception:
        libs["rasterio"] = None
        libs["gdal"] = None
    libs["rioxarray"] = ver("rioxarray")
    libs["cartopy"] = ver("cartopy")
    libs["matplotlib"] = ver("matplotlib")
    info["libs"] = libs
    # Heuristic extras presence from libs
    extras: dict[str, bool] = {
        "connectors": any(
            (libs.get(k) is not None) for k in ("boto3", "requests", "PyVimeo")
        ),
        "processing": any(
            (libs.get(k) is not None)
            for k in ("xarray", "netcdf4", "cfgrib", "rasterio", "rioxarray")
        ),
        "visualization": any(
            (libs.get(k) is not None) for k in ("cartopy", "matplotlib")
        ),
        "wizard": False,
        "api": False,
    }
    try:
        import prompt_toolkit  # type: ignore  # noqa: F401

        extras["wizard"] = True
    except Exception:
        pass
    try:
        import fastapi  # type: ignore  # noqa: F401
        import uvicorn  # type: ignore  # noqa: F401

        extras["api"] = True
    except Exception:
        pass
    info["extras"] = extras
    return info


def _parse_s3_url(url: str) -> Tuple[str, str]:
    m = re.match(r"^s3://([^/]+)/(.+)$", url)
    if not m:
        raise ValueError("Invalid s3 URL. Expected s3://bucket/key")
    return m.group(1), m.group(2)


def _normalize_group_name(name: str) -> str:
    """Normalize top-level group aliases to canonical names.

    Keeps canonical groups stable for internal wiring while accepting user-friendly
    aliases at the CLI entry: import→acquire, render→visualize,
    disseminate/export/decimation→decimate. The legacy name 'decimate' remains
    accepted for back-compat.
    """
    n = (name or "").strip().lower()
    alias_map = {
        "import": "acquire",
        "ingest": "acquire",
        "render": "visualize",
        # Egress: keep 'decimate' as internal canonical for back-compat
        "export": "decimate",
        "disseminate": "decimate",
        "decimation": "decimate",
        "optimize": "decide",
    }
    return alias_map.get(n, n)


def _read_bytes(
    path_or_url: str, *, idx_pattern: str | None = None, unsigned: bool = False
) -> bytes:
    # stdin
    if path_or_url == "-":
        return sys.stdin.buffer.read()

    p = Path(path_or_url)
    if p.exists():
        return p.read_bytes()

    # HTTP(S)
    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        try:
            from zyra.connectors.backends import http as http_backend
            from zyra.utils.grib import idx_to_byteranges

            if idx_pattern:
                lines = http_backend.get_idx_lines(path_or_url)
                ranges = idx_to_byteranges(lines, idx_pattern)
                return http_backend.download_byteranges(path_or_url, ranges.keys())
            return http_backend.fetch_bytes(path_or_url)
        except Exception as exc:  # pragma: no cover - optional dep
            raise SystemExit(f"Failed to fetch from URL: {exc}") from exc

    # S3
    if path_or_url.startswith("s3://"):
        try:
            from zyra.connectors.backends import s3 as s3_backend
            from zyra.utils.grib import idx_to_byteranges

            if idx_pattern:
                lines = s3_backend.get_idx_lines(path_or_url, unsigned=unsigned)
                ranges = idx_to_byteranges(lines, idx_pattern)
                return s3_backend.download_byteranges(
                    path_or_url, None, ranges.keys(), unsigned=unsigned
                )
            return s3_backend.fetch_bytes(path_or_url, unsigned=unsigned)
        except Exception as exc:  # pragma: no cover - optional dep
            raise SystemExit(f"Failed to fetch from S3: {exc}") from exc

    raise SystemExit(f"Input not found or unsupported scheme: {path_or_url}")


def cmd_decode_grib2(args: argparse.Namespace) -> int:
    from zyra.processing import grib_decode
    from zyra.processing.grib_utils import extract_metadata

    data = _read_bytes(
        args.file_or_url, idx_pattern=args.pattern, unsigned=args.unsigned
    )

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

    from zyra.processing import grib_decode
    from zyra.processing.grib_utils import (
        VariableNotFoundError,
        convert_to_format,
        extract_variable,
    )

    data = _read_bytes(args.file_or_url)

    # If --stdout is requested, stream binary output of the selected variable
    if getattr(args, "stdout", False):
        out_fmt = (args.format or "netcdf").lower()
        if out_fmt not in ("netcdf", "grib2"):
            raise SystemExit(
                "Unsupported --format for extract-variable: use 'netcdf' or 'grib2'"
            )

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
                    res = subprocess.run(
                        args_list, capture_output=True, text=True, check=False
                    )
                    if res.returncode != 0:
                        # Gracefully fall back to Python conversion when wgrib2 lacks NetCDF support
                        print(
                            res.stderr.strip()
                            or "wgrib2 subsetting failed; falling back to Python conversion",
                            file=sys.stderr,
                        )
                        # Do not return; continue to Python fallback below
                        # wgrib2 failed; will fall back to Python conversion after this block
                        # Continue to Python fallback below
                    else:
                        from pathlib import Path as _P

                        with _P(out_path).open("rb") as f:
                            sys.stdout.buffer.write(f.read())
                        return 0
                finally:
                    import contextlib
                    from pathlib import Path as _P

                    with contextlib.suppress(Exception):
                        _P(out_path).unlink()
            finally:
                import contextlib
                from pathlib import Path as _P

                with contextlib.suppress(Exception):
                    _P(in_path).unlink()

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
            from zyra.processing.netcdf_data_processor import convert_to_grib2

            ds = (
                var_obj.to_dataset(name=getattr(var_obj, "name", "var"))
                if hasattr(var_obj, "to_dataset")
                else None
            )
            if ds is None:
                print(
                    "Selected variable cannot be converted to GRIB2 without wgrib2",
                    file=sys.stderr,
                )
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
        name = getattr(var, "name", None) or getattr(
            getattr(var, "attrs", {}), "get", lambda *_: None
        )("long_name")
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
    from zyra.processing import grib_decode
    from zyra.processing.grib_utils import DecodedGRIB, convert_to_format

    if not args.output and not args.stdout:
        raise SystemExit("--output or --stdout is required for convert-format")

    data = _read_bytes(
        args.file_or_url, idx_pattern=args.pattern, unsigned=args.unsigned
    )

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
            from zyra.processing.netcdf_data_processor import load_netcdf

            with load_netcdf(data) as ds:
                decoded = DecodedGRIB(
                    backend="cfgrib", dataset=ds
                )  # reuse xarray-based conversions
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
        raise SystemExit(f"Failed to open input: {exc}") from exc

    out_bytes = convert_to_format(decoded, args.format, var=args.var)
    if args.stdout:
        sys.stdout.buffer.write(out_bytes)
    else:
        Path(args.output).write_bytes(out_bytes)
        print(f"Wrote {args.output}")
    return 0


def _viz_heatmap_cmd(ns: argparse.Namespace) -> int:
    # Local import to avoid importing visualization deps unless used
    from zyra.visualization.heatmap_manager import HeatmapManager

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
        from zyra.visualization.styles import MAP_STYLES

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
    from zyra.visualization.contour_manager import ContourManager

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
        from zyra.visualization.styles import MAP_STYLES

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
    from zyra.visualization.timeseries_manager import TimeSeriesManager

    mgr = TimeSeriesManager(
        title=ns.title, xlabel=ns.xlabel, ylabel=ns.ylabel, style=ns.style
    )
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
    from zyra.visualization.vector_field_manager import VectorFieldManager

    mgr = VectorFieldManager(
        basemap=ns.basemap,
        color=ns.color,
        density=ns.density,
        scale=ns.scale,
        streamlines=getattr(ns, "streamlines", False),
    )
    mgr.configure(extent=ns.extent)
    features = None
    if getattr(ns, "features", None):
        features = [f.strip() for f in (ns.features.split(",")) if f.strip()]
    else:
        features = None
    if features is None:
        from zyra.visualization.styles import MAP_STYLES

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


def main(argv: list[str] | None = None) -> int:
    # Pre-scan argv to support --version without requiring a subcommand
    args_list = argv if argv is not None else sys.argv[1:]
    if any(a in {"--version", "-V"} for a in args_list):
        mode = "short"
        if "--json" in args_list:
            mode = "json"
        elif "--long" in args_list:
            mode = "long"
        _print_version_banner(mode)
        return 0
    parser = argparse.ArgumentParser(prog="zyra")
    # Global verbosity controls for all commands
    vgrp = parser.add_mutually_exclusive_group()
    vgrp.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose output (sets ZYRA_VERBOSITY=debug)",
    )
    vgrp.add_argument(
        "--quiet", action="store_true", help="Quiet output (sets ZYRA_VERBOSITY=quiet)"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # Pre-scan argv to support lazy registration and avoid importing heavy stacks unnecessarily
    first_non_flag_raw = next((a for a in args_list if not a.startswith("-")), None)
    first_non_flag = (
        _normalize_group_name(first_non_flag_raw) if first_non_flag_raw else None
    )

    # Always make 'run' available (lightweight)
    from zyra.pipeline_runner import register_cli_run as _register_run

    _register_run(sub)

    # Lazy-register only the requested top-level group when possible
    if first_non_flag == "acquire":
        from zyra.connectors import ingest as _ingest_mod

        p_acq = sub.add_parser(
            "acquire", help="Acquire/ingest data from sources (alias: import/ingest)"
        )
        acq_sub = p_acq.add_subparsers(dest="acquire_cmd", required=True)
        _ingest_mod.register_cli(acq_sub)
        # Alias top-level: import → acquire
        p_import = sub.add_parser("import", help=argparse.SUPPRESS)
        import_sub = p_import.add_subparsers(dest="acquire_cmd", required=True)
        _ingest_mod.register_cli(import_sub)
    elif first_non_flag == "process":
        import zyra.transform as _transform_mod
        from zyra import processing as _process_mod

        p_proc = sub.add_parser(
            "process", help="Processing commands (GRIB/NetCDF/GeoTIFF) + transforms"
        )
        proc_sub = p_proc.add_subparsers(dest="process_cmd", required=True)
        # Combine transform commands under process group
        _process_mod.register_cli(proc_sub)
        _transform_mod.register_cli(proc_sub)
    elif first_non_flag == "visualize":
        from zyra.visualization import cli_register as _visual_mod

        p_viz = sub.add_parser(
            "visualize",
            help="Visualization commands (static/interactive/animation) (alias: render)",
        )
        viz_sub = p_viz.add_subparsers(dest="visualize_cmd", required=True)
        _visual_mod.register_cli(viz_sub)
        # Alias top-level: render → visualize
        p_render = sub.add_parser("render", help=argparse.SUPPRESS)
        render_sub = p_render.add_subparsers(dest="visualize_cmd", required=True)
        _visual_mod.register_cli(render_sub)
    elif first_non_flag == "disseminate":
        from zyra.connectors import egress as _egress_mod

        p_disseminate = sub.add_parser(
            "disseminate",
            help="Write/egress data to destinations (alias: export; legacy: decimate)",
        )
        dis_sub = p_disseminate.add_subparsers(dest="disseminate_cmd", required=True)
        _egress_mod.register_cli(dis_sub)
        # Legacy alias top-level: decimate → disseminate
        p_dec_alias = sub.add_parser("decimate", help=argparse.SUPPRESS)
        dec_alias_sub = p_dec_alias.add_subparsers(
            dest="disseminate_cmd", required=True
        )
        _egress_mod.register_cli(dec_alias_sub)
    elif first_non_flag == "decimate":
        # Legacy top-level alias retained for back-compat
        from zyra.connectors import egress as _egress_mod

        p_dec = sub.add_parser(
            "decimate",
            help="[deprecated] Write/egress data (use 'disseminate' or 'export')",
        )
        dec_sub = p_dec.add_subparsers(dest="decimate_cmd", required=True)
        _egress_mod.register_cli(dec_sub)
        # Alias top-level: disseminate/export → decimate
        p_disseminate = sub.add_parser("disseminate", help=argparse.SUPPRESS)
        dis_sub = p_disseminate.add_subparsers(dest="decimate_cmd", required=True)
        _egress_mod.register_cli(dis_sub)
        p_export = sub.add_parser("export", help=argparse.SUPPRESS)
        exp_sub = p_export.add_subparsers(dest="decimate_cmd", required=True)
        _egress_mod.register_cli(exp_sub)
    elif first_non_flag == "simulate":
        import zyra.simulate as _simulate_mod

        p_sim = sub.add_parser("simulate", help="Simulate under uncertainty (skeleton)")
        sim_sub = p_sim.add_subparsers(dest="simulate_cmd", required=True)
        _simulate_mod.register_cli(sim_sub)
    elif first_non_flag == "decide":
        import zyra.decide as _decide_mod

        p_dec = sub.add_parser("decide", help="Decision/optimization (skeleton)")
        d_sub = p_dec.add_subparsers(dest="decide_cmd", required=True)
        _decide_mod.register_cli(d_sub)
        # Alias top-level: optimize → decide
        p_opt = sub.add_parser("optimize", help=argparse.SUPPRESS)
        opt_sub = p_opt.add_subparsers(dest="decide_cmd", required=True)
        _decide_mod.register_cli(opt_sub)
    elif first_non_flag == "narrate":
        import zyra.narrate as _narrate_mod

        p_nar = sub.add_parser("narrate", help="Narrate/report (skeleton)")
        n_sub = p_nar.add_subparsers(dest="narrate_cmd", required=True)
        _narrate_mod.register_cli(n_sub)
    elif first_non_flag == "verify":
        import zyra.verify as _verify_mod

        p_ver = sub.add_parser(
            "verify", help="Evaluation/metrics/validation (skeleton)"
        )
        v_sub = p_ver.add_subparsers(dest="verify_cmd", required=True)
        _verify_mod.register_cli(v_sub)
    elif first_non_flag == "transform":
        import zyra.transform as _transform_mod

        p_tr = sub.add_parser("transform", help="Transform helpers (metadata, etc.)")
        tr_sub = p_tr.add_subparsers(dest="transform_cmd", required=True)
        _transform_mod.register_cli(tr_sub)
    elif first_non_flag == "run":
        # Already registered above
        pass
    elif first_non_flag == "search":
        # Single command for dataset discovery
        from zyra.connectors import discovery as _discovery_mod

        p_search = sub.add_parser(
            "search", help="Search datasets (local SOS catalog; JSON/YAML export)"
        )
        _discovery_mod.register_cli(p_search)
    elif first_non_flag == "wizard":
        # Lightweight: registers a single command with optional LLM backends
        from zyra import wizard as _wizard_mod

        p_wiz = sub.add_parser(
            "wizard", help="Interactive assistant that suggests/runs CLI commands"
        )
        _wizard_mod.register_cli(p_wiz)
    elif first_non_flag == "generate-manifest":
        # Developer utility to generate capabilities manifest
        from zyra.connectors import discovery as _discovery_mod
        from zyra.wizard.manifest import save_manifest as _save_manifest

        p_gen = sub.add_parser(
            "generate-manifest", help="Generate capabilities JSON manifest"
        )
        p_gen.add_argument(
            "-o",
            "--output",
            default=str(Path(__file__).parent / "wizard" / "zyra_capabilities.json"),
            help="Output path for capabilities manifest JSON",
        )

        def _cmd_gen(ns: argparse.Namespace) -> int:
            _save_manifest(ns.output)
            print(ns.output)
            return 0

        p_gen.set_defaults(func=_cmd_gen)
    else:
        # Fallback: register the full CLI tree when we cannot infer the target
        import zyra.decide as _decide_mod
        import zyra.narrate as _narrate_mod
        import zyra.simulate as _simulate_mod
        import zyra.transform as _transform_mod
        from zyra import processing as _process_mod
        from zyra import wizard as _wizard_mod
        from zyra.connectors import discovery as _discovery_mod
        from zyra.connectors import egress as _egress_mod
        from zyra.connectors import ingest as _ingest_mod
        from zyra.visualization import cli_register as _visual_mod
        from zyra.wizard.manifest import save_manifest as _save_manifest

        p_acq = sub.add_parser(
            "acquire", help="Acquire/ingest data from sources (alias: import/ingest)"
        )
        acq_sub = p_acq.add_subparsers(dest="acquire_cmd", required=True)
        _ingest_mod.register_cli(acq_sub)
        # Alias: import → acquire
        p_acq_alias = sub.add_parser("import", help=argparse.SUPPRESS)
        acq_alias_sub = p_acq_alias.add_subparsers(dest="acquire_cmd", required=True)
        _ingest_mod.register_cli(acq_alias_sub)

        p_proc = sub.add_parser(
            "process", help="Processing commands (GRIB/NetCDF/GeoTIFF) + transforms"
        )
        proc_sub = p_proc.add_subparsers(dest="process_cmd", required=True)
        # Combine transform commands under process group
        _process_mod.register_cli(proc_sub)
        _transform_mod.register_cli(proc_sub)

        p_viz = sub.add_parser(
            "visualize",
            help="Visualization commands (static/interactive/animation) (alias: render)",
        )
        viz_sub = p_viz.add_subparsers(dest="visualize_cmd", required=True)
        _visual_mod.register_cli(viz_sub)
        # Alias: render → visualize
        p_viz_alias = sub.add_parser("render", help=argparse.SUPPRESS)
        viz_alias_sub = p_viz_alias.add_subparsers(dest="visualize_cmd", required=True)
        _visual_mod.register_cli(viz_alias_sub)

        p_disseminate = sub.add_parser(
            "disseminate",
            help="Write/egress data to destinations (alias: export; legacy: decimate)",
        )
        dis_sub = p_disseminate.add_subparsers(dest="disseminate_cmd", required=True)
        _egress_mod.register_cli(dis_sub)
        # Aliases: export/decimate → disseminate
        p_export = sub.add_parser("export", help=argparse.SUPPRESS)
        exp_sub = p_export.add_subparsers(dest="disseminate_cmd", required=True)
        _egress_mod.register_cli(exp_sub)
        p_dec_alias = sub.add_parser("decimate", help=argparse.SUPPRESS)
        dec_alias_sub = p_dec_alias.add_subparsers(
            dest="disseminate_cmd", required=True
        )
        _egress_mod.register_cli(dec_alias_sub)

        p_tr = sub.add_parser("transform", help="Transform helpers (metadata, etc.)")
        tr_sub = p_tr.add_subparsers(dest="transform_cmd", required=True)
        _transform_mod.register_cli(tr_sub)

        # New skeleton groups: simulate/decide/narrate
        p_sim = sub.add_parser("simulate", help="Simulate under uncertainty (skeleton)")
        sim_sub = p_sim.add_subparsers(dest="simulate_cmd", required=True)
        _simulate_mod.register_cli(sim_sub)

        p_dec = sub.add_parser("decide", help="Decision/optimization (skeleton)")
        dec_sub2 = p_dec.add_subparsers(dest="decide_cmd", required=True)
        _decide_mod.register_cli(dec_sub2)

        p_nar = sub.add_parser("narrate", help="Narrate/report (skeleton)")
        nar_sub = p_nar.add_subparsers(dest="narrate_cmd", required=True)
        _narrate_mod.register_cli(nar_sub)

        # Wizard (single command, no subcommands)
        p_wiz = sub.add_parser(
            "wizard", help="Interactive assistant that suggests/runs CLI commands"
        )
        _wizard_mod.register_cli(p_wiz)

        # Verify stage
        import zyra.verify as _verify_mod

        p_ver = sub.add_parser(
            "verify", help="Evaluation/metrics/validation (skeleton)"
        )
        ver_sub = p_ver.add_subparsers(dest="verify_cmd", required=True)
        _verify_mod.register_cli(ver_sub)

        # Search (single command)
        p_search = sub.add_parser(
            "search", help="Search datasets (local SOS catalog; JSON/YAML export)"
        )
        _discovery_mod.register_cli(p_search)

        # Generate-manifest
        p_gen = sub.add_parser(
            "generate-manifest", help="Generate capabilities JSON manifest"
        )
        p_gen.add_argument(
            "-o",
            "--output",
            default=str(Path(__file__).parent / "wizard" / "zyra_capabilities.json"),
            help="Output path for capabilities manifest JSON",
        )

        def _cmd_gen(ns: argparse.Namespace) -> int:
            _save_manifest(ns.output)
            print(ns.output)
            return 0

        p_gen.set_defaults(func=_cmd_gen)

        # No separate workflow group; use `zyra run` for workflows

    args = parser.parse_args(args_list)
    # Apply global verbosity to environment so downstream modules pick it up
    # Deprecation notice for legacy 'decimate' and 'transform' groups
    try:
        import warnings

        cmd = getattr(args, "cmd", None)
        if cmd == "decimate":
            warnings.warn(
                "'decimate' is deprecated; use 'export' or 'disseminate'",
                category=UserWarning,
                stacklevel=1,
            )
        if cmd == "transform":
            warnings.warn(
                "'transform' is merged into 'process'; use 'process'",
                category=UserWarning,
                stacklevel=1,
            )
    except Exception:
        pass
    if getattr(args, "verbose", False):
        os.environ["ZYRA_VERBOSITY"] = "debug"
        os.environ["DATAVIZHUB_VERBOSITY"] = "debug"
    elif getattr(args, "quiet", False):
        os.environ["ZYRA_VERBOSITY"] = "quiet"
        os.environ["DATAVIZHUB_VERBOSITY"] = "quiet"
    else:
        os.environ.setdefault("ZYRA_VERBOSITY", "info")
        os.environ.setdefault("DATAVIZHUB_VERBOSITY", "info")
    # Configure logging based on env verbosity (idempotent)
    try:
        from zyra.utils.cli_helpers import configure_logging_from_env as _cfg_log

        _cfg_log(default=os.environ.get("ZYRA_VERBOSITY", "info"))
    except Exception:
        pass
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
