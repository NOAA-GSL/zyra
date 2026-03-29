# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import argparse
import contextlib
import json
import logging
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from rasterio.enums import Resampling

from zyra.transform.geospatial import (
    write_csv_points_geojson,
    write_shapefile_geojson,
)
from zyra.transform.raster import convert_geotiff_to_cog
from zyra.utils.cli_helpers import configure_logging_from_env
from zyra.utils.date_manager import DateManager
from zyra.utils.io_utils import open_output


def _compute_frames_metadata(
    frames_dir: str,
    *,
    pattern: str | None = None,
    datetime_format: str | None = None,
    period_seconds: int | None = None,
) -> dict[str, Any]:
    """Compute summary metadata for a directory of frame images.

    Scans a directory for image files (optionally filtered by regex), parses
    timestamps embedded in filenames using ``datetime_format`` or a fallback,
    and returns a JSON-serializable mapping with start/end timestamps, the
    number of frames, expected count for a cadence (if provided), and a list
    of missing timestamps on the cadence grid.
    """
    p = Path(frames_dir)
    if not p.exists() or not p.is_dir():
        raise SystemExit(f"Frames directory not found: {frames_dir}")

    # Collect candidate files
    names = [f.name for f in p.iterdir() if f.is_file()]
    if pattern:
        rx = re.compile(pattern)
        names = [n for n in names if rx.search(n)]
    else:
        exts = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".dds"}
        names = [n for n in names if Path(n).suffix.lower() in exts]
    names.sort()

    # Parse timestamps from filenames
    entries: list[tuple[datetime, Path]] = []
    timestamps: list[datetime] = []
    if datetime_format:
        dm = DateManager([datetime_format])
        parsed = dm.parse_timestamps_from_filenames(names, datetime_format)
        for name, dt in zip(names, parsed):
            if dt is not None:
                entries.append((dt, p / name))
                timestamps.append(dt)
    else:
        dm = DateManager()
        for n in names:
            s = dm.extract_date_time(n)
            if s:
                with contextlib.suppress(Exception):
                    dt = datetime.fromisoformat(s)
                    entries.append((dt, p / n))
                    timestamps.append(dt)
    entries.sort(key=lambda item: item[0])
    timestamps.sort()

    start_dt = timestamps[0] if timestamps else None
    end_dt = timestamps[-1] if timestamps else None

    out: dict[str, Any] = {
        "frames_dir": str(p),
        "pattern": pattern,
        "datetime_format": datetime_format,
        "period_seconds": period_seconds,
        "frame_count_actual": len(timestamps),
        "start_datetime": start_dt.isoformat() if start_dt else None,
        "end_datetime": end_dt.isoformat() if end_dt else None,
    }

    if period_seconds and start_dt and end_dt:
        exp = DateManager().calculate_expected_frames(start_dt, end_dt, period_seconds)
        out["frame_count_expected"] = exp
        # Compute missing timestamps grid
        have: set[str] = {t.isoformat() for t in timestamps}
        miss: list[str] = []
        cur = start_dt
        step = timedelta(seconds=int(period_seconds))
        for _ in range(exp):
            s = cur.isoformat()
            if s not in have:
                miss.append(s)
            cur += step
        out["missing_count"] = len(miss)
        out["missing_timestamps"] = miss
    else:
        out["frame_count_expected"] = None
        out["missing_count"] = None
        out["missing_timestamps"] = []

    analysis: dict[str, Any] = {}
    if start_dt and end_dt:
        analysis["span_seconds"] = int((end_dt - start_dt).total_seconds())
    if entries:
        unique_seen: set[str] = set()
        duplicates: list[str] = []
        for dt, _ in entries:
            iso = dt.isoformat()
            if iso in unique_seen:
                duplicates.append(iso)
            else:
                unique_seen.add(iso)
        analysis["frame_count_unique"] = len(unique_seen)
        analysis["duplicate_timestamps"] = duplicates
        sample_indexes = sorted({0, len(entries) // 2, len(entries) - 1})
        samples: list[dict[str, Any]] = []
        for idx in sample_indexes:
            if idx < 0 or idx >= len(entries):
                continue
            dt, file_path = entries[idx]
            sample: dict[str, Any] = {
                "timestamp": dt.isoformat(),
                "path": str(file_path),
            }
            with contextlib.suppress(OSError, ValueError):
                stat = file_path.stat()
                sample["size_bytes"] = stat.st_size
            samples.append(sample)
        analysis["sample_frames"] = samples

        sizes = []
        for _, fp in entries:
            with contextlib.suppress(OSError, ValueError):
                sizes.append(fp.stat().st_size)
        if sizes:
            analysis["file_size_summary"] = {
                "min_bytes": min(sizes),
                "max_bytes": max(sizes),
                "total_bytes": sum(sizes),
            }

    if analysis:
        out["analysis"] = analysis

    return out


def _cmd_metadata(ns: argparse.Namespace) -> int:
    """CLI: compute frames metadata and write JSON to stdout or a file."""
    if getattr(ns, "verbose", False):
        os.environ["ZYRA_VERBOSITY"] = "debug"
    elif getattr(ns, "quiet", False):
        os.environ["ZYRA_VERBOSITY"] = "quiet"
    if getattr(ns, "trace", False):
        os.environ["ZYRA_SHELL_TRACE"] = "1"
    configure_logging_from_env()
    alias = getattr(ns, "_command_alias", "metadata")
    if alias == "metadata":
        import logging

        logging.info(
            "Note: 'transform metadata' is also available as 'transform scan-frames'."
        )
    meta = _compute_frames_metadata(
        ns.frames_dir,
        pattern=ns.pattern,
        datetime_format=ns.datetime_format,
        period_seconds=ns.period_seconds,
    )
    payload = (json.dumps(meta, indent=2) + "\n").encode("utf-8")
    # Write to stdout or file
    # Ensure parent directories exist when writing to a file path
    if ns.output and ns.output != "-":
        try:
            out_path = Path(ns.output)
            if out_path.parent:
                out_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            # Fall through; open_output will surface any remaining errors
            pass
    with open_output(ns.output) as f:
        f.write(payload)
    return 0


_RESAMPLING_MAP = {item.name.lower(): item for item in Resampling}
_RESAMPLING_CHOICES = sorted(_RESAMPLING_MAP.keys())


def _parse_resampling(
    value: str | None, *, default: Resampling | None = None
) -> Resampling | None:
    if value is None:
        return default
    key = value.strip().lower()
    if key not in _RESAMPLING_MAP:
        raise SystemExit(f"Unsupported resampling value: {value}")
    return _RESAMPLING_MAP[key]


def _parse_overview_levels(value: str | None) -> tuple[int, ...] | None:
    if value is None:
        return None
    token = value.strip().lower()
    if not token or token == "auto":
        return None
    levels: list[int] = []
    for part in token.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            level = int(part)
        except ValueError as exc:
            raise SystemExit("Overview levels must be integers (e.g., 2,4,8)") from exc
        if level <= 1:
            raise SystemExit("Overview levels must be greater than 1")
        levels.append(level)
    if not levels:
        return None
    return tuple(sorted(set(levels)))


def _collect_raster_inputs(
    inputs: list[str] | None,
    input_dir: str | None,
    pattern: str,
    recursive: bool,
) -> list[Path]:
    pattern = pattern or "*.tif"
    gathered: list[Path] = []
    seen: set[Path] = set()

    def _add_candidate(path: Path) -> None:
        if not path.exists():
            raise SystemExit(f"Input not found: {path}")
        if not path.is_file():
            raise SystemExit(f"Input is not a file: {path}")
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            gathered.append(path)

    if inputs:
        for item in inputs:
            candidate = Path(item)
            if candidate.is_dir():
                iterator = (
                    candidate.rglob(pattern) if recursive else candidate.glob(pattern)
                )
                for child in sorted(iterator):
                    if child.is_file():
                        _add_candidate(child)
            else:
                _add_candidate(candidate)

    if input_dir:
        directory = Path(input_dir)
        if not directory.exists() or not directory.is_dir():
            raise SystemExit(f"Input directory not found: {directory}")
        iterator = directory.rglob(pattern) if recursive else directory.glob(pattern)
        for child in sorted(iterator):
            if child.is_file():
                _add_candidate(child)

    if not gathered:
        raise SystemExit("No GeoTIFF inputs found for geotiff-to-cog")
    return gathered


def _render_output_name(
    src_path: Path,
    *,
    template: str,
    output_dir: Path,
    dm: DateManager,
    timestamp_format: str | None,
) -> Path:
    if output_dir is None:
        raise SystemExit("--output-dir is required when using --name-template")
    values = {
        "stem": src_path.stem,
        "name": src_path.name,
        "timestamp": "",
    }
    if "{timestamp" in template:
        ts_iso = dm.extract_date_time(src_path.name)
        dt_value: datetime | None = None
        if ts_iso:
            try:
                dt_value = datetime.fromisoformat(ts_iso)
            except ValueError:
                dt_value = None
        if dt_value is None:
            raise SystemExit(
                f"Could not derive timestamp for '{src_path.name}' to populate {{timestamp}}"
            )
        out_fmt = timestamp_format or "%Y%m%dT%H%M%SZ"
        values["timestamp"] = dt_value.strftime(out_fmt)

    try:
        filename = template.format(**values)
    except KeyError as exc:
        missing = exc.args[0]
        raise SystemExit(
            f"Unknown placeholder '{{{missing}}}' in --name-template"
        ) from exc

    return output_dir / filename


def _cmd_geotiff_to_cog(ns: argparse.Namespace) -> int:
    if getattr(ns, "verbose", False):
        os.environ["ZYRA_VERBOSITY"] = "debug"
    elif getattr(ns, "quiet", False):
        os.environ["ZYRA_VERBOSITY"] = "quiet"
    if getattr(ns, "trace", False):
        os.environ["ZYRA_SHELL_TRACE"] = "1"
    configure_logging_from_env()

    inputs = _collect_raster_inputs(ns.inputs, ns.input_dir, ns.pattern, ns.recursive)
    multi_inputs = len(inputs) > 1

    if ns.output and ns.output_dir:
        raise SystemExit("Specify either --output or --output-dir, not both")
    if multi_inputs and ns.output:
        raise SystemExit("--output can only be used with a single input GeoTIFF")
    if multi_inputs and not ns.output_dir:
        raise SystemExit("--output-dir is required when converting multiple files")
    if not ns.output and not ns.output_dir:
        raise SystemExit(
            "Specify --output or --output-dir for the COG conversion output"
        )

    resampling = _parse_resampling(ns.resampling, default=Resampling.bilinear)
    overview_resampling = _parse_resampling(ns.overview_resampling, default=None)
    overview_levels = _parse_overview_levels(ns.overview_levels)

    if ns.predictor and ns.predictor.lower() != "auto":
        try:
            predictor_value: int | None = int(ns.predictor)
        except ValueError as exc:
            raise SystemExit("--predictor must be an integer or 'auto'") from exc
    else:
        predictor_value = None

    timestamp_dm = DateManager([ns.datetime_format] if ns.datetime_format else None)

    output_dir_path = Path(ns.output_dir) if ns.output_dir else None
    if output_dir_path and not ns.dry_run:
        output_dir_path.mkdir(parents=True, exist_ok=True)

    for input_path in inputs:
        if ns.output:
            target_path = Path(ns.output)
            if not ns.dry_run:
                target_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            target_path = _render_output_name(
                input_path,
                template=ns.name_template,
                output_dir=output_dir_path,
                dm=timestamp_dm,
                timestamp_format=ns.output_datetime_format,
            )

        if ns.dry_run:
            print(f"[dry-run] {input_path} -> {target_path}")
            continue

        try:
            result_path = convert_geotiff_to_cog(
                input_path,
                target_path,
                dst_crs=ns.dst_crs,
                resampling=resampling or Resampling.bilinear,
                overview_levels=overview_levels,
                overview_resampling=overview_resampling,
                blocksize=ns.blocksize,
                compression=ns.compression,
                predictor=predictor_value,
                bigtiff=ns.bigtiff,
                num_threads=ns.num_threads,
                overwrite=bool(ns.overwrite),
            )
        except Exception as exc:  # pragma: no cover - surface error to CLI
            logging.error(str(exc))
            return 2
        print(result_path)

    return 0


def register_cli(subparsers: Any) -> None:
    """Register transform subcommands (metadata, enrich, dataset tools, geo helpers)."""

    from zyra.cli_common import add_output_option

    def _configure_metadata_parser(
        parser: argparse.ArgumentParser, *, alias_name: str
    ) -> None:
        parser.add_argument(
            "--frames-dir",
            required=True,
            dest="frames_dir",
            help="Directory containing frames",
        )
        parser.add_argument("--pattern", help="Regex filter for frame filenames")
        parser.add_argument(
            "--datetime-format",
            dest="datetime_format",
            help="Datetime format used in filenames (e.g., %Y%m%d%H%M%S)",
        )
        parser.add_argument(
            "--period-seconds",
            type=int,
            help="Expected cadence to compute missing frames",
        )
        add_output_option(parser)
        parser.add_argument(
            "--verbose", action="store_true", help="Verbose logging for this command"
        )
        parser.add_argument(
            "--quiet", action="store_true", help="Quiet logging for this command"
        )
        parser.add_argument(
            "--trace",
            action="store_true",
            help="Shell-style trace of key steps and external commands",
        )
        parser.set_defaults(func=_cmd_metadata, _command_alias=alias_name)

    p = subparsers.add_parser(
        "metadata",
        help="Compute frames metadata as JSON",
        description=(
            "Scan a frames directory to compute start/end timestamps, counts, and missing frames on a cadence."
        ),
    )
    _configure_metadata_parser(p, alias_name="metadata")

    p_scan = subparsers.add_parser(
        "scan-frames",
        help="Alias of 'metadata' with a descriptive name",
        description=(
            "Alias of 'metadata'. Scan a frames directory and report timestamps, counts, and missing frames."
        ),
    )
    _configure_metadata_parser(p_scan, alias_name="scan-frames")

    p_cog = subparsers.add_parser(
        "geotiff-to-cog",
        help="Convert GeoTIFFs to Cloud Optimized GeoTIFFs",
        description=(
            "Convert one or more GeoTIFF inputs into Cloud Optimized GeoTIFFs (COGs) with optional reprojection, "
            "tiled compression, and overview generation."
        ),
    )
    p_cog.add_argument(
        "--input",
        dest="inputs",
        action="append",
        help="Input GeoTIFF path (repeatable). Directories will be scanned using --pattern",
    )
    p_cog.add_argument(
        "--input-dir",
        dest="input_dir",
        help="Directory containing GeoTIFF files to convert",
    )
    p_cog.add_argument(
        "--pattern",
        default="*.tif",
        help="Glob pattern used when scanning directories (default: *.tif)",
    )
    p_cog.add_argument(
        "-o",
        "--output",
        dest="output",
        help="Output path for a single input file",
    )
    p_cog.add_argument(
        "--output-dir",
        dest="output_dir",
        help="Directory to write outputs (required for multiple inputs)",
    )
    p_cog.add_argument(
        "--name-template",
        default="{stem}.tif",
        help="Filename template when writing to --output-dir. Supports {stem}, {name}, {timestamp}",
    )
    p_cog.add_argument(
        "--datetime-format",
        help="Datetime format to extract timestamps from source filenames (for {timestamp})",
    )
    p_cog.add_argument(
        "--output-datetime-format",
        default="%Y%m%dT%H%M%SZ",
        help="Strftime pattern used when formatting {timestamp} (default: %Y%m%dT%H%M%SZ)",
    )
    p_cog.add_argument(
        "--dst-crs",
        help="Destination CRS (e.g., EPSG:4326). Defaults to the source CRS",
    )
    p_cog.add_argument(
        "--resampling",
        default="bilinear",
        choices=_RESAMPLING_CHOICES,
        help="Resampling kernel to use when reprojecting (default: bilinear)",
    )
    p_cog.add_argument(
        "--overview-resampling",
        choices=_RESAMPLING_CHOICES,
        help="Resampling kernel to use for overview generation (default: match --resampling)",
    )
    p_cog.add_argument(
        "--overview-levels",
        help="Comma-separated overview decimation levels (default: auto)",
    )
    p_cog.add_argument(
        "--blocksize",
        type=int,
        default=512,
        help="Internal tile size in pixels (default: 512)",
    )
    p_cog.add_argument(
        "--compression",
        default="DEFLATE",
        help="Compression codec for output tiles (default: DEFLATE)",
    )
    p_cog.add_argument(
        "--predictor",
        default="auto",
        help="Predictor to use (auto, 1, 2, or 3)",
    )
    p_cog.add_argument(
        "--bigtiff",
        default="IF_SAFER",
        choices=["YES", "NO", "IF_NEEDED", "IF_SAFER"],
        help="Control BigTIFF creation (default: IF_SAFER)",
    )
    p_cog.add_argument(
        "--num-threads",
        dest="num_threads",
        help="Value for GDAL NUM_THREADS option (e.g., ALL_CPUS)",
    )
    p_cog.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow overwriting existing outputs",
    )
    p_cog.add_argument(
        "--dry-run",
        action="store_true",
        help="Report planned outputs without writing files",
    )
    p_cog.add_argument(
        "--recursive",
        action="store_true",
        help="Recurse into subdirectories when scanning directories",
    )
    p_cog.add_argument(
        "--verbose", action="store_true", help="Verbose logging for this command"
    )
    p_cog.add_argument(
        "--quiet", action="store_true", help="Quiet logging for this command"
    )
    p_cog.add_argument(
        "--trace",
        action="store_true",
        help="Shell-style trace of key steps and external commands",
    )
    p_cog.set_defaults(func=_cmd_geotiff_to_cog)

    # Enrich metadata with dataset_id, vimeo_uri, and updated_at
    def _cmd_enrich(ns: argparse.Namespace) -> int:
        """CLI: enrich a frames metadata JSON with dataset id and Vimeo URI.

        Accepts a base metadata JSON (e.g., from ``metadata``), merges optional
        ``dataset_id`` and ``vimeo_uri`` (read from arg or stdin), and stamps
        ``updated_at``.
        """
        if getattr(ns, "verbose", False):
            os.environ["ZYRA_VERBOSITY"] = "debug"
        elif getattr(ns, "quiet", False):
            os.environ["ZYRA_VERBOSITY"] = "quiet"
        if getattr(ns, "trace", False):
            os.environ["ZYRA_SHELL_TRACE"] = "1"
        configure_logging_from_env()
        import sys

        from zyra.utils.json_file_manager import JSONFileManager

        fm = JSONFileManager()
        # Load base metadata JSON from file or stdin when requested
        try:
            if getattr(ns, "read_frames_meta_stdin", False):
                raw = sys.stdin.buffer.read()
                try:
                    js = raw.decode("utf-8")
                except UnicodeDecodeError as e:
                    raise SystemExit(
                        f"Failed to decode stdin as UTF-8 for frames metadata: {e}"
                    ) from e
                try:
                    base = json.loads(js)
                except json.JSONDecodeError as e:
                    raise SystemExit(
                        f"Invalid JSON on stdin for frames metadata: {e}"
                    ) from e
            else:
                base = fm.read_json(ns.frames_meta)
        except Exception as exc:
            raise SystemExit(f"Failed to read frames metadata: {exc}") from exc
        if not isinstance(base, dict):
            base = {}
        # Attach dataset_id
        if getattr(ns, "dataset_id", None):
            base["dataset_id"] = ns.dataset_id
        # Attach vimeo_uri from arg or stdin
        vuri = getattr(ns, "vimeo_uri", None)
        if getattr(ns, "read_vimeo_uri", False):
            raw = sys.stdin.buffer.read()
            try:
                data = raw.decode("utf-8").strip()
            except UnicodeDecodeError as e:
                raise SystemExit(
                    f"Failed to decode stdin as UTF-8 for Vimeo URI: {e}"
                ) from e
            if data:
                vuri = data.splitlines()[0].strip()
        if vuri:
            base["vimeo_uri"] = vuri
        # Add updated_at timestamp
        base["updated_at"] = datetime.now().replace(microsecond=0).isoformat()
        payload = (json.dumps(base, indent=2) + "\n").encode("utf-8")
        with open_output(ns.output) as f:
            f.write(payload)
        return 0

    p2 = subparsers.add_parser(
        "enrich-metadata",
        help="Enrich frames metadata with dataset id and Vimeo URI",
        description=(
            "Enrich a frames metadata JSON with dataset_id, Vimeo URI, and updated_at; read from file or stdin."
        ),
    )
    # Source of base frames metadata: file or stdin
    srcgrp = p2.add_mutually_exclusive_group(required=True)
    srcgrp.add_argument(
        "--frames-meta",
        dest="frames_meta",
        help="Path to frames metadata JSON",
    )
    srcgrp.add_argument(
        "--read-frames-meta-stdin",
        dest="read_frames_meta_stdin",
        action="store_true",
        help="Read frames metadata JSON from stdin",
    )
    p2.add_argument(
        "--dataset-id", dest="dataset_id", help="Dataset identifier to embed"
    )
    grp = p2.add_mutually_exclusive_group()
    grp.add_argument("--vimeo-uri", help="Vimeo video URI to embed in metadata")
    grp.add_argument(
        "--read-vimeo-uri",
        action="store_true",
        help="Read Vimeo URI from stdin (first line)",
    )
    add_output_option(p2)
    p2.add_argument(
        "--verbose", action="store_true", help="Verbose logging for this command"
    )
    p2.add_argument(
        "--quiet", action="store_true", help="Quiet logging for this command"
    )
    p2.add_argument(
        "--trace",
        action="store_true",
        help="Shell-style trace of key steps and external commands",
    )
    p2.set_defaults(func=_cmd_enrich)

    # Enrich a list of dataset items (id,name,description,source,format,uri)
    def _cmd_enrich_datasets(ns: argparse.Namespace) -> int:
        """CLI: enrich dataset items provided in a JSON file.

        Input JSON can be either a list of items or an object with an `items` array.
        Each item should contain: id, name, description, source, format, uri.
        """
        if getattr(ns, "verbose", False):
            os.environ["ZYRA_VERBOSITY"] = "debug"
        elif getattr(ns, "quiet", False):
            os.environ["ZYRA_VERBOSITY"] = "quiet"
        if getattr(ns, "trace", False):
            os.environ["ZYRA_SHELL_TRACE"] = "1"
        configure_logging_from_env()
        from zyra.connectors.discovery import DatasetMetadata
        from zyra.transform.enrich import enrich_items
        from zyra.utils.json_file_manager import JSONFileManager
        from zyra.utils.serialize import to_list

        fm = JSONFileManager()
        try:
            data = fm.read_json(ns.items_file)
        except Exception as exc:
            raise SystemExit(f"Failed to read items JSON: {exc}") from exc
        if isinstance(data, dict) and isinstance(data.get("items"), list):
            items_in_raw = data.get("items")
        elif isinstance(data, list):
            items_in_raw = data
        else:
            raise SystemExit(
                "Input JSON must be a list or an object with an 'items' array"
            )

        # Optional profiles for defaults and license policy
        prof_defaults: dict[str, Any] = {}
        prof_license_policy: dict[str, Any] = {}
        if getattr(ns, "profile", None):
            try:
                from importlib import resources as importlib_resources

                pkg = "zyra.assets.profiles"
                res = f"{ns.profile}.json"
                path = importlib_resources.files(pkg).joinpath(res)
                with importlib_resources.as_file(path) as p:
                    import json as _json

                    prof0 = _json.loads(p.read_text(encoding="utf-8"))
                enr = prof0.get("enrichment") or {}
                ed = enr.get("defaults") or {}
                if isinstance(ed, dict):
                    prof_defaults.update(ed)
                lp = enr.get("license_policy") or {}
                if isinstance(lp, dict):
                    prof_license_policy.update(lp)
            except Exception as exc:
                raise SystemExit(
                    f"Failed to load bundled profile '{ns.profile}': {exc}"
                ) from exc
        if getattr(ns, "profile_file", None):
            try:
                import json as _json

                prof1 = _json.loads(Path(ns.profile_file).read_text(encoding="utf-8"))
                enr = prof1.get("enrichment") or {}
                ed = enr.get("defaults") or {}
                if isinstance(ed, dict):
                    prof_defaults.update(ed)
                lp = enr.get("license_policy") or {}
                if isinstance(lp, dict):
                    prof_license_policy.update(lp)
            except Exception as exc:
                raise SystemExit(f"Failed to load profile file: {exc}") from exc

        # Normalize to DatasetMetadata
        items_in: list[DatasetMetadata] = []
        for d in items_in_raw:
            try:
                items_in.append(
                    DatasetMetadata(
                        id=str(d.get("id")),
                        name=str(d.get("name")),
                        description=d.get("description"),
                        source=str(d.get("source")),
                        format=str(d.get("format")),
                        uri=str(d.get("uri")),
                    )
                )
            except Exception:
                continue
        enriched = enrich_items(
            items_in,
            level=str(ns.enrich),
            timeout=float(getattr(ns, "enrich_timeout", 3.0) or 3.0),
            workers=int(getattr(ns, "enrich_workers", 4) or 4),
            cache_ttl=int(getattr(ns, "cache_ttl", 86400) or 86400),
            offline=bool(getattr(ns, "offline", False) or False),
            https_only=bool(getattr(ns, "https_only", False) or False),
            allow_hosts=list(getattr(ns, "allow_host", []) or []),
            deny_hosts=list(getattr(ns, "deny_host", []) or []),
            max_probe_bytes=(getattr(ns, "max_probe_bytes", None)),
            profile_defaults=prof_defaults,
            profile_license_policy=prof_license_policy,
        )
        payload = (json.dumps(to_list(enriched), indent=2) + "\n").encode("utf-8")
        with open_output(ns.output) as f:
            f.write(payload)
        return 0

    p3 = subparsers.add_parser(
        "enrich-datasets",
        help=(
            "Enrich dataset items JSON (id,name,description,source,format,uri) with metadata\n"
            "Use --profile/--profile-file for defaults and license policy"
        ),
    )
    p3.add_argument(
        "--items-file", required=True, dest="items_file", help="Path to items JSON"
    )
    p3.add_argument("--profile", help="Bundled profile name under zyra.assets.profiles")
    p3.add_argument("--profile-file", help="External profile JSON path")
    p3.add_argument(
        "--enrich",
        required=True,
        choices=["shallow", "capabilities", "probe"],
        help="Enrichment level",
    )
    p3.add_argument(
        "--enrich-timeout", type=float, default=3.0, help="Per-item timeout (s)"
    )
    p3.add_argument(
        "--enrich-workers", type=int, default=4, help="Concurrency (workers)"
    )
    p3.add_argument("--cache-ttl", type=int, default=86400, help="Cache TTL seconds")
    p3.add_argument(
        "--offline", action="store_true", help="Disable network during enrichment"
    )
    p3.add_argument(
        "--https-only", action="store_true", help="Require HTTPS for remote probing"
    )
    p3.add_argument(
        "--allow-host", action="append", help="Allow host suffix (repeatable)"
    )
    p3.add_argument(
        "--deny-host", action="append", help="Deny host suffix (repeatable)"
    )
    p3.add_argument(
        "--max-probe-bytes", type=int, help="Skip probing when larger than this size"
    )
    add_output_option(p3)
    p3.add_argument(
        "--verbose", action="store_true", help="Verbose logging for this command"
    )
    p3.add_argument(
        "--quiet", action="store_true", help="Quiet logging for this command"
    )
    p3.add_argument(
        "--trace",
        action="store_true",
        help="Shell-style trace of key steps and external commands",
    )
    p3.set_defaults(func=_cmd_enrich_datasets)

    # Update a dataset.json entry's startTime/endTime (and optionally dataLink) by dataset id
    def _cmd_update_dataset(ns: argparse.Namespace) -> int:
        """CLI: update an entry in dataset.json by dataset id.

        Loads a dataset index JSON from a local path or URL (HTTP or s3),
        updates the entry matching ``--dataset-id`` with ``startTime`` and
        ``endTime`` (from metadata or explicit flags), and optionally updates
        ``dataLink`` from a Vimeo URI. Writes the updated JSON to ``--output``.
        """
        configure_logging_from_env()
        import sys

        # Fetch input JSON
        raw: bytes
        src = ns.input_url or ns.input_file
        if not src:
            raise SystemExit("--input-url or --input-file is required")
        try:
            if ns.input_url:
                url = ns.input_url
                if url.startswith("s3://"):
                    from zyra.connectors.backends import s3 as s3_backend

                    raw = s3_backend.fetch_bytes(url)
                else:
                    from zyra.connectors.backends import http as http_backend

                    raw = http_backend.fetch_bytes(url)
            else:
                raw = Path(ns.input_file).read_bytes()
        except Exception as exc:
            raise SystemExit(f"Failed to read dataset JSON: {exc}") from exc
        # Load metadata source (either explicit args or meta file/stdin)
        start = ns.start
        end = ns.end
        vimeo_uri = ns.vimeo_uri
        if ns.meta:
            try:
                meta = json.loads(Path(ns.meta).read_text(encoding="utf-8"))
                start = start or meta.get("start_datetime")
                end = end or meta.get("end_datetime")
                vimeo_uri = vimeo_uri or meta.get("vimeo_uri")
            except Exception:
                pass
        if ns.read_meta_stdin:
            raw_meta = sys.stdin.buffer.read()
            try:
                js = raw_meta.decode("utf-8")
            except UnicodeDecodeError as e:
                raise SystemExit(
                    f"Failed to decode stdin as UTF-8 for metadata JSON: {e}"
                ) from e
            try:
                meta2 = json.loads(js)
            except json.JSONDecodeError as e:
                raise SystemExit(f"Invalid metadata JSON on stdin: {e}") from e
            start = start or meta2.get("start_datetime")
            end = end or meta2.get("end_datetime")
            vimeo_uri = vimeo_uri or meta2.get("vimeo_uri")
        # Parse dataset JSON
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as e:
            raise SystemExit(f"Dataset JSON is not valid UTF-8: {e}") from e
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"Invalid dataset JSON: {exc}") from exc
        # Build dataLink from Vimeo if requested
        data_link = None
        if vimeo_uri and ns.set_data_link:
            vid = vimeo_uri.rsplit("/", 1)[-1]
            if vid.isdigit():
                data_link = f"https://vimeo.com/{vid}"
            else:
                # If full URL already
                if vimeo_uri.startswith("http"):
                    data_link = vimeo_uri
        # Update entry matching dataset id
        did = ns.dataset_id
        updated = False

        def _update_entry(entry: dict) -> bool:
            if not isinstance(entry, dict):
                return False
            if str(entry.get("id")) != str(did):
                return False
            if start is not None:
                entry["startTime"] = start
            if end is not None:
                entry["endTime"] = end
            if data_link is not None:
                entry["dataLink"] = data_link
            return True

        if isinstance(data, list):
            for ent in data:
                if _update_entry(ent):
                    updated = True
        elif isinstance(data, dict) and isinstance(data.get("datasets"), list):
            for ent in data["datasets"]:
                if _update_entry(ent):
                    updated = True
        else:
            # Single object case
            if isinstance(data, dict) and _update_entry(data):
                updated = True
        if not updated:
            raise SystemExit(f"Dataset id not found: {did}")
        out_bytes = (json.dumps(data, indent=2) + "\n").encode("utf-8")
        with open_output(ns.output) as f:
            f.write(out_bytes)
        return 0

    p3 = subparsers.add_parser(
        "update-dataset-json",
        help="Update start/end (and dataLink) for a dataset id in dataset.json",
        description=(
            "Update a dataset.json entry by id using metadata (start/end and Vimeo URI) from a file, stdin, or args."
        ),
    )
    srcgrp = p3.add_mutually_exclusive_group(required=True)
    srcgrp.add_argument("--input-url", help="HTTP(S) or s3:// URL of dataset.json")
    srcgrp.add_argument("--input-file", help="Local dataset.json path")
    p3.add_argument("--dataset-id", required=True, help="Dataset id to update")
    # Metadata sources
    p3.add_argument(
        "--meta",
        help="Path to metadata JSON containing start_datetime/end_datetime/vimeo_uri",
    )
    p3.add_argument(
        "--read-meta-stdin", action="store_true", help="Read metadata JSON from stdin"
    )
    p3.add_argument("--start", help="Explicit startTime override (ISO)")
    p3.add_argument("--end", help="Explicit endTime override (ISO)")
    p3.add_argument("--vimeo-uri", help="Explicit Vimeo URI (e.g., /videos/12345)")
    p3.add_argument(
        "--no-set-data-link",
        dest="set_data_link",
        action="store_false",
        help="Do not update dataLink from Vimeo URI",
    )
    p3.set_defaults(set_data_link=True)
    add_output_option(p3)
    p3.add_argument(
        "--verbose", action="store_true", help="Verbose logging for this command"
    )
    p3.add_argument(
        "--quiet", action="store_true", help="Quiet logging for this command"
    )
    p3.add_argument(
        "--trace",
        action="store_true",
        help="Shell-style trace of key steps and external commands",
    )
    p3.set_defaults(func=_cmd_update_dataset)

    def _cmd_shapefile_to_geojson(ns: argparse.Namespace) -> int:
        if getattr(ns, "verbose", False):
            os.environ["ZYRA_VERBOSITY"] = "debug"
        elif getattr(ns, "quiet", False):
            os.environ["ZYRA_VERBOSITY"] = "quiet"
        if getattr(ns, "trace", False):
            os.environ["ZYRA_SHELL_TRACE"] = "1"
        configure_logging_from_env()
        time_fields = ns.time_fields if ns.time_fields else ["LocalTime"]
        time_formats = ns.time_formats if ns.time_formats else None
        fallback_date = None
        if ns.fallback_date:
            try:
                fallback_date = datetime.strptime(ns.fallback_date, "%Y-%m-%d").date()
            except ValueError as exc:  # pragma: no cover - CLI validation
                raise SystemExit(
                    f"Invalid --fallback-date: {ns.fallback_date}"
                ) from exc
        try:
            write_shapefile_geojson(
                ns.input,
                ns.output,
                indent=ns.indent,
                time_fields=time_fields,
                time_formats=time_formats,
                timezone_name=ns.timezone,
                year_field=ns.year_field,
                month_field=ns.month_field,
                day_field=ns.day_field,
                default_year=ns.default_year,
                fallback_date=fallback_date,
                local_time_property=ns.local_time_property,
                utc_time_property=ns.utc_time_property,
            )
        except FileNotFoundError as exc:
            raise SystemExit(str(exc)) from exc
        return 0

    p_sf = subparsers.add_parser(
        "shapefile-to-geojson",
        help="Convert shapefile polygons/polylines to GeoJSON with optional time normalization",
        description=(
            "Convert a shapefile to GeoJSON. Optionally normalize local time fields into ISO timestamps using timezone hints."
        ),
    )
    p_sf.add_argument("--input", required=True, help="Path to input .shp file")
    p_sf.add_argument(
        "--time-field",
        dest="time_fields",
        action="append",
        help="Field containing local time strings (repeatable)",
    )
    p_sf.add_argument(
        "--time-format",
        dest="time_formats",
        action="append",
        help="Custom strptime format for local time (repeatable)",
    )
    p_sf.add_argument(
        "--timezone",
        default="UTC",
        help="Timezone name for local time parsing (default: UTC)",
    )
    p_sf.add_argument(
        "--year-field",
        default="Year",
        help="Field containing year values used when time strings omit a year",
    )
    p_sf.add_argument(
        "--month-field",
        default="Month",
        help="Field containing month values used when time strings omit a month",
    )
    p_sf.add_argument(
        "--day-field",
        default="Day",
        help="Field containing day values used when time strings omit a day",
    )
    p_sf.add_argument(
        "--default-year",
        type=int,
        help="Fallback year when no year field is present",
    )
    p_sf.add_argument(
        "--fallback-date",
        help="Fallback date (YYYY-MM-DD) when month/day are missing",
    )
    p_sf.add_argument(
        "--local-time-property",
        default="time_local_iso",
        help="Output property name for normalized local timestamp",
    )
    p_sf.add_argument(
        "--utc-time-property",
        default="time_utc_iso",
        help="Output property name for normalized UTC timestamp",
    )
    p_sf.add_argument(
        "--indent",
        type=int,
        default=2,
        help="Indentation level for GeoJSON output",
    )
    add_output_option(p_sf)
    p_sf.add_argument(
        "--verbose", action="store_true", help="Verbose logging for this command"
    )
    p_sf.add_argument(
        "--quiet", action="store_true", help="Quiet logging for this command"
    )
    p_sf.add_argument(
        "--trace",
        action="store_true",
        help="Shell-style trace of key steps and external commands",
    )
    p_sf.set_defaults(func=_cmd_shapefile_to_geojson)

    def _cmd_csv_to_geojson(ns: argparse.Namespace) -> int:
        if getattr(ns, "verbose", False):
            os.environ["ZYRA_VERBOSITY"] = "debug"
        elif getattr(ns, "quiet", False):
            os.environ["ZYRA_VERBOSITY"] = "quiet"
        if getattr(ns, "trace", False):
            os.environ["ZYRA_SHELL_TRACE"] = "1"
        configure_logging_from_env()
        local_fields = ns.local_time_fields if ns.local_time_fields else ["Time (CDT)"]
        utc_fields = ns.utc_time_fields if ns.utc_time_fields else ["Time (Z)"]
        time_formats = ns.time_formats if ns.time_formats else None
        event_date = None
        if ns.event_date:
            try:
                event_date = datetime.strptime(ns.event_date, "%Y-%m-%d").date()
            except ValueError as exc:  # pragma: no cover - CLI validation
                raise SystemExit(f"Invalid --event-date: {ns.event_date}") from exc
        try:
            write_csv_points_geojson(
                ns.input,
                ns.output,
                indent=ns.indent,
                lat_field=ns.lat_field,
                lon_field=ns.lon_field,
                local_time_fields=local_fields,
                utc_time_fields=utc_fields,
                time_formats=time_formats,
                timezone_name=ns.timezone,
                event_date=event_date,
                local_time_property=ns.local_time_property,
                utc_time_property=ns.utc_time_property,
            )
        except FileNotFoundError as exc:
            raise SystemExit(str(exc)) from exc
        return 0

    p_csv = subparsers.add_parser(
        "csv-to-geojson",
        help="Convert CSV latitude/longitude rows to GeoJSON points",
        description=(
            "Convert a tabular CSV with latitude/longitude columns into GeoJSON points, optionally normalizing local timestamps."
        ),
    )
    p_csv.add_argument("--input", required=True, help="Path to CSV file")
    p_csv.add_argument(
        "--lat-field",
        default="Lat",
        help="Column containing latitude values (default: Lat)",
    )
    p_csv.add_argument(
        "--lon-field",
        default="Lon",
        help="Column containing longitude values (default: Lon)",
    )
    p_csv.add_argument(
        "--local-time-field",
        dest="local_time_fields",
        action="append",
        help="Column containing local time strings (repeatable)",
    )
    p_csv.add_argument(
        "--utc-time-field",
        dest="utc_time_fields",
        action="append",
        help="Column containing UTC time strings (HH:MM, repeatable)",
    )
    p_csv.add_argument(
        "--time-format",
        dest="time_formats",
        action="append",
        help="Custom strptime format for local time strings (repeatable)",
    )
    p_csv.add_argument(
        "--timezone",
        default="UTC",
        help="Local timezone name for interpreting local time strings",
    )
    p_csv.add_argument(
        "--event-date",
        help="Event date (YYYY-MM-DD) used when local/UTC fields omit a date",
    )
    p_csv.add_argument(
        "--local-time-property",
        default="time_local_iso",
        help="Output property name for normalized local timestamp",
    )
    p_csv.add_argument(
        "--utc-time-property",
        default="time_utc_iso",
        help="Output property name for normalized UTC timestamp",
    )
    p_csv.add_argument(
        "--indent",
        type=int,
        default=2,
        help="Indentation level for GeoJSON output",
    )
    add_output_option(p_csv)
    p_csv.add_argument(
        "--verbose", action="store_true", help="Verbose logging for this command"
    )
    p_csv.add_argument(
        "--quiet", action="store_true", help="Quiet logging for this command"
    )
    p_csv.add_argument(
        "--trace",
        action="store_true",
        help="Shell-style trace of key steps and external commands",
    )
    p_csv.set_defaults(func=_cmd_csv_to_geojson)
