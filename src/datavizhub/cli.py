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
                        print(res.stderr.strip() or "wgrib2 subsetting failed", file=sys.stderr)
                        return 2
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
    from datavizhub.processing import grib_decode
    from datavizhub.processing.grib_utils import convert_to_format, DecodedGRIB

    if not args.output and not args.stdout:
        raise SystemExit("--output or --stdout is required for convert-format")

    data = _read_bytes(args.file_or_url, idx_pattern=args.pattern, unsigned=args.unsigned)

    # Detect input type: GRIB2 vs NetCDF (classic CDF or HDF5-based NetCDF4)
    decoded = None
    try:
        if data.startswith(b"GRIB"):
            decoded = grib_decode(data, backend=args.backend)
        elif data.startswith(b"\x89HDF\r\n\x1a\n") or data.startswith(b"CDF"):
            # Load NetCDF and wrap as DecodedGRIB-like for reuse of conversion
            from datavizhub.processing.netcdf_data_processor import load_netcdf

            ds = load_netcdf(data)
            decoded = DecodedGRIB(backend="cfgrib", dataset=ds)  # reuse xarray-based conversions
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

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
