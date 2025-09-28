# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

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
    timestamps: list[datetime] = []
    if datetime_format:
        dm = DateManager([datetime_format])
        timestamps = dm.parse_timestamps_from_filenames(names, datetime_format)
    else:
        dm = DateManager()
        for n in names:
            s = dm.extract_date_time(n)
            if s:
                from contextlib import suppress

                with suppress(Exception):
                    timestamps.append(datetime.fromisoformat(s))
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


def register_cli(subparsers: Any) -> None:
    """Register transform subcommands (metadata, enrich-metadata, enrich-datasets, update-dataset-json)."""

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
