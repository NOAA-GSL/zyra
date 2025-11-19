# SPDX-License-Identifier: Apache-2.0
"""CesiumJS-based interactive globe renderer.

The generated bundle references Cesium assets via jsDelivr CDN. Future
iterations can add an option to vendor or pin a local copy if offline support
is required.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from textwrap import dedent

from zyra.utils.date_manager import DateManager

from .base import InteractiveBundle, InteractiveRenderer
from .frame_utils import finalize_frame_entries, load_manifest_entries
from .probe_utils import ProbeDatasetError, prepare_probe_dataset_file
from .registry import register
from .video_utils import (
    VideoExtractionError,
    compute_end_time,
    compute_frame_timestamps,
    extract_frames,
    format_datetime,
    parse_datetime,
    probe_video_metadata,
    resolve_video_source,
)

LOGGER = logging.getLogger(__name__)


def _format_display_timestamp(dt: datetime) -> str:
    """Render a display-friendly UTC label for timeline timestamps."""

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


def _coerce_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _is_remote_ref(value: object) -> bool:
    if not isinstance(value, str):
        return False
    lower = value.lower()
    return lower.startswith(("http://", "https://", "http:/", "https:/"))


def _normalize_remote_ref(value: str) -> str:
    lower = value.lower()
    if lower.startswith(("http://", "https://")):
        return value
    if lower.startswith(("http:/", "https:/")):
        scheme, rest = value.split(":/", 1)
        return f"{scheme}://{rest.lstrip('/')}"
    return value


def _video_elapsed_seconds(start, timestamp: str) -> float:
    try:
        end = parse_datetime(timestamp)
    except Exception:
        return 0.0
    delta = end - start
    return max(delta.total_seconds(), 0.0)


@register
class CesiumGlobeRenderer(InteractiveRenderer):
    slug = "cesium-globe"
    description = "CesiumJS globe renderer that emits a standalone bundle."

    def __init__(self, **options: object) -> None:
        super().__init__(**options)
        self._video_entries: list[dict[str, object]] | None = None

    def build(self, *, output_dir: Path) -> InteractiveBundle:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        assets_dir = output_dir / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)

        index_html = output_dir / "index.html"
        script_path = assets_dir / "cesium.js"
        config_path = assets_dir / "config.json"

        asset_overrides, asset_files = self._stage_assets(assets_dir)

        config = self._sanitized_config(overrides=asset_overrides)
        config_json = json.dumps(config, indent=2)
        config_path.write_text(config_json + "\n", encoding="utf-8")

        credentials = self._credential_payload()

        index_html.write_text(
            self._render_index_html(config, credentials), encoding="utf-8"
        )
        script_path.write_text(self._render_script(), encoding="utf-8")

        return InteractiveBundle(
            output_dir=output_dir,
            index_html=index_html,
            assets=(script_path, config_path, *asset_files),
        )

    def _stage_assets(
        self, assets_dir: Path
    ) -> tuple[dict[str, object], tuple[Path, ...]]:
        """Copy optional assets (gradients, LUTs, textures) into bundle."""

        staged: list[Path] = []
        overrides: dict[str, object] = {}

        gradients_dir = assets_dir / "gradients"
        textures_dir = assets_dir / "textures"
        data_dir = assets_dir / "data"
        legends_dir = assets_dir / "legends"

        video_meta = self._maybe_generate_video_frames(assets_dir)

        texture = self._options.get("texture")
        if texture:
            if _is_remote_ref(texture):
                overrides["texture"] = _normalize_remote_ref(str(texture))
            else:
                staged.append(
                    self._copy_asset(Path(texture), textures_dir, overrides, "texture")
                )

        probe_gradient = self._options.get("probe_gradient")
        if probe_gradient:
            if _is_remote_ref(probe_gradient):
                overrides["probe_gradient"] = _normalize_remote_ref(str(probe_gradient))
            else:
                staged.append(
                    self._copy_asset(
                        Path(probe_gradient), gradients_dir, overrides, "probe_gradient"
                    )
                )

        probe_lut = self._options.get("probe_lut")
        if probe_lut:
            if _is_remote_ref(probe_lut):
                overrides["probe_lut"] = _normalize_remote_ref(str(probe_lut))
            else:
                staged.append(
                    self._copy_asset(
                        Path(probe_lut), gradients_dir, overrides, "probe_lut"
                    )
                )

        probe_data = self._options.get("probe_data")
        if probe_data:
            if _is_remote_ref(probe_data):
                overrides["probe_data"] = _normalize_remote_ref(str(probe_data))
            else:
                converted = self._try_convert_probe_dataset(data_dir, Path(probe_data))
                if converted is not None:
                    dest_path, meta = converted
                    rel_path = Path("assets") / "data" / dest_path.name
                    overrides["probe_data"] = str(rel_path)
                    staged.append(dest_path)
                    if (
                        meta.get("units")
                        and "probe_units" not in overrides
                        and "probe_units" not in self._options
                    ):
                        overrides["probe_units"] = meta["units"]
                else:
                    staged.append(
                        self._copy_asset(
                            Path(probe_data), data_dir, overrides, "probe_data"
                        )
                    )

        legend_source = self._options.get("legend")
        if legend_source is None:
            legend_source = self._options.get("legend_texture")
        if legend_source:
            if _is_remote_ref(legend_source):
                overrides["legend"] = _normalize_remote_ref(str(legend_source))
            else:
                staged.append(
                    self._copy_asset(
                        Path(legend_source), legends_dir, overrides, "legend"
                    )
                )
        overrides.pop("legend_texture", None)

        frame_entries = self._collect_frames()
        if frame_entries:
            frames_dir = textures_dir
            frames_dir.mkdir(parents=True, exist_ok=True)
            staged_paths: list[Path] = []
            manifest: list[dict[str, object]] = []
            for entry in frame_entries:
                raw_path = str(entry["path"])
                timestamp = entry.get("timestamp")
                display_ts = entry.get("display_timestamp")
                metadata = (
                    entry.get("metadata")
                    if isinstance(entry.get("metadata"), dict)
                    else None
                )
                label = entry.get("label")
                if _is_remote_ref(raw_path):
                    manifest_entry: dict[str, object] = {
                        "path": _normalize_remote_ref(raw_path)
                    }
                    if timestamp:
                        manifest_entry["timestamp"] = timestamp
                    if display_ts:
                        manifest_entry["display_timestamp"] = display_ts
                    if label:
                        manifest_entry["label"] = label
                    if metadata:
                        manifest_entry["metadata"] = metadata
                    manifest.append(manifest_entry)
                    continue
                src = Path(raw_path).expanduser()
                if not src.is_file():
                    msg = f"Frame file not found: {src}"
                    raise FileNotFoundError(msg)
                dest = frames_dir / src.name
                if src.resolve() != dest.resolve():
                    dest.write_bytes(src.read_bytes())
                staged_paths.append(dest)
                manifest_entry = {"path": f"assets/textures/{src.name}"}
                if timestamp:
                    manifest_entry["timestamp"] = timestamp
                if display_ts:
                    manifest_entry["display_timestamp"] = display_ts
                if label:
                    manifest_entry["label"] = label
                if metadata:
                    manifest_entry["metadata"] = metadata
                manifest.append(manifest_entry)
            overrides["frames"] = manifest
            overrides.setdefault("texture", manifest[0]["path"])
            staged.extend(staged_paths)

        tile_url = self._options.get("tile_url")
        if isinstance(tile_url, str) and _is_remote_ref(tile_url):
            overrides["tile_url"] = _normalize_remote_ref(tile_url)

        shared_gradients = self._options.get("shared_gradients")
        if isinstance(shared_gradients, dict) and shared_gradients:
            shared_dir = gradients_dir / "shared"
            shared_overrides: dict[str, str] = {}
            for name, raw_value in shared_gradients.items():
                key = str(name).strip()
                if not key:
                    continue
                if _is_remote_ref(raw_value):
                    shared_overrides[key] = _normalize_remote_ref(str(raw_value))
                    continue
                src = Path(str(raw_value)).expanduser()
                if not src.is_file():
                    msg = f"Shared gradient '{key}' file not found: {src}"
                    raise FileNotFoundError(msg)
                shared_dir.mkdir(parents=True, exist_ok=True)
                dest = shared_dir / src.name
                if src.resolve() != dest.resolve():
                    dest.write_bytes(src.read_bytes())
                staged.append(dest)
                shared_overrides[key] = f"assets/gradients/shared/{dest.name}"
            if shared_overrides:
                overrides["shared_gradients"] = shared_overrides

        if video_meta:
            overrides.update(video_meta)

        return overrides, tuple(staged)

    def _maybe_generate_video_frames(self, assets_dir: Path) -> dict[str, object]:
        video_source = self._options.get("video_source")
        if not video_source:
            self._video_entries = None
            return {}
        entries, meta = self._extract_video_frames(assets_dir)
        self._video_entries = entries
        for key, value in (meta or {}).items():
            if value is None:
                continue
            if key == "frame_duration" and self._options.get("frame_duration") not in (
                None,
                0,
                "",
            ):
                continue
            self._options[key] = value
        return meta

    def _load_timeline_overrides(
        self,
    ) -> tuple[datetime | None, float | None, str | None]:
        """Return optional (start, period, source) overrides for frame timelines."""

        start_override: datetime | None = None
        period_override: float | None = None
        source: str | None = None

        frames_meta_path = self._options.get("frames_meta")
        if frames_meta_path:
            try:
                meta_path = Path(frames_meta_path).expanduser()
                data = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception as exc:  # pragma: no cover - filesystem dependent
                LOGGER.warning(
                    "Failed to load frames metadata '%s': %s", frames_meta_path, exc
                )
            else:
                raw_start = data.get("start_datetime") or data.get("start")
                raw_period = (
                    data.get("period_seconds")
                    or data.get("cadence_seconds")
                    or data.get("interval_seconds")
                )
                if raw_start:
                    try:
                        start_override = _coerce_utc(parse_datetime(str(raw_start)))
                    except Exception as exc:  # pragma: no cover
                        LOGGER.warning(
                            "Invalid start_datetime in frames metadata '%s': %s",
                            frames_meta_path,
                            exc,
                        )
                if raw_period not in (None, ""):
                    try:
                        period_override = float(raw_period)
                    except (TypeError, ValueError) as exc:  # pragma: no cover
                        LOGGER.warning(
                            "Invalid period_seconds in frames metadata '%s': %s",
                            frames_meta_path,
                            exc,
                        )
                source = "frames-meta"

        period_option = self._options.get("period_seconds")
        if period_option not in (None, ""):
            try:
                period_override = float(period_option)
                source = "period-seconds"
            except (TypeError, ValueError) as exc:  # pragma: no cover
                LOGGER.warning(
                    "Ignoring invalid period_seconds override '%s': %s",
                    period_option,
                    exc,
                )

        return start_override, period_override, source

    def _apply_timeline_overrides(
        self,
        entries: list[dict[str, object]],
        *,
        default_start: datetime,
        overrides: tuple[datetime | None, float | None, str | None],
    ) -> dict[str, object]:
        """Adjust frame timestamps/metadata based on cadence overrides."""

        start_override, period_override, source = overrides
        start_override = _coerce_utc(start_override)
        default_start = _coerce_utc(default_start)
        updates: dict[str, object] = {}

        if start_override is None and period_override in (None, 0):
            return updates

        base_start = start_override or default_start
        base_start = _coerce_utc(base_start)

        if (
            period_override is not None
            and period_override > 0
            and base_start is not None
            and entries
        ):
            step = timedelta(seconds=float(period_override))
            for idx, entry in enumerate(entries):
                ts = base_start + step * idx
                entry["timestamp"] = format_datetime(ts)
                entry["display_timestamp"] = _format_display_timestamp(ts)
                meta = entry.setdefault("metadata", {})
                meta["elapsed_seconds"] = float((ts - base_start).total_seconds())
            updates["video_start"] = format_datetime(base_start)
            updates["video_end"] = format_datetime(
                base_start + step * max(len(entries) - 1, 0)
            )
            updates["timeline_period_seconds"] = step.total_seconds()
            if source:
                updates["timeline_source"] = source
            return updates

        if start_override is not None and entries:
            first_raw = entries[0].get("timestamp")
            last_raw = entries[-1].get("timestamp")
            try:
                first_dt = (
                    _coerce_utc(parse_datetime(str(first_raw)))
                    if first_raw
                    else default_start
                )
            except Exception:
                first_dt = default_start
            try:
                last_dt = (
                    _coerce_utc(parse_datetime(str(last_raw)))
                    if last_raw
                    else default_start
                )
            except Exception:
                last_dt = default_start

            if first_dt is None or last_dt is None:
                return updates

            delta = start_override - first_dt
            for entry in entries:
                raw = entry.get("timestamp")
                if not raw:
                    continue
                try:
                    ts = _coerce_utc(parse_datetime(str(raw))) + delta
                except Exception:
                    continue
                entry["timestamp"] = format_datetime(ts)
                entry["display_timestamp"] = _format_display_timestamp(ts)
                meta = entry.setdefault("metadata", {})
                meta["elapsed_seconds"] = float((ts - start_override).total_seconds())
            updates["video_start"] = format_datetime(start_override)
            updates["video_end"] = format_datetime(last_dt + delta)
            if source and "timeline_source" not in updates:
                updates["timeline_source"] = source
        return updates

    def _extract_video_frames(
        self, assets_dir: Path
    ) -> tuple[list[dict[str, object]], dict[str, object]]:
        video_source = str(self._options.get("video_source"))
        credentials = self._options.get("credentials") or {}
        frame_cache_option = self._options.get("frame_cache")
        if frame_cache_option:
            frame_cache = Path(frame_cache_option)
            if not frame_cache.is_absolute():
                frame_cache = Path.cwd() / frame_cache
        else:
            frame_cache = assets_dir / "_video_cache"
        frame_cache.mkdir(parents=True, exist_ok=True)

        try:
            video_url = resolve_video_source(video_source, credentials)
        except Exception as exc:  # pragma: no cover - Vimeo/network dependent
            raise VideoExtractionError(str(exc)) from exc

        fps = float(self._options.get("video_fps") or 1.0)
        metadata = probe_video_metadata(video_url)

        overrides = self._load_timeline_overrides()
        start_override, period_override, source = overrides

        start_value = self._options.get("video_start")
        if start_value:
            start_dt = parse_datetime(str(start_value))
        elif start_override:
            start_dt = start_override
            self._options["video_start"] = format_datetime(start_dt)
        else:
            raise VideoExtractionError(
                "--video-start is required when extracting frames from a video source."
            )

        end_value = self._options.get("video_end")
        frames = extract_frames(video_url, output_dir=frame_cache, fps=fps)

        if end_value:
            end_dt = parse_datetime(str(end_value))
        else:
            end_dt = compute_end_time(start_dt, len(frames), fps)

        entries = compute_frame_timestamps(
            frames=frames,
            start_time=start_dt,
            fps=fps,
        )

        for entry in entries:
            entry_metadata = entry.setdefault("metadata", {})
            entry_metadata["elapsed_seconds"] = _video_elapsed_seconds(
                start_dt, entry["timestamp"]
            )

        frame_duration = 1.0 / fps if fps > 0 else None
        meta_payload = {
            "video_start": format_datetime(start_dt),
            "video_end": format_datetime(end_dt),
            "video_duration_seconds": metadata.duration_seconds,
            "video_fps": fps,
            "frame_duration": frame_duration,
        }
        timeline_updates = self._apply_timeline_overrides(
            entries, default_start=start_dt, overrides=overrides
        )
        if timeline_updates:
            meta_payload.update(timeline_updates)
        return entries, meta_payload

    def _collect_frames(self) -> list[dict[str, object]]:
        pattern = self._options.get("texture_pattern")
        frame_list = self._options.get("frame_list")
        date_format = self._options.get("date_format")
        time_key = self._options.get("time_key")
        time_format = self._options.get("time_format")

        parse_formats: list[str] = []
        if date_format:
            parse_formats.append(str(date_format))
        if time_format and time_format not in parse_formats:
            parse_formats.append(str(time_format))

        try:
            filename_date_manager: DateManager | None = (
                DateManager([date_format]) if date_format else DateManager([])
            )
        except Exception:
            filename_date_manager = None

        entries: list[dict[str, object]] = []
        if self._video_entries:
            entries.extend(self._video_entries)
        if pattern:
            base = Path(pattern)
            for path in sorted(base.parent.glob(base.name)):
                payload: dict[str, object] = {"path": str(path)}
                timestamp = self._infer_frame_timestamp(
                    path.name, filename_date_manager
                )
                if timestamp:
                    payload["timestamp"] = timestamp
                entries.append(payload)

        if frame_list:
            frame_file = Path(frame_list)
            if not frame_file.is_file():
                msg = f"Frame list file not found: {frame_file}"
                raise FileNotFoundError(msg)

            text = frame_file.read_text(encoding="utf-8")
            manifest_entries = load_manifest_entries(text)
            if manifest_entries is not None:
                for item in manifest_entries:
                    path_value = item.get("path")
                    if isinstance(path_value, str) and not _is_remote_ref(path_value):
                        path_obj = Path(path_value)
                        if not path_obj.is_absolute():
                            path_obj = (frame_file.parent / path_obj).resolve()
                        item["path"] = str(path_obj)
                entries.extend(manifest_entries)
            else:
                base_dir = frame_file.parent
                for line in text.splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split()
                    raw_path = parts[0]
                    if not _is_remote_ref(raw_path):
                        path_obj = Path(raw_path)
                        if not path_obj.is_absolute():
                            raw_path = str((base_dir / path_obj).resolve())
                    payload: dict[str, object] = {"path": raw_path}
                    if len(parts) > 1:
                        payload["timestamp"] = " ".join(parts[1:])
                    elif filename_date_manager:
                        timestamp = self._infer_frame_timestamp(
                            parts[0], filename_date_manager
                        )
                        if timestamp:
                            payload["timestamp"] = timestamp
                    entries.append(payload)

        finalized = finalize_frame_entries(
            entries,
            time_key=time_key,
            parse_formats=parse_formats,
            display_format=time_format,
        )

        seen: set[tuple[str, str | None]] = set()
        unique_entries: list[dict[str, object]] = []
        for entry in finalized:
            key = (entry["path"], entry.get("timestamp"))
            if key in seen:
                continue
            seen.add(key)
            unique_entries.append(entry)
        return unique_entries

    @staticmethod
    def _infer_frame_timestamp(
        filename: str, date_manager: DateManager | None
    ) -> str | None:
        if not date_manager:
            return None
        try:
            extracted = date_manager.extract_date_time(filename)
        except Exception:
            return None
        return extracted

    def _try_convert_probe_dataset(
        self, data_dir: Path, source: Path
    ) -> tuple[Path, dict[str, object]] | None:
        try:
            dest, metadata = prepare_probe_dataset_file(
                source,
                data_dir,
                variable=self._options.get("probe_var"),
            )
        except ProbeDatasetError:
            return None
        return dest, metadata

    def _maybe_generate_video_frames(self, assets_dir: Path) -> dict[str, object]:
        video_source = self._options.get("video_source")
        if not video_source:
            self._video_entries = None
            return {}
        entries, meta = self._extract_video_frames(assets_dir)
        self._video_entries = entries
        for key, value in (meta or {}).items():
            if value is None:
                continue
            if key == "frame_duration" and self._options.get("frame_duration") not in (
                None,
                0,
                "",
            ):
                continue
            self._options[key] = value
        return meta

    def _extract_video_frames(
        self, assets_dir: Path
    ) -> tuple[list[dict[str, object]], dict[str, object]]:
        video_source = str(self._options.get("video_source"))
        credentials = self._options.get("credentials") or {}
        frame_cache_option = self._options.get("frame_cache")
        if frame_cache_option:
            frame_cache = Path(frame_cache_option)
            if not frame_cache.is_absolute():
                frame_cache = Path.cwd() / frame_cache
        else:
            frame_cache = assets_dir / "_video_cache"
        frame_cache.mkdir(parents=True, exist_ok=True)

        try:
            video_url = resolve_video_source(video_source, credentials)
        except Exception as exc:  # pragma: no cover - Vimeo/network dependent
            raise VideoExtractionError(str(exc)) from exc

        fps = float(self._options.get("video_fps") or 1.0)
        metadata = probe_video_metadata(video_url)

        overrides = self._load_timeline_overrides()
        start_override, period_override, source = overrides

        start_value = self._options.get("video_start")
        if start_value:
            start_dt = parse_datetime(str(start_value))
        elif start_override:
            start_dt = start_override
            self._options["video_start"] = format_datetime(start_dt)
        else:
            raise VideoExtractionError(
                "--video-start is required when extracting frames from a video source."
            )

        end_value = self._options.get("video_end")
        frames = extract_frames(video_url, output_dir=frame_cache, fps=fps)

        if end_value:
            end_dt = parse_datetime(str(end_value))
        else:
            end_dt = compute_end_time(start_dt, len(frames), fps)

        entries = compute_frame_timestamps(
            frames=frames,
            start_time=start_dt,
            fps=fps,
        )

        for entry in entries:
            entry_metadata = entry.setdefault("metadata", {})
            entry_metadata["elapsed_seconds"] = _video_elapsed_seconds(
                start_dt, entry["timestamp"]
            )

        meta_payload = {
            "video_start": format_datetime(start_dt),
            "video_end": format_datetime(end_dt),
            "video_duration_seconds": metadata.duration_seconds,
            "video_fps": fps,
        }
        timeline_updates = self._apply_timeline_overrides(
            entries, default_start=start_dt, overrides=overrides
        )
        if timeline_updates:
            meta_payload.update(timeline_updates)
        return entries, meta_payload

    def _copy_asset(
        self,
        source: Path,
        target_dir: Path,
        overrides: dict[str, object],
        key: str,
    ) -> Path:
        source = source.expanduser()
        if not source.is_file():
            msg = f"{key.replace('_', ' ').capitalize()} file not found: {source}"
            raise FileNotFoundError(msg)
        target_dir.mkdir(parents=True, exist_ok=True)
        dest = target_dir / source.name
        if source.resolve() != dest.resolve():
            dest.write_bytes(source.read_bytes())
        rel_dir_map = {
            "probe_gradient": "gradients",
            "probe_lut": "gradients",
            "probe_data": "data",
            "legend": "legends",
        }
        rel_dir = rel_dir_map.get(key, "textures")
        overrides[key] = f"assets/{rel_dir}/{source.name}"
        return dest

    def _sanitized_config(
        self, *, overrides: dict[str, object] | None = None
    ) -> dict[str, object]:
        """Return a Cesium config with sensitive keys removed."""

        secrets = {
            "credentials",
            "auth",
            "credential_file",
            "cesium_ion_token",
            "credentials_masked",
            "texture",
            "probe_gradient",
            "probe_lut",
            "probe_data",
            "probe_var",
            "tile_token",
            "texture_pattern",
            "frame_list",
            "frame_cache",
            "show_controls",
            "shared_gradients",
            "video_source",
        }
        filtered = {
            key: value
            for key, value in self._options.items()
            if key not in secrets and value is not None
        }
        filtered.setdefault("width", None)
        filtered.setdefault("height", None)
        filtered.setdefault("animate", "none")
        filtered.setdefault("probe_enabled", True)
        filtered.setdefault("probe_height", False)
        filtered.setdefault("auto_rotate", False)
        filtered.setdefault("auto_rotate_speed", None)
        filtered.setdefault("terrain", "ellipsoid")
        filtered.setdefault("frame_duration", None)
        if overrides:
            filtered.update(overrides)
        return filtered

    def _credential_payload(self) -> dict[str, str]:
        """Return credentials to expose to the front-end bundle."""

        payload: dict[str, str] = {}
        credentials = self._options.get("credentials")
        if isinstance(credentials, dict):
            token = credentials.get("cesium_ion_token") or credentials.get(
                "cesium_ion_default_access_token"
            )
            tile_token = credentials.get("tile_token") or credentials.get("tileToken")
        else:
            token = None
            tile_token = None

        token = token or self._options.get("cesium_ion_token")
        if not token:
            token = os.environ.get("CESIUM_ION_TOKEN")
        if token:
            payload["cesiumIonDefaultAccessToken"] = token
        tile_token = tile_token or self._options.get("tile_token")
        if tile_token:
            payload["tileToken"] = tile_token
        return payload

    def _render_index_html(
        self, config: dict[str, object], credentials: dict[str, str]
    ) -> str:
        config_json = json.dumps(config, indent=2)
        creds_json = json.dumps(credentials, indent=2)
        html = f"""
            <!DOCTYPE html>
            <html lang="en">
              <head>
                <meta charset="utf-8" />
                <meta name="viewport" content="width=device-width, initial-scale=1" />
                <title>Zyra Cesium Globe</title>
                <link
                  rel="stylesheet"
                  href="https://cdn.jsdelivr.net/npm/cesium@1.114.0/Build/Cesium/Widgets/widgets.css"
                />
                <style>
                  html, body {{ margin: 0; padding: 0; width: 100%; height: 100%; background: #0b0d11; color: #f5f7fa; font-family: system-ui, sans-serif; }}
                  #zyra-cesium {{ width: 100%; height: 100%; display: block; position: relative; }}
                  #zyra-overlay {{ position: absolute; top: 16px; left: 16px; background: rgba(0, 0, 0, 0.55); padding: 12px 16px; border-radius: 8px; max-width: 320px; z-index: 100; backdrop-filter: blur(4px); }}
                  #zyra-overlay .overlay-title {{ font-weight: 600; font-size: 1rem; margin-bottom: 4px; }}
                  #zyra-overlay .overlay-description {{ font-size: 0.85rem; margin-bottom: 8px; color: rgba(245, 247, 250, 0.85); }}
                  #zyra-overlay .overlay-time {{ font-size: 0.85rem; margin-bottom: 6px; color: rgba(245, 247, 250, 0.85); }}
                  #zyra-overlay .overlay-meta {{ margin-top: 12px; font-size: 0.8rem; color: rgba(245, 247, 250, 0.75); }}
                  #zyra-overlay .overlay-meta p {{ margin: 0; }}
                  #zyra-overlay code {{ font-size: 0.85rem; }}
                  #zyra-probe {{ margin-top: 10px; font-size: 0.85rem; line-height: 1.35; }}
                  #zyra-probe .probe-header {{ font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 4px; font-size: 0.8rem; }}
                  #zyra-probe .probe-line {{ display: flex; align-items: center; gap: 6px; white-space: nowrap; }}
                  #zyra-probe .probe-label {{ min-width: 68px; color: rgba(245, 247, 250, 0.75); }}
                  #zyra-overlay .overlay-legend {{ margin-top: 12px; }}
                  #zyra-overlay .overlay-legend img {{ max-width: 260px; width: 100%; height: auto; display: block; border: 1px solid rgba(245, 247, 250, 0.35); border-radius: 4px; }}
                </style>
              </head>
              <body>
                <div id="zyra-cesium">
                  <div id="zyra-overlay" data-probe-container>
                    <div class="overlay-title" data-overlay-title style="display:none;"></div>
                    <div class="overlay-description" data-overlay-description style="display:none;"></div>
                    <div class="overlay-time" data-overlay-time style="display:none;"></div>
                    <div class="overlay-legend" data-legend style="display:none;"></div>
                    <div class="overlay-meta" data-overlay-meta style="display:none;">
                      <strong>Zyra Cesium Globe (beta)</strong>
                      <p>Renderer target: <code>{self.slug}</code></p>
                    </div>
                    <div id="zyra-probe">
                      <div class="probe-header">Probe</div>
                      <div class="probe-line"><span class="probe-label">Latitude</span><span data-probe-lat>—</span></div>
                      <div class="probe-line"><span class="probe-label">Longitude</span><span data-probe-lon>—</span></div>
                      <div class="probe-line" data-probe-height-row><span class="probe-label">Height</span><span data-probe-height>—</span></div>
                      <div class="probe-line"><span class="probe-label">Value</span><span data-probe-value>—</span></div>
                      <div class="probe-line"><span class="probe-label">Units</span><span data-probe-units>—</span></div>
                      <div class="probe-line"><span class="probe-label">Gradient</span><span data-probe-gradient>—</span></div>
                      <div class="probe-line"><span class="probe-label">LUT</span><span data-probe-lut>—</span></div>
                    </div>
                  </div>
                </div>
                <script>
                  window.ZYRA_GLOBE_CONFIG = {config_json};
                  window.ZYRA_GLOBE_CREDENTIALS = {creds_json};
                </script>
                <script src="https://cdn.jsdelivr.net/npm/cesium@1.114.0/Build/Cesium/Cesium.js"></script>
                <script src="assets/cesium.js"></script>
              </body>
            </html>
        """
        return dedent(html).strip() + "\n"

    def _render_script(self) -> str:
        return (
            dedent(
                """
(async function () {
  const config = window.ZYRA_GLOBE_CONFIG || {};
  const container = document.getElementById("zyra-cesium");
  const overlay = document.getElementById("zyra-overlay");

  const formatDisplayTime = (value) => {
    if (value == null) {
      return "";
    }
    const raw = String(value).trim();
    if (!raw) {
      return "";
    }
    let candidate = raw;
    if (!candidate.includes("T")) {
      candidate = `${candidate}T00:00:00`;
    }
    if (!/[zZ]$/.test(candidate) && !/[+-]\\d{2}:?\\d{2}$/.test(candidate)) {
      candidate = `${candidate}Z`;
    }
    const date = new Date(candidate);
    if (Number.isNaN(date.getTime())) {
      return raw;
    }
    return date.toISOString().replace("T", " ").replace("Z", " UTC");
  };

  const rawFrameList = Array.isArray(config.frames) ? config.frames : null;
  const frameDurationSeconds = Math.max(Number(config.frame_duration) || 3600, 0.1);
  const normalizedFrames = [];
  if (rawFrameList && rawFrameList.length) {
    let fallbackEpoch = Date.UTC(2000, 0, 1);
    rawFrameList.forEach((entry) => {
      if (!entry || typeof entry.path !== "string") {
        return;
      }
      const path = entry.path;
      const rawTimestamp = entry.timestamp;
      const providedDisplay =
        typeof entry.display_timestamp === "string" && entry.display_timestamp.trim()
          ? entry.display_timestamp.trim()
          : typeof entry.display === "string" && entry.display.trim()
            ? entry.display.trim()
            : null;
      const label =
        typeof entry.label === "string" && entry.label.trim() ? entry.label.trim() : null;
      const metadata =
        entry.metadata && typeof entry.metadata === "object" ? { ...entry.metadata } : null;

      let iso = null;
      if (typeof rawTimestamp === "number" && Number.isFinite(rawTimestamp)) {
        const seconds = rawTimestamp > 1e12 ? rawTimestamp / 1000 : rawTimestamp;
        iso = new Date(seconds * 1000).toISOString();
      } else if (typeof rawTimestamp === "string" && rawTimestamp.trim()) {
        let candidate = rawTimestamp.trim();
        if (!candidate.includes("T")) {
          candidate = `${candidate}T00:00:00`;
        }
        if (!/[zZ]$/.test(candidate) && !/[+-]\\d{2}:?\\d{2}$/.test(candidate)) {
          candidate = `${candidate}Z`;
        }
        const date = new Date(candidate);
        if (!Number.isNaN(date.getTime())) {
          iso = date.toISOString();
        }
      } else if (rawTimestamp != null) {
        const date = new Date(rawTimestamp);
        if (!Number.isNaN(date.getTime())) {
          iso = date.toISOString();
        }
      }

      if (!iso) {
        const date = new Date(fallbackEpoch);
        fallbackEpoch += frameDurationSeconds * 1000;
        iso = date.toISOString();
      }

      let display = providedDisplay || label || null;
      if (!display) {
        display = formatDisplayTime(iso);
      }

      const frameRecord = { path, iso, display };
      if (metadata) {
        frameRecord.metadata = metadata;
      }
      if (label) {
        frameRecord.label = label;
      }
      normalizedFrames.push(frameRecord);
    });
  }
  const hasFrameStack = normalizedFrames.length > 0;

  if (!window.Cesium) {
    overlay.innerHTML = "<strong>Cesium failed to load.</strong>";
    return;
  }

  const credentials = window.ZYRA_GLOBE_CREDENTIALS || {};
  if (credentials.cesiumIonDefaultAccessToken) {
    Cesium.Ion.defaultAccessToken = credentials.cesiumIonDefaultAccessToken;
  }
  const tileToken = credentials.tileToken || null;

  let frameEntries = null;
  if (hasFrameStack) {
    frameEntries = normalizedFrames
      .map((entry, index) => {
        try {
          return {
            ...entry,
            index,
            julian: Cesium.JulianDate.fromIso8601(entry.iso),
            stop: null,
          };
        } catch (error) {
          console.warn(
            "Cesium globe: failed to parse frame timestamp",
            entry.iso,
            error,
          );
          return null;
        }
      })
      .filter((entry) => entry && entry.julian);
    frameEntries.sort((a, b) => Cesium.JulianDate.compare(a.julian, b.julian));
    if (!frameEntries.length) {
      frameEntries = null;
    }
  }
  const frameStackActive = Boolean(frameEntries && frameEntries.length);
  let frameStepSeconds = frameDurationSeconds;

  if (frameEntries) {
    if (frameEntries.length > 1) {
      const deltaSeconds = Cesium.JulianDate.secondsDifference(
        frameEntries[1].julian,
        frameEntries[0].julian,
      );
      if (Number.isFinite(deltaSeconds) && deltaSeconds > 0) {
        frameStepSeconds = deltaSeconds;
      }
    }
    for (let i = 0; i < frameEntries.length; i += 1) {
      const entry = frameEntries[i];
      const next = frameEntries[i + 1];
      if (
        next &&
        Cesium.JulianDate.greaterThan(next.julian, entry.julian)
      ) {
        entry.stop = Cesium.JulianDate.clone(next.julian);
      } else {
        entry.stop = Cesium.JulianDate.addSeconds(
          entry.julian,
          frameStepSeconds,
          new Cesium.JulianDate(),
        );
      }
    }
  }

  const latEl = document.querySelector("[data-probe-lat]");
  const lonEl = document.querySelector("[data-probe-lon]");
  const heightEl = document.querySelector("[data-probe-height]");
  const heightRow = document.querySelector("[data-probe-height-row]");
  const gradientEl = document.querySelector("[data-probe-gradient]");
  const lutEl = document.querySelector("[data-probe-lut]");
  const valueEl = document.querySelector("[data-probe-value]");
  const unitsEl = document.querySelector("[data-probe-units]");
  const legendEl = document.querySelector("[data-legend]");
  const titleEl = document.querySelector("[data-overlay-title]");
  const descriptionEl = document.querySelector("[data-overlay-description]");
  const timeEl = document.querySelector("[data-overlay-time]");
  const metaEl = document.querySelector("[data-overlay-meta]");
  const probeContainer = document.getElementById("zyra-probe");

  const toFiniteNumber = (value) => {
    const num = Number(value);
    return Number.isFinite(num) ? num : undefined;
  };

  const tileUrl =
    frameStackActive
      ? ""
      : typeof config.tile_url === "string"
        ? config.tile_url.trim()
        : "";
  const tileTypeRaw = config.tile_type;
  const tileType =
    typeof tileTypeRaw === "string" && tileTypeRaw
      ? tileTypeRaw.toLowerCase()
      : "arcgis";
  const tileCredit =
    typeof config.tile_credit === "string" ? config.tile_credit : undefined;
  const creditObject =
    tileCredit && Cesium.Credit ? new Cesium.Credit(tileCredit, true) : undefined;
  let tileMinLevel = toFiniteNumber(
    config.tile_min_level ?? config.tile_minimum_level,
  );
  let tileMaxLevel = toFiniteNumber(
    config.tile_max_level ?? config.tile_maximum_level,
  );
  if (
    tileMinLevel != null &&
    tileMaxLevel != null &&
    Number.isFinite(tileMinLevel) &&
    Number.isFinite(tileMaxLevel) &&
    tileMaxLevel < tileMinLevel
  ) {
    console.warn(
      `Cesium globe: tile_max_level (${tileMaxLevel}) is below tile_min_level (${tileMinLevel}); swapping values`,
    );
    const tmp = tileMinLevel;
    tileMinLevel = tileMaxLevel;
    tileMaxLevel = tmp;
  }
  let tileParams =
    config.tile_params && typeof config.tile_params === "object"
      ? { ...config.tile_params }
      : null;
  const tileTimeKeyRaw = config.tile_time_key;
  const tileTimeKey =
    typeof tileTimeKeyRaw === "string" && tileTimeKeyRaw.trim().length
      ? tileTimeKeyRaw.trim()
      : null;
  const tileTimeValues = Array.isArray(config.tile_time_values)
    ? config.tile_time_values
        .map((value) =>
          typeof value === "string" ? value.trim() : value,
        )
        .filter((value) => typeof value === "string" && value.length > 0)
    : null;
  if (tileParams && tileTimeKey) {
    delete tileParams[tileTimeKey];
  }
  const tileTimeMultiplier = toFiniteNumber(config.tile_time_multiplier) || 3600;
  const tileSchemeRaw =
    config.tile_scheme ?? config.tile_tiling_scheme ?? null;
  const tileSchemeMode =
    typeof tileSchemeRaw === "string" ? tileSchemeRaw.toLowerCase() : null;
  const hasDynamicTime =
    tileType === "template" &&
    tileTimeKey &&
    tileTimeValues &&
    tileTimeValues.length > 0;
  let dynamicLayerActive = false;
  const probeHeightRaw = config.probe_height;
  const probeHeightEnabled = !(
    probeHeightRaw === false ||
    probeHeightRaw === "false" ||
    probeHeightRaw === "False" ||
    probeHeightRaw === 0 ||
    probeHeightRaw === "0"
  );
  if (!probeHeightEnabled && heightRow) {
    heightRow.style.display = "none";
  }

  const width = config.width || window.innerWidth;
  const height = config.height || window.innerHeight;
  container.style.width = `${width}px`;
  container.style.height = `${height}px`;

  const animate = config.animate === "time" || frameStackActive;

  let terrainProvider = undefined;
  const terrainMode = (config.terrain || "ellipsoid").toString().toLowerCase();
  const wantsTerrain = !["ellipsoid", "none", "false", "0"].includes(terrainMode);
  if (wantsTerrain && Cesium.createWorldTerrainAsync) {
    try {
      terrainProvider = await Cesium.createWorldTerrainAsync();
    } catch (error) {
      console.warn("Cesium globe: failed to load world terrain, using ellipsoid", error);
      terrainProvider = undefined;
    }
  }

  const viewer = new Cesium.Viewer(container, {
    animation: animate,
    timeline: animate,
    baseLayerPicker: false,
    geocoder: false,
    homeButton: false,
    sceneModePicker: false,
    navigationHelpButton: false,
    infoBox: false,
    terrainProvider,
  });

  if (terrainProvider && viewer.scene?.globe) {
    viewer.scene.globe.depthTestAgainstTerrain = true;
  }

  const enableLighting = config.lighting == null ? true : Boolean(config.lighting);
  viewer.scene.globe.enableLighting = enableLighting;
  viewer.scene.skyAtmosphere.show = enableLighting;
  viewer.scene.skyBox = enableLighting ? new Cesium.SkyBox({ show: true }) : undefined;

  viewer.imageryLayers.removeAll();
  let baseProvider = null;
  if (frameStackActive && frameEntries) {
    dynamicLayerActive = true;

    const startTime = Cesium.JulianDate.clone(frameEntries[0].julian);
    const lastEntry = frameEntries[frameEntries.length - 1];
    const stopTime = Cesium.JulianDate.clone(lastEntry.stop);

    viewer.clock.startTime = Cesium.JulianDate.clone(startTime);
    viewer.clock.stopTime = Cesium.JulianDate.clone(stopTime);
    viewer.clock.currentTime = Cesium.JulianDate.clone(startTime);
    viewer.clock.clockRange = Cesium.ClockRange.CLAMPED;
    viewer.clock.clockStep = Cesium.ClockStep.SYSTEM_CLOCK_MULTIPLIER;
    viewer.clock.multiplier = frameStepSeconds;
    viewer.clock.shouldAnimate = config.animate === "time";
    if (viewer.timeline) {
      viewer.timeline.zoomTo(viewer.clock.startTime, viewer.clock.stopTime);
    }

    let activeFrameLayer = null;
    let pendingFrameLayer = null;
    let pendingFrameIndex = null;
    let lastFrameIndex = -1;

    const ensureLayerForFrame = (frameEntry, reason) => {
      if (!frameEntry) {
        return;
      }
      if (frameEntry.index === lastFrameIndex && activeFrameLayer) {
        return;
      }
      if (pendingFrameLayer) {
        if (pendingFrameIndex === frameEntry.index) {
          return;
        }
        viewer.imageryLayers.remove(pendingFrameLayer, true);
        pendingFrameLayer = null;
        pendingFrameIndex = null;
      }
      const providerOptions = {
        url: frameEntry.path,
        rectangle: Cesium.Rectangle.MAX_VALUE,
      };
      if (creditObject) {
        providerOptions.credit = creditObject;
      }
      console.debug("Cesium globe: configuring frame imagery provider", {
        url: providerOptions.url,
        reason,
      });
      const provider = new Cesium.SingleTileImageryProvider(providerOptions);
      let insertIndex = undefined;
      if (activeFrameLayer) {
        const existingIndex = viewer.imageryLayers.indexOf(activeFrameLayer);
        if (existingIndex >= 0) {
          insertIndex = existingIndex;
        }
      }
      const newLayer = viewer.imageryLayers.addImageryProvider(provider, insertIndex);
      newLayer.alpha = 0;
      newLayer.show = true;
      pendingFrameLayer = newLayer;
      pendingFrameIndex = frameEntry.index;

      const finalizeLayer = () => {
        if (pendingFrameLayer !== newLayer) {
          return;
        }
        pendingFrameLayer = null;
        pendingFrameIndex = null;
        const previousLayer = activeFrameLayer && activeFrameLayer !== newLayer ? activeFrameLayer : null;
        const fadeDurationMs = 250;
        const start = typeof performance !== "undefined" ? performance.now() : Date.now();

        const stepFade = (timestamp) => {
          const now = timestamp || (typeof performance !== "undefined" ? performance.now() : Date.now());
          const progress = Math.min((now - start) / fadeDurationMs, 1);
          newLayer.alpha = progress;
          if (previousLayer) {
            previousLayer.alpha = 1 - progress;
            previousLayer.show = true;
          }
          viewer.scene.requestRender();
          if (progress < 1) {
            if (typeof requestAnimationFrame === "function") {
              requestAnimationFrame(stepFade);
            } else {
              setTimeout(() => stepFade(), 16);
            }
          } else if (previousLayer) {
            try {
              if (!viewer.imageryLayers.contains || viewer.imageryLayers.contains(previousLayer)) {
                viewer.imageryLayers.remove(previousLayer, true);
              }
            } catch (error) {
              console.debug("Cesium globe: failed to remove previous frame layer", error);
            }
          }
        };

        if (typeof requestAnimationFrame === "function") {
          requestAnimationFrame(stepFade);
        } else {
          setTimeout(() => stepFade(), 0);
        }

        activeFrameLayer = newLayer;
        lastFrameIndex = frameEntry.index;
        if (timeEl) {
          timeEl.style.display = "block";
          timeEl.textContent = frameEntry.display || formatDisplayTime(frameEntry.iso);
        }
        console.debug("Cesium globe: applied frame imagery layer", {
          url: providerOptions.url,
          reason,
        });
      };

      const readyPromise = provider.readyPromise;
      if (readyPromise && typeof readyPromise.then === "function") {
        readyPromise
          .then(finalizeLayer)
          .catch((error) => {
            console.warn("Cesium globe: frame imagery failed to load", providerOptions.url, error);
            if (pendingFrameLayer === newLayer) {
              pendingFrameLayer = null;
            }
            viewer.imageryLayers.remove(newLayer, true);
          });
      } else {
        finalizeLayer();
      }
    };

    const pickFrameForJulian = (julian) => {
      for (const entry of frameEntries) {
        if (
          Cesium.JulianDate.lessThanOrEquals(entry.julian, julian) &&
          Cesium.JulianDate.lessThan(julian, entry.stop)
        ) {
          return entry;
        }
      }
      return frameEntries[frameEntries.length - 1];
    };

    ensureLayerForFrame(frameEntries[0], "initial");

    viewer.clock.onTick.addEventListener((clock) => {
      const frameEntry = pickFrameForJulian(clock.currentTime);
      if (!frameEntry) {
        return;
      }
      ensureLayerForFrame(frameEntry, "clock");
    });
  } else if (config.texture) {
    baseProvider = new Cesium.SingleTileImageryProvider({
      url: config.texture,
      rectangle: Cesium.Rectangle.MAX_VALUE,
    });
  } else if (tileUrl) {
    try {
      const normalizedTileUrl = tileUrl.replace(/[/]+$/, "");
      const isImageServer = normalizedTileUrl.toLowerCase().includes("imageserver");

      const prepareTemplateUrl = (timeValue) => {
        let url = tileUrl;
        if (tileTimeKey && typeof timeValue === "string" && timeValue.length) {
          const pattern = new RegExp(`\\{${tileTimeKey}\\}`, "gi");
          url = url.replace(pattern, encodeURIComponent(timeValue));
        }
        if (tileParams) {
          for (const [rawKey, rawValue] of Object.entries(tileParams)) {
            if (rawValue == null) {
              continue;
            }
            const key = String(rawKey);
            const encodedValue =
              typeof rawValue === "string" || typeof rawValue === "number"
                ? encodeURIComponent(String(rawValue))
                : null;
            if (!encodedValue) {
              continue;
            }
            const pattern = new RegExp(`\\{${key}\\}`, "gi");
            url = url.replace(pattern, encodedValue);
          }
        }
        if (tileToken) {
          if (url.includes("{token}")) {
            url = url.replace(new RegExp("\\{token\\}", "gi"), encodeURIComponent(tileToken));
          } else {
            url = `${url}${url.includes("?") ? "&" : "?"}token=${encodeURIComponent(tileToken)}`;
          }
        }
        url = url
          .replace(/\\{TileMatrix\\}/gi, "{z}")
          .replace(/\\{TileRow\\}/gi, "{y}")
          .replace(/\\{TileCol\\}/gi, "{x}")
          .replace(/\\{level\\}/gi, "{z}")
          .replace(/\\{row\\}/gi, "{y}")
          .replace(/\\{col\\}/gi, "{x}");
        return url;
      };

      let tilingScheme =
        tileSchemeMode === "geographic" && Cesium.GeographicTilingScheme
          ? new Cesium.GeographicTilingScheme()
          : tileSchemeMode === "webmercator" && Cesium.WebMercatorTilingScheme
            ? new Cesium.WebMercatorTilingScheme()
            : undefined;
      if (!tilingScheme && Cesium.WebMercatorTilingScheme) {
        tilingScheme = new Cesium.WebMercatorTilingScheme();
      }

      if (hasDynamicTime) {
        dynamicLayerActive = true;

        const timeEntries = tileTimeValues.map((value) => {
          const isoValue =
            typeof value === "string" && value.includes("T")
              ? value
              : `${value}T00:00:00Z`;
          const julian = Cesium.JulianDate.fromIso8601(isoValue);
          return {
            value: String(value),
            iso: isoValue,
            julian,
          };
        });
        timeEntries.sort((a, b) => Cesium.JulianDate.compare(a.julian, b.julian));
        timeEntries.forEach((entry, index) => {
          if (index < timeEntries.length - 1) {
            entry.stop = Cesium.JulianDate.clone(timeEntries[index + 1].julian);
          } else {
            entry.stop = Cesium.JulianDate.addDays(entry.julian, 1, new Cesium.JulianDate());
          }
        });

        const startTime = Cesium.JulianDate.clone(timeEntries[0].julian);
        const stopTime = Cesium.JulianDate.clone(timeEntries[timeEntries.length - 1].stop);

        viewer.clock.startTime = Cesium.JulianDate.clone(startTime);
        viewer.clock.stopTime = Cesium.JulianDate.clone(stopTime);
        viewer.clock.currentTime = Cesium.JulianDate.clone(startTime);
        viewer.clock.clockRange = Cesium.ClockRange.CLAMPED;
        viewer.clock.clockStep = Cesium.ClockStep.SYSTEM_CLOCK_MULTIPLIER;
        viewer.clock.multiplier = tileTimeMultiplier;
        viewer.clock.shouldAnimate = true;
        if (viewer.timeline) {
          viewer.timeline.zoomTo(viewer.clock.startTime, viewer.clock.stopTime);
        }

        let activeLayer = null;
        let lastTimeValue = null;


        const ensureLayerForTime = (timeValue, reason) => {
          if (!timeValue) {
            return;
          }
          if (timeValue === lastTimeValue && activeLayer) {
            return;
          }
          const preparedUrl = prepareTemplateUrl(timeValue);
          const providerOptions = {
            url: preparedUrl,
            tilingScheme,
          };
          if (creditObject) {
            providerOptions.credit = creditObject;
          }
          if (tileMinLevel != null) {
            providerOptions.minimumLevel = tileMinLevel;
          }
          if (tileMaxLevel != null) {
            providerOptions.maximumLevel = tileMaxLevel;
          }
          console.debug("Cesium globe: configuring UrlTemplateImageryProvider", {
            url: providerOptions.url,
            minimumLevel: providerOptions.minimumLevel ?? null,
            maximumLevel: providerOptions.maximumLevel ?? null,
            tilingScheme: tilingScheme ? tilingScheme.constructor?.name : null,
            reason,
          });
          const provider = new Cesium.UrlTemplateImageryProvider(providerOptions);
          let insertIndex = undefined;
          if (activeLayer) {
            const existingIndex = viewer.imageryLayers.indexOf(activeLayer);
            if (existingIndex >= 0) {
              insertIndex = existingIndex;
            }
          }
          const newLayer = viewer.imageryLayers.addImageryProvider(provider, insertIndex);
          if (activeLayer) {
            viewer.imageryLayers.remove(activeLayer, true);
          }
          activeLayer = newLayer;
          lastTimeValue = timeValue;
          if (timeEl) {
            timeEl.style.display = "block";
          timeEl.textContent = formatDisplayTime(timeValue);
          }
          console.debug("Cesium globe: created UrlTemplateImageryProvider", {
            url: providerOptions.url,
            minimumLevel: providerOptions.minimumLevel ?? null,
            maximumLevel: providerOptions.maximumLevel ?? null,
            tilingScheme: tilingScheme ? tilingScheme.constructor?.name : null,
            reason,
          });
        };

        const pickTimeForJulian = (julian) => {
          for (const entry of timeEntries) {
            if (
              Cesium.JulianDate.lessThanOrEquals(entry.julian, julian) &&
              Cesium.JulianDate.lessThan(julian, entry.stop)
            ) {
              return entry.value;
            }
          }
          let closest = timeEntries[0];
          let bestDiff = Math.abs(
            Cesium.JulianDate.secondsDifference(julian, closest.julian),
          );
          for (const entry of timeEntries.slice(1)) {
            const diff = Math.abs(
              Cesium.JulianDate.secondsDifference(julian, entry.julian),
            );
            if (diff < bestDiff) {
              bestDiff = diff;
              closest = entry;
            }
          }
          return closest.value;
        };

        ensureLayerForTime(timeEntries[0].value, "initial");
        viewer.clock.onTick.addEventListener((clock) => {
          const desiredValue = pickTimeForJulian(clock.currentTime);
          ensureLayerForTime(desiredValue, "clock");
        });
      } else {
        if (timeEl) {
          timeEl.style.display = "none";
        }
        let providerLoaded = false;
        const inferredMinLevel =
          tileMinLevel != null
            ? tileMinLevel
            : isImageServer
              ? 2
              : undefined;
        if (
          Cesium.ArcGisMapServerImageryProvider &&
          tileType !== "template" &&
          !isImageServer
        ) {
          try {
            const arcgisOptions = {
              enablePickFeatures: false,
            };
            if (creditObject) {
              arcgisOptions.credit = creditObject;
            }
            if (inferredMinLevel != null) {
              arcgisOptions.minimumLevel = inferredMinLevel;
            }
            if (tileMaxLevel != null) {
              arcgisOptions.maximumLevel = tileMaxLevel;
            }
            if (tileToken) {
              arcgisOptions.token = tileToken;
            }
            if (typeof Cesium.ArcGisMapServerImageryProvider.fromUrl === "function") {
              baseProvider = await Cesium.ArcGisMapServerImageryProvider.fromUrl(
                tileUrl,
                arcgisOptions,
              );
            } else {
              arcgisOptions.url = tileUrl;
              baseProvider = new Cesium.ArcGisMapServerImageryProvider(arcgisOptions);
            }
            providerLoaded = true;
          } catch (arcgisError) {
            console.warn(
              "Cesium globe: ArcGIS imagery provider failed, attempting template fallback",
              arcgisError,
            );
            baseProvider = null;
          }
        }

        if (
          !baseProvider &&
          Cesium.UrlTemplateImageryProvider &&
          (tileType === "template" || (tileType === "arcgis" && isImageServer))
        ) {
          if (isImageServer) {
            console.warn(
              "Cesium globe: skipping URL template fallback for ImageServer endpoint (not tile cached)",
            );
          } else {
            const templateUrl = prepareTemplateUrl(null);
            const templateOptions = {
              url: templateUrl,
              tilingScheme,
            };
            if (creditObject) {
              templateOptions.credit = creditObject;
            }
            if (inferredMinLevel != null) {
              templateOptions.minimumLevel = inferredMinLevel;
            }
            if (tileMaxLevel != null) {
              templateOptions.maximumLevel = tileMaxLevel;
            }
            console.debug("Cesium globe: configuring UrlTemplateImageryProvider", {
              url: templateOptions.url,
              minimumLevel: templateOptions.minimumLevel ?? null,
              maximumLevel: templateOptions.maximumLevel ?? null,
              tilingScheme: tilingScheme ? tilingScheme.constructor?.name : null,
            });
            baseProvider = new Cesium.UrlTemplateImageryProvider(templateOptions);
            console.debug("Cesium globe: created UrlTemplateImageryProvider", {
              url: templateOptions.url,
              minimumLevel: templateOptions.minimumLevel ?? null,
              maximumLevel: templateOptions.maximumLevel ?? null,
              tilingScheme: tilingScheme ? tilingScheme.constructor?.name : null,
            });
            providerLoaded = true;
          }
        }

        if (!providerLoaded) {
          console.warn(
            "Cesium globe: ArcGIS tile support unavailable in this Cesium build",
          );
        }
      }
    } catch (error) {
      console.warn("Cesium globe: failed to initialize custom tile imagery", error);
      baseProvider = null;
    }
  } else if (timeEl) {
    timeEl.style.display = "none";
  }
  if (!baseProvider && !dynamicLayerActive) {
    if (Cesium.createWorldImageryAsync) {
      try {
        baseProvider = await Cesium.createWorldImageryAsync();
      } catch (error) {
        console.warn("Cesium globe: failed to load world imagery", error);
      }
    }
    if (!baseProvider && Cesium.createWorldImagery) {
      try {
        baseProvider = Cesium.createWorldImagery();
      } catch (error) {
        console.warn("Cesium globe: createWorldImagery fallback failed", error);
      }
    }
    if (!baseProvider && Cesium.IonImageryProvider) {
      try {
        baseProvider = new Cesium.IonImageryProvider({ assetId: 2 });
      } catch (error) {
        console.warn("Cesium globe: Ion imagery provider failed", error);
      }
    }
    if (!baseProvider && Cesium.TileCoordinatesImageryProvider) {
      baseProvider = new Cesium.TileCoordinatesImageryProvider();
    }
  }
  if (baseProvider) {
    viewer.imageryLayers.addImageryProvider(baseProvider);
  }
  const autoRotate = Boolean(config.auto_rotate);
  const autoRotateSpeed =
    Number.isFinite(Number(config.auto_rotate_speed)) && Number(config.auto_rotate_speed) !== 0
      ? Number(config.auto_rotate_speed)
      : 0.5; // degrees per second
  if (autoRotate) {
    let spinEnabled = true;
    const spinRate = Cesium.Math.toRadians(autoRotateSpeed); // degrees per second -> radians per second
    let lastTimestamp = undefined;
    const onPostRender = () => {
      if (!spinEnabled) {
        return;
      }
      const now = performance.now();
      if (lastTimestamp === undefined) {
        lastTimestamp = now;
        return;
      }
      const deltaSeconds = Math.max((now - lastTimestamp) / 1000, 0.016);
      lastTimestamp = now;
      viewer.scene.camera.rotate(Cesium.Cartesian3.UNIT_Z, spinRate * deltaSeconds);
    };
    const stopSpin = () => {
      spinEnabled = false;
      viewer.scene.postRender.removeEventListener(onPostRender);
      viewer.scene.canvas.removeEventListener("mousedown", stopSpin);
      viewer.scene.canvas.removeEventListener("touchstart", stopSpin);
    };
    viewer.scene.postRender.addEventListener(onPostRender);
    viewer.scene.canvas.addEventListener("mousedown", stopSpin);
    viewer.scene.canvas.addEventListener("touchstart", stopSpin);
  }


  const canvas = viewer.scene.canvas;
  if (config.probe_enabled) {
    canvas.style.cursor = "crosshair";
  }

  function sanitizeHeight(value) {
    if (!Number.isFinite(value)) {
      return null;
    }
    if (value < -11000 || value > 9000) {
      return null;
    }
    return value;
  }

  function labelFromPath(value) {
    if (!value || typeof value !== "string") {
      return "—";
    }
    const parts = value.split("/");
    return parts[parts.length - 1] || value;
  }

  if (gradientEl) gradientEl.textContent = labelFromPath(config.probe_gradient);
  if (lutEl) lutEl.textContent = labelFromPath(config.probe_lut);

  const titleText =
    typeof config.title === "string" ? config.title.trim() : "";
  if (titleEl) {
    if (titleText) {
      titleEl.textContent = titleText;
      titleEl.style.display = "block";
    } else {
      titleEl.style.display = "none";
    }
  }

  const descriptionText =
    typeof config.description === "string" ? config.description.trim() : "";
  if (descriptionEl) {
    if (descriptionText) {
      descriptionEl.textContent = descriptionText;
      descriptionEl.style.display = "block";
    } else {
      descriptionEl.style.display = "none";
    }
  }

  const debugOverlayRaw = config.debug_overlay;
  const debugOverlay =
    debugOverlayRaw === true ||
    debugOverlayRaw === "true" ||
    debugOverlayRaw === "True" ||
    debugOverlayRaw === 1 ||
    debugOverlayRaw === "1";
  if (metaEl) {
    metaEl.style.display = debugOverlay ? "block" : "none";
  }

  if (legendEl) {
    const legendSrc = config.legend || null;
    if (legendSrc) {
      legendEl.innerHTML = "";
      const img = document.createElement("img");
      img.src = legendSrc;
      img.loading = "lazy";
      img.alt = "Legend";
      legendEl.appendChild(img);
      legendEl.style.display = "block";
    } else {
      legendEl.style.display = "none";
    }
  }

  if (!config.probe_enabled && overlay) {
    overlay.style.opacity = "0.65";
  }
  if (!config.probe_enabled && probeContainer) {
    probeContainer.style.display = "none";
  }

  async function fetchText(url) {
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`Fetch failed: ${response.status}`);
    }
    return response.text();
  }

  async function loadJson(url) {
    try {
      const text = await fetchText(url);
      return JSON.parse(text);
    } catch (error) {
      console.warn("Cesium probe: failed to load JSON", url, error);
      return null;
    }
  }

  function parseCsvDataset(text) {
    const lines = text
      .split(/\\r?\\n/)
      .map((line) => line.trim())
      .filter(Boolean);
    if (!lines.length) {
      return null;
    }
    const headers = lines[0]
      .split(",")
      .map((h) => h.trim().toLowerCase());
    const latIdx = headers.findIndex((h) => h === "lat" || h === "latitude");
    const lonIdx = headers.findIndex((h) => h === "lon" || h === "lng" || h === "long" || h === "longitude");
    const valueIdx = headers.findIndex((h) => h === "value" || h === "val" || h === "data");
    const unitsIdx = headers.findIndex((h) => h === "units" || h === "unit");
    if (latIdx === -1 || lonIdx === -1 || valueIdx === -1) {
      return null;
    }
    const points = [];
    for (let i = 1; i < lines.length; i += 1) {
      const parts = lines[i].split(",").map((p) => p.trim());
      if (parts.length < headers.length) {
        continue;
      }
      const lat = Number(parts[latIdx]);
      const lon = Number(parts[lonIdx]);
      const value = Number(parts[valueIdx]);
      if (!Number.isFinite(lat) || !Number.isFinite(lon) || !Number.isFinite(value)) {
        continue;
      }
      const entry = { lat, lon, value };
      if (unitsIdx !== -1 && parts[unitsIdx]) {
        entry.units = parts[unitsIdx];
      }
      points.push(entry);
    }
    return points.length ? { points } : null;
  }

  function normalizeProbeArray(raw) {
    if (!Array.isArray(raw)) {
      return null;
    }
    const points = [];
    for (const entry of raw) {
      if (typeof entry !== "object" || entry == null) {
        continue;
      }
      const lat = Number(entry.lat ?? entry.latitude);
      const lon = Number(entry.lon ?? entry.lng ?? entry.long ?? entry.longitude);
      const value = Number(entry.value ?? entry.val ?? entry.data);
      if (!Number.isFinite(lat) || !Number.isFinite(lon) || !Number.isFinite(value)) {
        continue;
      }
      points.push({
        lat,
        lon,
        value,
        units: entry.units ?? entry.unit ?? null,
      });
    }
    return points.length ? { points } : null;
  }

  async function loadProbeDataset(url) {
    try {
      const text = await fetchText(url);
      try {
        const parsed = JSON.parse(text);
        const normalized = normalizeProbeArray(parsed);
        if (normalized) {
          return normalized;
        }
      } catch (jsonError) {
        // fall through to CSV parser
      }
      const csv = parseCsvDataset(text);
      if (csv) {
        return csv;
      }
      console.warn("Cesium probe: unsupported dataset format", url);
    } catch (error) {
      console.warn("Cesium probe: failed to load dataset", url, error);
    }
    return null;
  }

  function nearestProbe(lat, lon, dataset) {
    if (!dataset || !dataset.points || !dataset.points.length) {
      return null;
    }
    const latRad = Cesium.Math.toRadians(lat);
    const lonRad = Cesium.Math.toRadians(lon);
    let best = null;
    let bestScore = Infinity;
    for (const point of dataset.points) {
      const pLat = Cesium.Math.toRadians(point.lat);
      const pLon = Cesium.Math.toRadians(point.lon);
      const dLat = latRad - pLat;
      const dLon = lonRad - pLon;
      const sinLat = Math.sin(dLat / 2);
      const sinLon = Math.sin(dLon / 2);
      const a =
        sinLat * sinLat +
        Math.cos(latRad) * Math.cos(pLat) * sinLon * sinLon;
      const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
      if (c < bestScore) {
        bestScore = c;
        best = point;
      }
    }
    return best;
  }

  function formatValue(value) {
    if (!Number.isFinite(value)) {
      return "—";
    }
    if (Math.abs(value) >= 1000 || Math.abs(value) < 0.01) {
      return value.toExponential(2);
    }
    return value.toFixed(2);
  }

  const probeDataset = config.probe_data
    ? await loadProbeDataset(config.probe_data)
    : null;

  const handler = new Cesium.ScreenSpaceEventHandler(canvas);
  const ellipsoid = viewer.scene.globe.ellipsoid;

  function updateProbeDisplay(payload) {
    if (!latEl || !lonEl) {
      return;
    }
    if (!payload) {
      latEl.textContent = "—";
      lonEl.textContent = "—";
      if (heightEl) heightEl.textContent = "—";
      if (valueEl) valueEl.textContent = "—";
      if (unitsEl) unitsEl.textContent = "—";
      return;
    }
    latEl.textContent = `${payload.lat.toFixed(2)}°`;
    lonEl.textContent = `${payload.lon.toFixed(2)}°`;
    if (heightEl) {
      const cleanHeight = sanitizeHeight(payload.height);
      if (cleanHeight == null) {
        heightEl.textContent = "—";
      } else {
        heightEl.textContent = `${cleanHeight.toFixed(0)} m`;
      }
    }
    if (valueEl) {
      valueEl.textContent =
        payload.dataValue != null ? formatValue(payload.dataValue) : "—";
    }
    if (unitsEl) {
      unitsEl.textContent = payload.dataUnits ?? "—";
    }
  }

  function clearProbe() {
    updateProbeDisplay(null);
  }

  let probeHeightRequestId = 0;

  if (config.probe_enabled) {
    handler.setInputAction((movement) => {
      const pickRay = viewer.camera.getPickRay(movement.endPosition);
      let cartesian = pickRay
        ? viewer.scene.globe.pick(pickRay, viewer.scene)
        : undefined;
      if (!Cesium.defined(cartesian)) {
        cartesian = viewer.camera.pickEllipsoid(
          movement.endPosition,
          ellipsoid,
        );
      }
      if (!Cesium.defined(cartesian)) {
        clearProbe();
        return;
      }
      const cartographic = ellipsoid.cartesianToCartographic(cartesian);
      const lat = Cesium.Math.toDegrees(cartographic.latitude);
      let lon = Cesium.Math.toDegrees(cartographic.longitude);
      if (lon > 180) lon -= 360;
      if (lon < -180) lon += 360;
      let heightMeters = null;
      if (probeHeightEnabled) {
        heightMeters = sanitizeHeight(cartographic.height);
        if (heightMeters == null) {
          heightMeters = sanitizeHeight(viewer.scene.globe.getHeight(cartographic));
        }
        if (heightMeters == null) {
          heightMeters = sanitizeHeight(cartographic.height);
        }
      }

      let dataValue = null;
      let dataUnits = null;
      if (probeDataset) {
        const nearest = nearestProbe(lat, lon, probeDataset);
        if (nearest) {
          dataValue = nearest.value;
          dataUnits = nearest.units ?? config.probe_units ?? null;
        }
      }

      const payload = {
        lat,
        lon,
        height: heightMeters,
        dataValue,
        dataUnits,
      };
      updateProbeDisplay(payload);

      if (
        probeHeightEnabled &&
        wantsTerrain &&
        terrainProvider &&
        Cesium.sampleTerrainMostDetailed &&
        Cesium.Cartographic
      ) {
        const requestId = ++probeHeightRequestId;
        const target = Cesium.Cartographic.clone(cartographic);
        Cesium.sampleTerrainMostDetailed(terrainProvider, [target])
          .then((result) => {
            if (requestId !== probeHeightRequestId) {
              return;
            }
            const refined = (result && result[0]) || target;
            if (refined) {
              const clean = sanitizeHeight(refined.height);
              if (clean != null) {
                payload.height = clean;
                updateProbeDisplay(payload);
              }
            }
          })
          .catch((error) => {
            if (requestId === probeHeightRequestId) {
              console.warn("Cesium probe: terrain refinement failed", error);
            }
          });
      }
    }, Cesium.ScreenSpaceEventType.MOUSE_MOVE);

    canvas.addEventListener("mouseleave", clearProbe);
    clearProbe();
  }

  window.addEventListener("resize", () => {
    const w = config.width || window.innerWidth;
    const h = config.height || window.innerHeight;
    container.style.width = `${w}px`;
    container.style.height = `${h}px`;
    viewer.resize();
  });
})();

"""
            ).strip()
            + "\n"
        )
