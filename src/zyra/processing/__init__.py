# SPDX-License-Identifier: Apache-2.0
from .base import DataProcessor

# Optional: GRIB utilities rely on optional deps like pygrib/cfgrib. Keep import lazy-safe.
try:
    from .grib_data_processor import GRIBDataProcessor, interpolate_time_steps
except (ImportError, ModuleNotFoundError):
    # pygrib/scipy/siphon may be unavailable in minimal environments; expose
    # GRIBDataProcessor only when its dependencies are installed.
    GRIBDataProcessor = None  # type: ignore[assignment]
    interpolate_time_steps = None  # type: ignore[assignment]
from .grib_utils import (
    DecodedGRIB,
    VariableNotFoundError,
    convert_to_format,
    extract_metadata,
    extract_variable,
    grib_decode,
    validate_subset,
)
from .netcdf_data_processor import (
    convert_to_grib2,
    load_netcdf,
    subset_netcdf,
)
from .pad_missing import pad_missing_frames
from .video_processor import VideoProcessor
from .video_transcode import (
    VideoTranscoder,
    normalise_extra_args,
    run_video_transcode,
)

__all__ = [
    "DataProcessor",
    "VideoProcessor",
    "VideoTranscoder",
    "run_video_transcode",
    "normalise_extra_args",
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
    "pad_missing_frames",
]
# Only export GRIBDataProcessor helpers when optional deps are present
if GRIBDataProcessor is not None and interpolate_time_steps is not None:
    __all__ += ["GRIBDataProcessor", "interpolate_time_steps"]

# ---- CLI registration ---------------------------------------------------------------

import copy
import csv
import io
import json
import sys
from typing import Any


