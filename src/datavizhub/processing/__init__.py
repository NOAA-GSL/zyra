from .base import DataProcessor
from .video_processor import VideoProcessor
from .grib_data_processor import GRIBDataProcessor, interpolate_time_steps
from .grib_utils import (
    DecodedGRIB,
    VariableNotFoundError,
    grib_decode,
    extract_variable,
    convert_to_format,
    validate_subset,
    extract_metadata,
)
from .netcdf_data_processor import (
    load_netcdf,
    subset_netcdf,
    convert_to_grib2,
)

__all__ = [
    "DataProcessor",
    "VideoProcessor",
    "GRIBDataProcessor",
    "interpolate_time_steps",
    "DecodedGRIB",
    "VariableNotFoundError",
    "grib_decode",
    "extract_variable",
    "convert_to_format",
    "validate_subset",
    "extract_metadata",
    "load_netcdf",
    "subset_netcdf",
    "convert_to_grib2",
]

# ---- CLI registration ---------------------------------------------------------------

from typing import Any
import sys


def register_cli(subparsers: Any) -> None:
    """Register processing subcommands under a provided subparsers object.

    Adds: decode-grib2, extract-variable, convert-format
    """
    import argparse

    from datavizhub.utils.cli_helpers import read_all_bytes as _read_bytes, is_netcdf_bytes

    def cmd_decode_grib2(args: argparse.Namespace) -> int:
        from datavizhub.utils.cli_helpers import configure_logging_from_env
        configure_logging_from_env()
        from datavizhub.processing import grib_decode
        from datavizhub.processing.grib_utils import extract_metadata

        data = _read_bytes(args.file_or_url)
        if getattr(args, "raw", False):
            sys.stdout.buffer.write(data)
            return 0
        decoded = grib_decode(data, backend=args.backend)
        meta = extract_metadata(decoded)
        import logging
        logging.info(str(meta))
        return 0

    def cmd_extract_variable(args: argparse.Namespace) -> int:
        from datavizhub.utils.cli_helpers import configure_logging_from_env
        configure_logging_from_env()
        import shutil
        import subprocess
        import tempfile

        from datavizhub.processing import grib_decode
        from datavizhub.processing.grib_utils import (
            extract_variable,
            VariableNotFoundError,
            convert_to_format,
        )

        data = _read_bytes(args.file_or_url)
        if getattr(args, "stdout", False):
            out_fmt = (args.format or "netcdf").lower()
            if out_fmt not in ("netcdf", "grib2"):
                raise SystemExit("Unsupported --format for extract-variable: use 'netcdf' or 'grib2'")
            wgrib2 = shutil.which("wgrib2")
            if wgrib2 is not None:
                fd, in_path = tempfile.mkstemp(suffix=".grib2")
                try:
                    with open(fd, "wb", closefd=False) as f:
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
                        if res.returncode == 0:
                            with open(out_path, "rb") as f:
                                sys.stdout.buffer.write(f.read())
                            return 0
                    finally:
                        try:
                            import os
                            os.remove(out_path)
                        except Exception:
                            pass
                finally:
                    try:
                        import os
                        os.remove(in_path)
                    except Exception:
                        pass
            decoded = grib_decode(data, backend=args.backend)
            if out_fmt == "netcdf":
                out_bytes = convert_to_format(decoded, "netcdf", var=args.pattern)
                sys.stdout.buffer.write(out_bytes)
                return 0
            try:
                var_obj = extract_variable(decoded, args.pattern)
            except VariableNotFoundError as exc:
                import logging
                logging.error(str(exc))
                return 2
            try:
                import xarray as xr  # type: ignore
                from datavizhub.processing.netcdf_data_processor import convert_to_grib2

                ds = var_obj.to_dataset(name=getattr(var_obj, "name", "var")) if hasattr(var_obj, "to_dataset") else None
                if ds is None:
                    import logging
                    logging.error("Selected variable cannot be converted to GRIB2 without wgrib2")
                    return 2
                grib_bytes = convert_to_grib2(ds)
                sys.stdout.buffer.write(grib_bytes)
                return 0
            except Exception as exc:
                import logging
                logging.error(f"GRIB2 conversion failed: {exc}")
                return 2

        decoded = grib_decode(data, backend=args.backend)
        try:
            var = extract_variable(decoded, args.pattern)
        except VariableNotFoundError as exc:
            import logging
            logging.error(str(exc))
            return 2
        try:
            name = getattr(var, "name", None) or getattr(getattr(var, "attrs", {}), "get", lambda *_: None)("long_name")
        except Exception:
            name = None
        import logging
        logging.info(f"Matched variable: {name or args.pattern}")
        return 0

    def cmd_convert_format(args: argparse.Namespace) -> int:
        from datavizhub.utils.cli_helpers import configure_logging_from_env
        configure_logging_from_env()
        from datavizhub.processing import grib_decode
        from datavizhub.processing.grib_utils import convert_to_format

        data = _read_bytes(args.file_or_url)
        # If reading NetCDF and writing NetCDF with --stdout, pass-through
        if getattr(args, "stdout", False) and args.format == "netcdf":
            if is_netcdf_bytes(data):
                sys.stdout.buffer.write(data)
                return 0
        # Otherwise, decode and convert based on requested format
        decoded = grib_decode(data, backend=args.backend)
        out_bytes = convert_to_format(decoded, args.format, var=getattr(args, "var", None))
        if getattr(args, "stdout", False):
            sys.stdout.buffer.write(out_bytes)
            return 0
        if not args.output:
            raise SystemExit("--output is required when not using --stdout")
        with open(args.output, "wb") as f:
            f.write(out_bytes)
        import logging
        logging.info(args.output)
        return 0

    p_dec = subparsers.add_parser("decode-grib2", help="Decode GRIB2 and print metadata")
    p_dec.add_argument("file_or_url")
    p_dec.add_argument("--backend", default="cfgrib", choices=["cfgrib", "pygrib", "wgrib2"])
    p_dec.add_argument("--pattern", help="Regex for .idx-based subsetting when using HTTP/S3")
    p_dec.add_argument("--unsigned", action="store_true", help="Use unsigned S3 access for public buckets")
    p_dec.add_argument("--raw", action="store_true", help="Emit raw (optionally .idx-subset) GRIB2 bytes to stdout")
    p_dec.set_defaults(func=cmd_decode_grib2)

    p_ext = subparsers.add_parser("extract-variable", help="Extract a variable using a regex pattern")
    p_ext.add_argument("file_or_url")
    p_ext.add_argument("pattern")
    p_ext.add_argument("--backend", default="cfgrib", choices=["cfgrib", "pygrib", "wgrib2"])
    p_ext.add_argument("--stdout", action="store_true", help="Write selected variable as bytes to stdout")
    p_ext.add_argument("--format", default="netcdf", choices=["netcdf", "grib2"], help="Output format for --stdout")
    p_ext.set_defaults(func=cmd_extract_variable)

    p_conv = subparsers.add_parser("convert-format", help="Convert decoded data to a format")
    p_conv.add_argument("file_or_url")
    p_conv.add_argument("format", choices=["netcdf", "geotiff"])  # bytes outputs
    p_conv.add_argument("-o", "--output", dest="output")
    p_conv.add_argument("--stdout", action="store_true", help="Write binary output to stdout instead of a file")
    p_conv.add_argument("--backend", default="cfgrib", choices=["cfgrib", "pygrib", "wgrib2"])
    p_conv.add_argument("--var", help="Variable name or regex for multi-var datasets")
    p_conv.add_argument("--pattern", help="Regex for .idx-based subsetting when using HTTP/S3")
    p_conv.add_argument("--unsigned", action="store_true", help="Use unsigned S3 access for public buckets")
    p_conv.set_defaults(func=cmd_convert_format)
