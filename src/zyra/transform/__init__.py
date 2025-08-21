from __future__ import annotations

import argparse
import json
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
    configure_logging_from_env()
    meta = _compute_frames_metadata(
        ns.frames_dir,
        pattern=ns.pattern,
        datetime_format=ns.datetime_format,
        period_seconds=ns.period_seconds,
    )
    payload = (json.dumps(meta, indent=2) + "\n").encode("utf-8")
    # Write to stdout or file
    with open_output(ns.output) as f:
        f.write(payload)
    return 0


def register_cli(subparsers: Any) -> None:
    """Register transform subcommands (metadata, enrich-metadata, update-dataset-json)."""
    p = subparsers.add_parser("metadata", help="Compute frames metadata as JSON")
    p.add_argument(
        "--frames-dir",
        required=True,
        dest="frames_dir",
        help="Directory containing frames",
    )
    p.add_argument("--pattern", help="Regex filter for frame filenames")
    p.add_argument(
        "--datetime-format",
        dest="datetime_format",
        help="Datetime format used in filenames (e.g., %Y%m%d%H%M%S)",
    )
    p.add_argument(
        "--period-seconds", type=int, help="Expected cadence to compute missing frames"
    )
    from zyra.cli_common import add_output_option

    add_output_option(p)
    p.set_defaults(func=_cmd_metadata)

    # Enrich metadata with dataset_id, vimeo_uri, and updated_at
    def _cmd_enrich(ns: argparse.Namespace) -> int:
        """CLI: enrich a frames metadata JSON with dataset id and Vimeo URI.

        Accepts a base metadata JSON (e.g., from ``metadata``), merges optional
        ``dataset_id`` and ``vimeo_uri`` (read from arg or stdin), and stamps
        ``updated_at``.
        """
        configure_logging_from_env()
        from zyra.utils.json_file_manager import JSONFileManager

        fm = JSONFileManager()
        # Load base metadata JSON from file
        try:
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
            try:
                import sys

                data = sys.stdin.buffer.read().decode("utf-8", errors="ignore").strip()
                if data:
                    vuri = data.splitlines()[0].strip()
            except Exception:
                pass
        if vuri:
            base["vimeo_uri"] = vuri
        # Add updated_at timestamp
        base["updated_at"] = datetime.now().replace(microsecond=0).isoformat()
        payload = (json.dumps(base, indent=2) + "\n").encode("utf-8")
        with open_output(ns.output) as f:
            f.write(payload)
        return 0

    p2 = subparsers.add_parser(
        "enrich-metadata", help="Enrich frames metadata with dataset id and Vimeo URI"
    )
    p2.add_argument(
        "--frames-meta",
        required=True,
        dest="frames_meta",
        help="Path to frames metadata JSON",
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
    p2.set_defaults(func=_cmd_enrich)

    # Update a dataset.json entry's startTime/endTime (and optionally dataLink) by dataset id
    def _cmd_update_dataset(ns: argparse.Namespace) -> int:
        """CLI: update an entry in dataset.json by dataset id.

        Loads a dataset index JSON from a local path or URL (HTTP or s3),
        updates the entry matching ``--dataset-id`` with ``startTime`` and
        ``endTime`` (from metadata or explicit flags), and optionally updates
        ``dataLink`` from a Vimeo URI. Writes the updated JSON to ``--output``.
        """
        configure_logging_from_env()
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
            try:
                import sys

                js = sys.stdin.buffer.read().decode("utf-8", errors="ignore")
                meta2 = json.loads(js)
                start = start or meta2.get("start_datetime")
                end = end or meta2.get("end_datetime")
                vimeo_uri = vimeo_uri or meta2.get("vimeo_uri")
            except Exception:
                pass
        # Parse dataset JSON
        try:
            data = json.loads(raw.decode("utf-8", errors="ignore"))
        except Exception as exc:
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
    p3.set_defaults(func=_cmd_update_dataset)