def register_cli(subparsers: Any) -> None:
    """Register processing subcommands under a provided subparsers object.

    Adds: decode-grib2, extract-variable, convert-format
    """
    import argparse

    from zyra.utils.cli_helpers import (
        is_netcdf_bytes,
    )
    from zyra.utils.cli_helpers import (
        read_all_bytes as _read_bytes,
    )

    def cmd_decode_grib2(args: argparse.Namespace) -> int:
        # Per-command verbosity/trace mapping
        import os

        from zyra.utils.cli_helpers import configure_logging_from_env

        if getattr(args, "verbose", False):
            os.environ["ZYRA_VERBOSITY"] = "debug"
        elif getattr(args, "quiet", False):
            os.environ["ZYRA_VERBOSITY"] = "quiet"
        if getattr(args, "trace", False):
            os.environ["ZYRA_SHELL_TRACE"] = "1"
        configure_logging_from_env()
        # Read input bytes first so missing-file errors surface quickly without
        # importing heavy GRIB dependencies. Only import decoders when needed.
        #
        # Deferred heavy imports
        # ----------------------
        # The GRIB decode path pulls in optional stacks (cfgrib/pygrib, eccodes
        # bindings, etc.). Importing those libraries can be relatively slow and
        # noisy in minimal environments. To keep "missing file"/"--raw" cases
        # fast and to avoid importing heavy modules unnecessarily, we load the
        # decoder utilities only after we've successfully read the input bytes
        # and determined that we actually need to decode.
        data = _read_bytes(args.file_or_url)
        import logging

        if os.environ.get("ZYRA_SHELL_TRACE"):
            logging.info("+ input='%s'", args.file_or_url)
            logging.info("+ backend=%s", args.backend)
        if getattr(args, "raw", False):
            sys.stdout.buffer.write(data)
            return 0
        # Lazy-import after successful read (see note above)
        from zyra.processing import grib_decode
        from zyra.processing.grib_utils import extract_metadata

        decoded = grib_decode(data, backend=args.backend)
        meta = extract_metadata(decoded)
        logging.info(str(meta))
        return 0

    def cmd_extract_variable(args: argparse.Namespace) -> int:
        import os

        from zyra.utils.cli_helpers import configure_logging_from_env

        if getattr(args, "verbose", False):
            os.environ["ZYRA_VERBOSITY"] = "debug"
        elif getattr(args, "quiet", False):
            os.environ["ZYRA_VERBOSITY"] = "quiet"
        if getattr(args, "trace", False):
            os.environ["ZYRA_SHELL_TRACE"] = "1"
        configure_logging_from_env()
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
        if getattr(args, "stdout", False):
            out_fmt = (args.format or "netcdf").lower()
            if out_fmt not in ("netcdf", "grib2"):
                raise SystemExit(
                    "Unsupported --format for extract-variable: use 'netcdf' or 'grib2'"
                )
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
                        if os.environ.get("ZYRA_SHELL_TRACE"):
                            import logging as _log

                            _log.info("+ %s", " ".join(args_list))
                        res = subprocess.run(
                            args_list, capture_output=True, text=True, check=False
                        )
                        if res.returncode == 0:
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
                from zyra.processing.netcdf_data_processor import convert_to_grib2

                ds = (
                    var_obj.to_dataset(name=getattr(var_obj, "name", "var"))
                    if hasattr(var_obj, "to_dataset")
                    else None
                )
                if ds is None:
                    import logging

                    logging.error(
                        "Selected variable cannot be converted to GRIB2 without wgrib2"
                    )
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
            name = getattr(var, "name", None) or getattr(
                getattr(var, "attrs", {}), "get", lambda *_: None
            )("long_name")
        except Exception:
            name = None
        import logging

        logging.info(f"Matched variable: {name or args.pattern}")
        return 0

    def cmd_convert_format(args: argparse.Namespace) -> int:
        import os

        from zyra.utils.cli_helpers import configure_logging_from_env

        if getattr(args, "verbose", False):
            os.environ["ZYRA_VERBOSITY"] = "debug"
        elif getattr(args, "quiet", False):
            os.environ["ZYRA_VERBOSITY"] = "quiet"
        if getattr(args, "trace", False):
            os.environ["ZYRA_SHELL_TRACE"] = "1"
        configure_logging_from_env()

        # Multi-input support: --inputs with --output-dir required
        if getattr(args, "inputs", None):
            if getattr(args, "stdout", False):
                raise SystemExit(
                    "--stdout is not supported with --inputs (use --output-dir)"
                )
            outdir = getattr(args, "output_dir", None)
            if not outdir:
                raise SystemExit("--output-dir is required when using --inputs")
            import logging
            from pathlib import Path

            from zyra.processing import grib_decode
            from zyra.processing.grib_utils import convert_to_format

            outdir_p = Path(outdir)
            outdir_p.mkdir(parents=True, exist_ok=True)
            wrote = []
            for src in args.inputs:
                data = _read_bytes(src)
                # Fast-path: NetCDF passthrough when converting to NetCDF
                if args.format == "netcdf" and is_netcdf_bytes(data):
                    # Write source name with .nc extension
                    base = Path(str(src)).stem
                    dest = outdir_p / f"{base}.nc"
                    dest.write_bytes(data)
                    logging.info(str(dest))
                    wrote.append(str(dest))
                    continue
                decoded = grib_decode(data, backend=args.backend)
                out_bytes = convert_to_format(
                    decoded, args.format, var=getattr(args, "var", None)
                )
                # Choose extension by format
                ext = ".nc" if args.format == "netcdf" else ".tif"
                base = Path(str(src)).stem
                dest = outdir_p / f"{base}{ext}"
                with dest.open("wb") as f:
                    f.write(out_bytes)
                logging.info(str(dest))
                wrote.append(str(dest))
            # Print a simple JSON list of outputs for convenience
            try:
                import json

                print(json.dumps({"outputs": wrote}))
            except Exception:
                pass
            return 0

        # Single-input flow
        # Read input first so we can short-circuit pass-through without heavy imports
        data = _read_bytes(args.file_or_url)
        # If reading NetCDF and writing NetCDF with --stdout, pass-through
        if (
            getattr(args, "stdout", False)
            and args.format == "netcdf"
            and is_netcdf_bytes(data)
        ):
            sys.stdout.buffer.write(data)
            return 0

        # Otherwise, decode and convert based on requested format
        # Lazy-import heavy GRIB dependencies only when needed
        from zyra.processing import grib_decode
        from zyra.processing.grib_utils import convert_to_format

        decoded = grib_decode(data, backend=args.backend)
        out_bytes = convert_to_format(
            decoded, args.format, var=getattr(args, "var", None)
        )
        if getattr(args, "stdout", False):
            sys.stdout.buffer.write(out_bytes)
            return 0
        if not args.output:
            raise SystemExit("--output is required when not using --stdout")
        from pathlib import Path as _P

        with _P(args.output).open("wb") as f:
            f.write(out_bytes)
        import logging

        logging.info(args.output)
        return 0

    def cmd_pad_missing(args: argparse.Namespace) -> int:
        import logging
        import os

        from zyra.utils.cli_helpers import configure_logging_from_env

        if getattr(args, "verbose", False):
            os.environ["ZYRA_VERBOSITY"] = "debug"
        elif getattr(args, "quiet", False):
            os.environ["ZYRA_VERBOSITY"] = "quiet"
        if getattr(args, "trace", False):
            os.environ["ZYRA_SHELL_TRACE"] = "1"
        configure_logging_from_env()
        try:
            source = getattr(args, "frames_meta", None) or "-"
            created = pad_missing_frames(
                source,
                output_dir=args.output_dir,
                fill_mode=args.fill_mode,
                basemap=getattr(args, "basemap", None),
                indicator=getattr(args, "indicator", None),
                overwrite=bool(getattr(args, "overwrite", False)),
                dry_run=bool(getattr(args, "dry_run", False)),
                json_report=getattr(args, "json_report", None),
                read_stdin=bool(getattr(args, "read_frames_meta_stdin", False)),
            )
        except Exception as exc:
            logging.error(str(exc))
            return 2
        for path in created:
            try:
                print(path)
            except Exception:
                logging.debug("Created frame: %s", path)
        return 0

    # ---- api-json processor helpers ----
    from zyra.utils.json_tools import get_by_path as _get_by_path

    def _flatten(obj: Any, prefix: str = "", out: dict | None = None) -> dict:
        out = out or {}
        if isinstance(obj, dict):
            for k, v in obj.items():
                key = f"{prefix}.{k}" if prefix else k
                _flatten(v, key, out)
        elif isinstance(obj, list):
            out[prefix] = obj
        else:
            out[prefix] = obj
        return out

    def _explode(rows: list[dict], path: str) -> list[dict]:
        out_rows: list[dict] = []
        for r in rows:
            val = _get_by_path(r, path)
            if isinstance(val, list) and val:
                for item in val:
                    # Deep-copy the row so each exploded item is independent
                    nr = copy.deepcopy(r)
                    parts = path.split(".")
                    cur = nr
                    for p in parts[:-1]:
                        cur = cur.get(p, {})
                    cur[parts[-1]] = item
                    out_rows.append(nr)
            else:
                out_rows.append(r)
        return out_rows

    def _has_path(obj: dict, path: str) -> bool:
        cur = obj
        for part in (path or "").split(".") if path else []:
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                return False
        return True

    def _project(
        row: dict, fields: list[str] | None, flatten: bool, *, strict: bool = False
    ) -> dict:
        if not fields:
            return _flatten(row) if flatten else row
        out_map: dict = {}
        if flatten:
            src = _flatten(row)
            for f in fields:
                if f in src:
                    out_map[f] = src.get(f)
                else:
                    if strict:
                        raise SystemExit(f"Missing required field: {f}")
                    out_map[f] = ""
        else:
            for f in fields:
                if _has_path(row, f):
                    out_map[f] = _get_by_path(row, f)
                else:
                    if strict:
                        raise SystemExit(f"Missing required field: {f}")
                    out_map[f] = ""
        return out_map

    def _derive(row: dict, which: list[str]) -> dict:
        res = {}
        if "word_count" in which:
            text = row.get("text") or _get_by_path(row, "message.text") or ""
            res["word_count"] = (
                len([w for w in text.split() if isinstance(text, str)])
                if isinstance(text, str)
                else 0
            )
        if "sentence_count" in which:
            text2 = row.get("text") or _get_by_path(row, "message.text") or ""
            if isinstance(text2, str) and text2:
                res["sentence_count"] = max(1, sum(1 for ch in text2 if ch in ".!?"))
            else:
                res["sentence_count"] = 0
        if "tool_calls_count" in which:
            val = row.get("toolCalls") or _get_by_path(row, "message.toolCalls")
            res["tool_calls_count"] = len(val) if isinstance(val, list) else 0
        return res

    def cmd_api_json(args: argparse.Namespace) -> int:
        from zyra.utils.cli_helpers import read_all_bytes as _read_bytes
        from zyra.utils.io_utils import open_output as _open_output

        raw = _read_bytes(args.file_or_url)
        text = raw.decode("utf-8")

        def _try_parse_json(s: str):
            try:
                return json.loads(s)
            except Exception:
                return None

        # Apply preset defaults
        if (
            getattr(args, "preset", None) == "limitless-lifelogs"
            and not args.records_path
        ):
            args.records_path = "data.lifelogs"

        records: list[dict] = []
        # JSONL/NDJSON detection and parsing
        lines = [ln for ln in text.splitlines() if ln.strip()]
        if lines and all(
            ln.strip().startswith("{") for ln in lines[: min(3, len(lines))]
        ):
            objs = [
                o
                for o in (_try_parse_json(ln) for ln in lines)
                if isinstance(o, (dict, list))
            ]
            if len(objs) > 1:
                if args.records_path:
                    for page in objs:
                        page_obj = page
                        if isinstance(page, list):
                            # already records
                            records.extend([r for r in page if isinstance(r, dict)])
                        else:
                            recs = _get_by_path(page_obj, args.records_path)
                            if isinstance(recs, list):
                                records.extend([r for r in recs if isinstance(r, dict)])
                else:
                    for obj in objs:
                        if isinstance(obj, dict):
                            records.append(obj)

        if not records:
            root = _try_parse_json(text)
            if isinstance(root, list):
                records = [r for r in root if isinstance(r, dict)]
            elif isinstance(root, dict):
                source = (
                    _get_by_path(root, args.records_path) if args.records_path else root
                )
                if isinstance(source, list):
                    records = [r for r in source if isinstance(r, dict)]
                else:
                    records = [source]

        # Explode arrays
        for path in args.explode or []:
            records = _explode(records, path)

        # Projection + derived
        field_list = args.fields.split(",") if args.fields else None
        derived_list = args.derived.split(",") if args.derived else []
        out_rows = []
        for r in records:
            base = _project(
                r, field_list, args.flatten, strict=bool(getattr(args, "strict", False))
            )
            base.update(_derive(base if args.flatten else r, derived_list))
            out_rows.append(base)

        with _open_output(args.output) as f:
            if args.format == "jsonl":
                for row in out_rows:
                    f.write(
                        (json.dumps(row, ensure_ascii=False) + "\n").encode("utf-8")
                    )
                return 0
            # CSV
            if field_list:
                headers = list(field_list)
            else:
                # Use a stable union of keys across all rows when fields are not provided.
                # This avoids empty headers when the first row is sparse.
                hdr_set: set[str] = set()
                for row in out_rows:
                    try:
                        hdr_set.update(k for k in row if isinstance(k, str))
                    except Exception:
                        continue
                headers = sorted(hdr_set)
            headers = headers + [d for d in derived_list if d not in headers]
            # csv expects a text file-like; ensure we pass the underlying handle if possible
            handle = getattr(f, "_file", None)
            if handle is None:
                # Fallback: write to string buffer then encode
                buf = io.StringIO()
                w = csv.DictWriter(buf, fieldnames=headers, extrasaction="ignore")
                w.writeheader()
                for row in out_rows:
                    norm = {
                        k: (
                            json.dumps(v, ensure_ascii=False)
                            if isinstance(v, (list, dict))
                            else v
                        )
                        for k, v in row.items()
                    }
                    w.writerow(norm)
                f.write(buf.getvalue().encode("utf-8"))
            else:
                w = csv.DictWriter(handle, fieldnames=headers, extrasaction="ignore")
                w.writeheader()
                for row in out_rows:
                    norm = {
                        k: (
                            json.dumps(v, ensure_ascii=False)
                            if isinstance(v, (list, dict))
                            else v
                        )
                        for k, v in row.items()
                    }
                    w.writerow(norm)
        return 0

    p_dec = subparsers.add_parser(
        "decode-grib2",
        help="Decode GRIB2 and print metadata",
        description=(
            "Decode a GRIB2 file or URL using cfgrib/pygrib/wgrib2 and log basic metadata. "
            "Optionally emit raw bytes (with optional .idx subset) to stdout."
        ),
    )
    p_dec.add_argument("file_or_url")
    p_dec.add_argument(
        "--backend", default="cfgrib", choices=["cfgrib", "pygrib", "wgrib2"]
    )
    p_dec.add_argument(
        "--pattern", help="Regex for .idx-based subsetting when using HTTP/S3"
    )
    p_dec.add_argument(
        "--unsigned",
        action="store_true",
        help="Use unsigned S3 access for public buckets",
    )
    p_dec.add_argument(
        "--raw",
        action="store_true",
        help="Emit raw (optionally .idx-subset) GRIB2 bytes to stdout",
    )
    p_dec.add_argument(
        "--verbose", action="store_true", help="Verbose logging for this command"
    )
    p_dec.add_argument(
        "--quiet", action="store_true", help="Quiet logging for this command"
    )
    p_dec.add_argument(
        "--trace",
        action="store_true",
        help="Shell-style trace of key steps and external commands",
    )
    p_dec.set_defaults(func=cmd_decode_grib2)

    p_ext = subparsers.add_parser(
        "extract-variable",
        help="Extract a variable using a regex pattern",
        description=(
            "Extract a variable from GRIB2 by regex pattern. Output selected variable as NetCDF/GRIB2 "
            "to stdout when requested, or log the matched variable name."
        ),
    )
    p_ext.add_argument("file_or_url")
    p_ext.add_argument("pattern")
    p_ext.add_argument(
        "--backend", default="cfgrib", choices=["cfgrib", "pygrib", "wgrib2"]
    )
    p_ext.add_argument(
        "--stdout",
        action="store_true",
        help="Write selected variable as bytes to stdout",
    )
    p_ext.add_argument(
        "--format",
        default="netcdf",
        choices=["netcdf", "grib2"],
        help="Output format for --stdout",
    )
    p_ext.add_argument(
        "--verbose", action="store_true", help="Verbose logging for this command"
    )
    p_ext.add_argument(
        "--quiet", action="store_true", help="Quiet logging for this command"
    )
    p_ext.add_argument(
        "--trace",
        action="store_true",
        help="Shell-style trace of key steps and external commands",
    )
    p_ext.set_defaults(func=cmd_extract_variable)

    p_conv = subparsers.add_parser(
        "convert-format",
        help="Convert decoded data to a format",
        description=(
            "Convert decoded GRIB2 data to NetCDF or GeoTIFF. Supports single input or batch via --inputs."
        ),
    )
    p_conv.add_argument(
        "file_or_url", nargs="?", help="Single input when not using --inputs"
    )
    p_conv.add_argument("format", choices=["netcdf", "geotiff"])  # bytes outputs
    p_conv.add_argument("-o", "--output", dest="output")
    p_conv.add_argument(
        "--stdout",
        action="store_true",
        help="Write binary output to stdout instead of a file",
    )
    # Multi-input support
    p_conv.add_argument("--inputs", nargs="+", help="Multiple input paths or URLs")
    p_conv.add_argument(
        "--output-dir",
        dest="output_dir",
        help="Directory to write outputs for --inputs",
    )
    p_conv.add_argument(
        "--backend", default="cfgrib", choices=["cfgrib", "pygrib", "wgrib2"]
    )
    p_conv.add_argument("--var", help="Variable name or regex for multi-var datasets")
    p_conv.add_argument(
        "--pattern", help="Regex for .idx-based subsetting when using HTTP/S3"
    )
    p_conv.add_argument(
        "--unsigned",
        action="store_true",
        help="Use unsigned S3 access for public buckets",
    )
    p_conv.add_argument(
        "--verbose", action="store_true", help="Verbose logging for this command"
    )
    p_conv.add_argument(
        "--quiet", action="store_true", help="Quiet logging for this command"
    )
    p_conv.add_argument(
        "--trace",
        action="store_true",
        help="Shell-style trace of key steps and external commands",
    )
    p_conv.set_defaults(func=cmd_convert_format)

    p_pad = subparsers.add_parser(
        "pad-missing",
        help="Fill missing frames using metadata output",
        description=(
            "Read frames metadata JSON from 'transform metadata/scan-frames' and generate placeholder images "
            "for each missing timestamp using blank, solid color, basemap, or nearest-frame strategies."
        ),
    )
    meta_source = p_pad.add_mutually_exclusive_group(required=True)
    meta_source.add_argument(
        "--frames-meta",
        dest="frames_meta",
        help="Path to frames metadata JSON (from transform metadata/scan-frames)",
    )
    meta_source.add_argument(
        "--read-frames-meta-stdin",
        dest="read_frames_meta_stdin",
        action="store_true",
        help="Read frames metadata JSON from stdin",
    )
    p_pad.add_argument(
        "--output-dir",
        dest="output_dir",
        required=True,
        help="Directory where placeholder frames will be written",
    )
    p_pad.add_argument(
        "--fill-mode",
        dest="fill_mode",
        default="blank",
        choices=["blank", "solid", "basemap", "nearest"],
        help="Strategy for filling gaps (default: blank)",
    )
    p_pad.add_argument(
        "--basemap",
        help="Basemap image, package reference, or color (solid/basemap modes)",
    )
    p_pad.add_argument(
        "--indicator",
        help="Optional overlay indicator, e.g., watermark:MISSING or badge:pkg:...",
    )
    p_pad.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing files when output paths already exist",
    )
    p_pad.add_argument(
        "--dry-run",
        action="store_true",
        help="Report planned outputs without writing files",
    )
    p_pad.add_argument(
        "--json-report",
        dest="json_report",
        help="Optional path to write a JSON summary report",
    )
    p_pad.add_argument(
        "--verbose", action="store_true", help="Verbose logging for this command"
    )
    p_pad.add_argument(
        "--quiet", action="store_true", help="Quiet logging for this command"
    )
    p_pad.add_argument(
        "--trace",
        action="store_true",
        help="Shell-style trace of key steps and external commands",
    )
    p_pad.set_defaults(func=cmd_pad_missing)

    # api-json
    p_api_json = subparsers.add_parser(
        "api-json",
        help="Transform API JSON/NDJSON into CSV/JSONL (select, flatten, explode)",
        description=(
            "Read a JSON or NDJSON file/stream, select fields via dot paths, optionally flatten nested objects, "
            "explode arrays into multiple rows, and write CSV or JSONL."
        ),
    )
    p_api_json.add_argument("file_or_url")
    p_api_json.add_argument(
        "--records-path",
        dest="records_path",
        help="Dot path to array of records (e.g., data.lifelogs or data.chat.messages)",
    )
    p_api_json.add_argument(
        "--preset",
        choices=["limitless-lifelogs"],
        help="Apply provider-specific defaults (e.g., Limitless lifelogs records path)",
    )
    p_api_json.add_argument(
        "--fields",
        help="Comma-separated field list (dot paths). If omitted, use first row keys",
    )
    p_api_json.add_argument(
        "--flatten", action="store_true", help="Flatten nested objects"
    )
    p_api_json.add_argument(
        "--explode",
        action="append",
        help="Repeatable: dot path to array to explode into multiple rows",
    )
    p_api_json.add_argument(
        "--derived",
        help="Comma-separated derived columns: word_count,sentence_count,tool_calls_count",
    )
    p_api_json.add_argument(
        "--format", choices=["csv", "jsonl"], default="csv", help="Output format"
    )
    p_api_json.add_argument(
        "--strict",
        action="store_true",
        help="Error on missing fields instead of emitting empty strings",
    )
    p_api_json.add_argument(
        "--output", default="-", help="Output file path or '-' for stdout"
    )
    p_api_json.set_defaults(func=cmd_api_json)

    # video-transcode (ffmpeg wrapper for modern and legacy outputs)
    def cmd_video_transcode(args: argparse.Namespace) -> int:
        import os

        from zyra.utils.cli_helpers import configure_logging_from_env

        if getattr(args, "verbose", False):
            os.environ["ZYRA_VERBOSITY"] = "debug"
        elif getattr(args, "quiet", False):
            os.environ["ZYRA_VERBOSITY"] = "quiet"
        if getattr(args, "trace", False):
            os.environ["ZYRA_SHELL_TRACE"] = "1"
        configure_logging_from_env()
        return run_video_transcode(args)

    p_vt = subparsers.add_parser(
        "video-transcode",
        help="Transcode video files or image sequences via ffmpeg",
        description=(
            "Transcode videos or JPG image stacks into modern or legacy formats using FFmpeg. "
            "Supports SOS presets, metadata capture, and batch processing."
        ),
    )
    p_vt.add_argument(
        "input", help="Input video path, directory, glob, or frame pattern"
    )
    p_vt.add_argument(
        "-o",
        "--output",
        dest="output",
        help="Output file path (single input) or directory when batching",
    )
    p_vt.add_argument(
        "--to",
        dest="container",
        choices=["mp4", "webm", "mov", "mpg"],
        default="mp4",
        help="Target container format",
    )
    p_vt.add_argument(
        "--codec",
        choices=["h264", "hevc", "vp9", "av1", "libxvid", "mpeg2video"],
        help="Video codec to use (sensible default chosen per container)",
    )
    p_vt.add_argument(
        "--audio-codec",
        dest="audio_codec",
        help="Audio codec to use (defaults based on container)",
    )
    p_vt.add_argument(
        "--audio-bitrate",
        dest="audio_bitrate",
        help="Optional audio bitrate, e.g. 192k",
    )
    p_vt.add_argument("--scale", help="Optional scale filter, e.g. 1920x1080 or 1080")
    p_vt.add_argument(
        "--fps",
        dest="fps",
        type=float,
        help="Output frames per second (also used as input framerate for sequences)",
    )
    p_vt.add_argument(
        "--framerate",
        dest="fps",
        type=float,
        help="Alias for --fps, kept for FFmpeg parity",
    )
    p_vt.add_argument(
        "--bitrate",
        help="Target video bitrate (e.g. 8M, 2500k). Defaults to 8M or SOS preset",
    )
    p_vt.add_argument(
        "--pix-fmt",
        dest="pix_fmt",
        help="Pixel format to emit (default yuv420p for compatibility)",
    )
    p_vt.add_argument("--preset", help="FFmpeg encoder preset when supported")
    p_vt.add_argument(
        "--crf",
        type=int,
        help="Constant Rate Factor value for quality-based encoders",
    )
    p_vt.add_argument(
        "--gop",
        type=int,
        help="Group-of-pictures interval (keyframe spacing)",
    )
    p_vt.add_argument(
        "--extra-args",
        action="append",
        default=None,
        help="Additional raw FFmpeg arguments (repeatable)",
    )
    p_vt.add_argument(
        "--metadata-out",
        dest="metadata_out",
        help="Path to write ffprobe metadata JSON",
    )
    p_vt.add_argument(
        "--write-metadata",
        dest="write_metadata",
        action="store_true",
        help="Emit ffprobe metadata JSON after transcoding",
    )
    p_vt.add_argument(
        "--sos-legacy",
        dest="sos_legacy",
        action="store_true",
        help="Apply SOS defaults: -framerate 30 -b:v 25M -c:v libxvid -pix_fmt yuv420p",
    )
    p_vt.add_argument(
        "--no-overwrite",
        dest="no_overwrite",
        action="store_true",
        help="Do not overwrite existing outputs (passes -n to FFmpeg)",
    )
    p_vt.add_argument("--verbose", action="store_true")
    p_vt.add_argument("--quiet", action="store_true")
    p_vt.add_argument("--trace", action="store_true")

    def _vt_entry(args: argparse.Namespace) -> int:
        args.extra_args = normalise_extra_args(getattr(args, "extra_args", None))
        return cmd_video_transcode(args)

    p_vt.set_defaults(func=_vt_entry)

    # audio-transcode (optional helper using ffmpeg)
    def cmd_audio_transcode(args: argparse.Namespace) -> int:
        import os
        import shutil
        import subprocess

        from zyra.utils.cli_helpers import configure_logging_from_env

        if getattr(args, "verbose", False):
            os.environ["ZYRA_VERBOSITY"] = "debug"
        elif getattr(args, "quiet", False):
            os.environ["ZYRA_VERBOSITY"] = "quiet"
        if getattr(args, "trace", False):
            os.environ["ZYRA_SHELL_TRACE"] = "1"
        configure_logging_from_env()

        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise SystemExit(
                "ffmpeg binary not found in PATH. Install FFmpeg to use audio-transcode."
            )
        # Determine output path and format
        out_path = args.output
        fmt = args.to
        # Build ffmpeg args
        cmd = [
            ffmpeg,
            "-y",
            "-i",
            args.input,
            "-ac",
            "1" if args.mono else "2",
            "-ar",
            str(args.sample_rate),
        ]
        if fmt == "mp3":
            cmd += ["-codec:a", "libmp3lame"]
        elif fmt == "ogg":
            cmd += ["-codec:a", "libopus"]
        # else wav defaults
        cmd += [out_path]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            import logging

            logging.error(res.stderr.strip())
            return 2
        import logging

        logging.info(out_path)
        return 0

    p_at = subparsers.add_parser(
        "audio-transcode",
        help="Transcode audio to wav/mp3/ogg via ffmpeg",
        description=(
            "Transcode input audio to a target format using ffmpeg. Requires FFmpeg runtime."
        ),
    )
    p_at.add_argument("input", help="Input audio file path")
    p_at.add_argument(
        "-o", "--output", dest="output", required=True, help="Output file path"
    )
    p_at.add_argument("--to", choices=["wav", "mp3", "ogg"], default="wav")
    p_at.add_argument("--sample-rate", dest="sample_rate", type=int, default=16000)
    p_at.add_argument(
        "--mono", action="store_true", default=True, help="Force mono output"
    )
    p_at.add_argument(
        "--stereo", action="store_true", help="Force stereo output (overrides --mono)"
    )
    p_at.add_argument("--verbose", action="store_true")
    p_at.add_argument("--quiet", action="store_true")
    p_at.add_argument("--trace", action="store_true")

    def _at_entry(args: argparse.Namespace) -> int:
        # Resolve mono/stereo precedence
        if getattr(args, "stereo", False):
            args.mono = False
        return cmd_audio_transcode(args)

    p_at.set_defaults(func=_at_entry)

    # audio-metadata (ffprobe)
    def cmd_audio_metadata(args: argparse.Namespace) -> int:
        import os
        import shutil
        import subprocess

        from zyra.utils.cli_helpers import configure_logging_from_env
        from zyra.utils.io_utils import open_output as _open_output

        if getattr(args, "verbose", False):
            os.environ["ZYRA_VERBOSITY"] = "debug"
        elif getattr(args, "quiet", False):
            os.environ["ZYRA_VERBOSITY"] = "quiet"
        if getattr(args, "trace", False):
            os.environ["ZYRA_SHELL_TRACE"] = "1"
        configure_logging_from_env()

        ffprobe = shutil.which("ffprobe")
        if not ffprobe:
            raise SystemExit(
                "ffprobe binary not found in PATH. Install FFmpeg to use audio-metadata."
            )
        cmd = [
            ffprobe,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_streams",
            "-show_format",
            args.input,
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            import logging

            logging.error(res.stderr.strip())
            return 2
        # Parse and normalize a minimal metadata dict
        try:
            data = json.loads(res.stdout)
        except Exception as exc:  # pragma: no cover - unexpected
            raise SystemExit("ffprobe returned invalid JSON") from exc
        fmt = (data or {}).get("format", {})
        streams = (data or {}).get("streams", []) or []
        audio = next((s for s in streams if s.get("codec_type") == "audio"), {})
        meta = {
            "codec": audio.get("codec_name"),
            "channels": audio.get("channels"),
            "sample_rate": int(audio["sample_rate"])
            if audio.get("sample_rate")
            else None,
            "bit_rate": int(audio["bit_rate"]) if audio.get("bit_rate") else None,
            "duration": float(fmt["duration"]) if fmt.get("duration") else None,
            "format_name": fmt.get("format_name"),
            "size": int(fmt["size"]) if fmt.get("size") else None,
        }
        # Write JSON to output
        payload = (json.dumps(meta, ensure_ascii=False) + "\n").encode("utf-8")
        with _open_output(args.output) as f:
            f.write(payload)
        return 0

    p_am = subparsers.add_parser(
        "audio-metadata",
        help="Extract audio metadata via ffprobe and emit JSON",
        description=(
            "Run ffprobe to extract duration, bitrate, channels, sample rate, codec, and size; writes JSON."
        ),
    )
    p_am.add_argument("input", help="Input audio file path")
    p_am.add_argument(
        "-o",
        "--output",
        dest="output",
        default="-",
        help="Output path or '-' for stdout",
    )
    p_am.add_argument("--verbose", action="store_true")
    p_am.add_argument("--quiet", action="store_true")
    p_am.add_argument("--trace", action="store_true")
    p_am.set_defaults(func=cmd_audio_metadata)
