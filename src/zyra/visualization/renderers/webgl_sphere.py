# SPDX-License-Identifier: Apache-2.0
"""WebGL/Three.js based globe renderer."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from textwrap import dedent, indent

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


def _elapsed_seconds(start, timestamp: str) -> float:
    try:
        end = parse_datetime(timestamp)
    except Exception:
        return 0.0
    delta = end - start
    return max(delta.total_seconds(), 0.0)


@register
class WebGLSphereRenderer(InteractiveRenderer):
    slug = "webgl-sphere"
    description = "Three.js based sphere renderer that emits a standalone bundle."

    def __init__(self, **options: object) -> None:
        super().__init__(**options)
        self._video_entries: list[dict[str, object]] | None = None

    def build(self, *, output_dir: Path) -> InteractiveBundle:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        assets_dir = output_dir / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)

        index_html = output_dir / "index.html"
        script_path = assets_dir / "sphere.js"
        config_path = assets_dir / "config.json"

        asset_overrides, asset_files = self._stage_assets(assets_dir)

        config = self._sanitized_config(overrides=asset_overrides)
        config_json = json.dumps(config, indent=2)
        config_path.write_text(config_json + "\n", encoding="utf-8")

        index_html.write_text(self._render_index_html(config), encoding="utf-8")
        script_path.write_text(self._render_script(), encoding="utf-8")

        return InteractiveBundle(
            output_dir=output_dir,
            index_html=index_html,
            assets=(script_path, config_path, *asset_files),
        )

    def _stage_assets(
        self, assets_dir: Path
    ) -> tuple[dict[str, object], tuple[Path, ...]]:
        """Copy optional assets (textures, legends) into bundle."""

        staged: list[Path] = []
        overrides: dict[str, object] = {}

        textures_dir = assets_dir / "textures"
        data_dir = assets_dir / "data"
        legends_dir = assets_dir / "legends"
        texture = self._options.get("texture")
        if texture:
            if _is_remote_ref(texture):
                overrides["texture"] = _normalize_remote_ref(str(texture))
            else:
                staged.append(
                    self._copy_asset(Path(texture), textures_dir, overrides, "texture")
                )

        video_meta = self._maybe_generate_video_frames(assets_dir)

        frame_entries = self._collect_frames()
        if frame_entries:
            frames_dir = textures_dir
            frames_dir.mkdir(parents=True, exist_ok=True)
            staged_paths = []
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

        if video_meta:
            overrides.update(video_meta)

        gradients_dir = assets_dir / "gradients"
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

        legend = self._options.get("legend")
        if legend:
            if _is_remote_ref(legend):
                overrides["legend"] = _normalize_remote_ref(str(legend))
            else:
                staged.append(
                    self._copy_asset(Path(legend), legends_dir, overrides, "legend")
                )

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
            except Exception as exc:  # pragma: no cover - depends on filesystem
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
                    except Exception as exc:  # pragma: no cover - defensive
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
            except (
                TypeError,
                ValueError,
            ) as exc:  # pragma: no cover - CLI already types
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
            entry_metadata["elapsed_seconds"] = _elapsed_seconds(
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
        frame_date_format = self._options.get("frame_date_format") or self._options.get(
            "date_format"
        )
        time_key = self._options.get("time_key")
        time_format = self._options.get("time_format")

        parse_formats: list[str] = []
        if frame_date_format:
            parse_formats.append(str(frame_date_format))
        if time_format and time_format not in parse_formats:
            parse_formats.append(str(time_format))

        try:
            filename_date_manager: DateManager | None = (
                DateManager([frame_date_format])
                if frame_date_format
                else DateManager([])
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

    def _copy_asset(
        self,
        source: Path,
        target_dir: Path,
        overrides: dict[str, object],
        key: str,
    ) -> Path:
        source = source.expanduser()
        if not source.is_file():
            msg = f"{key.capitalize()} file not found: {source}"
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
        """Return config suitable for embedding (no sensitive values)."""

        secrets = {
            "credentials",
            "auth",
            "credential_file",
            "texture",
            "texture_pattern",
            "frame_list",
            "frame_cache",
            "probe_gradient",
            "probe_lut",
            "probe_data",
            "probe_var",
            "legend",
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
        filtered.setdefault("show_controls", True)
        if overrides:
            filtered.update(overrides)
        return filtered

    def _render_index_html(self, config: dict[str, object]) -> str:
        """Return the HTML entry point for the bundle."""

        probe_section = ""
        if config.get("probe_enabled", True):
            probe_section = indent(
                dedent(
                    """
                    <div id="zyra-probe">
                      <div class="probe-header">Probe</div>
                      <div class="probe-line"><span class="probe-label">Latitude</span><span data-probe-lat>—</span></div>
                      <div class="probe-line"><span class="probe-label">Longitude</span><span data-probe-lon>—</span></div>
                      <div class="probe-line"><span class="probe-label">Frame</span><span data-probe-frame>—</span></div>
                      <div class="probe-line"><span class="probe-label">Color</span><span class="probe-swatch" data-probe-swatch></span><code data-probe-hex>—</code></div>
                      <div class="probe-line"><span class="probe-label">Value</span><span data-probe-value>—</span></div>
                      <div class="probe-line"><span class="probe-label">Units</span><span data-probe-units>—</span></div>
                      <div class="probe-line"><span class="probe-label">Gradient</span><span data-probe-gradient>—</span></div>
                      <div class="probe-line"><span class="probe-label">LUT</span><span data-probe-lut>—</span></div>
                    </div>
                    """
                ).strip(),
                "                  ",
            )

        config_json = json.dumps(config, indent=2)

        meta_section = ""
        if config.get("debug_overlay"):
            meta_section = indent(
                dedent(
                    f"""
                    <div class="overlay-meta">
                      <strong>Zyra WebGL Sphere (beta)</strong>
                      <p>Renderer target: <code>{self.slug}</code></p>
                    </div>
                    """
                ).strip(),
                "                  ",
            )

        title_section = ""
        if config.get("title"):
            title_section = indent(
                dedent(
                    f"""
                    <div class="overlay-title">{config["title"]}</div>
                    """
                ).strip(),
                "                  ",
            )

        description_section = ""
        if config.get("description"):
            description_section = indent(
                dedent(
                    f"""
                    <div class="overlay-description">{config["description"]}</div>
                    """
                ).strip(),
                "                  ",
            )

        legend_section = ""
        if config.get("legend"):
            legend_section = indent(
                dedent(
                    f"""
                    <div class="overlay-legend"><img src="{config["legend"]}" alt="Legend" /></div>
                    """
                ).strip(),
                "                  ",
            )

        frame_info_section = indent(
            dedent(
                """
                <div class="overlay-frame-info" data-frame-info>
                  <div class="frame-line">
                    <span class="frame-label">Timestamp</span><span data-frame-timestamp>—</span>
                  </div>
                </div>
                """
            ).strip(),
            "                  ",
        )

        controls_section = indent(
            dedent(
                """
                <div class="overlay-controls" data-controls>
                  <button type="button" data-controls-prev aria-label="Previous frame">Prev</button>
                  <button type="button" data-controls-play aria-label="Play or pause">Pause</button>
                  <button type="button" data-controls-next aria-label="Next frame">Next</button>
                </div>
                """
            ).strip(),
            "                  ",
        )

        overlay_sections = "".join(
            section
            for section in (
                title_section,
                description_section,
                legend_section,
                frame_info_section,
                controls_section,
                meta_section,
                probe_section,
            )
            if section
        )

        if overlay_sections:
            overlay_block = dedent(
                f"""
                <div id="zyra-overlay" data-probe-container>
{overlay_sections}
                </div>
                """
            ).strip("\n")
        else:
            overlay_block = ""

        return (
            dedent(
                f"""
            <!DOCTYPE html>
            <html lang=\"en\">
              <head>
                <meta charset=\"utf-8\" />
                <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
                <title>Zyra WebGL Globe</title>
                <style>
                  body, html {{ margin: 0; padding: 0; background: #0f1114; color: #f5f7fa; font-family: system-ui, sans-serif; }}
                  #zyra-globe {{ width: 100vw; height: 100vh; display: block; }}
                  #zyra-overlay {{ position: absolute; top: 16px; left: 16px; background: rgba(0, 0, 0, 0.55); padding: 12px 16px; border-radius: 8px; max-width: 320px; }}
                  #zyra-overlay .overlay-meta {{ margin-bottom: 8px; }}
                  #zyra-overlay .overlay-title {{ font-weight: 600; font-size: 1rem; margin-bottom: 4px; }}
                  #zyra-overlay .overlay-description {{ font-size: 0.85rem; margin-bottom: 8px; color: rgba(245, 247, 250, 0.85); }}
                  #zyra-overlay .overlay-legend img {{ max-width: 240px; height: auto; display: block; margin: 8px 0; border: 1px solid rgba(245, 247, 250, 0.35); border-radius: 4px; }}
                  #zyra-overlay code {{ font-size: 0.85rem; }}
                  #zyra-overlay .overlay-frame-info {{ margin-top: 8px; font-size: 0.85rem; display: flex; flex-direction: column; gap: 4px; }}
                  #zyra-overlay .overlay-frame-info .frame-line {{ display: flex; align-items: center; gap: 6px; }}
                  #zyra-overlay .overlay-frame-info .frame-label {{ min-width: 74px; color: rgba(245, 247, 250, 0.7); }}
                  #zyra-overlay .overlay-controls {{ margin-top: 12px; display: flex; align-items: center; gap: 8px; }}
                  #zyra-overlay .overlay-controls button {{ background: rgba(245, 247, 250, 0.12); border: 1px solid rgba(245, 247, 250, 0.25); color: #f5f7fa; padding: 4px 10px; border-radius: 4px; font-size: 0.85rem; cursor: pointer; }}
                  #zyra-overlay .overlay-controls button:hover {{ background: rgba(245, 247, 250, 0.2); }}
                  #zyra-overlay .overlay-controls button:focus {{ outline: 2px solid rgba(245, 247, 250, 0.45); outline-offset: 1px; }}
                  #zyra-probe {{ margin-top: 10px; font-size: 0.85rem; line-height: 1.35; }}
                  #zyra-probe .probe-header {{ font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 4px; font-size: 0.8rem; }}
                  #zyra-probe .probe-line {{ display: flex; align-items: center; gap: 6px; white-space: nowrap; }}
                  #zyra-probe .probe-label {{ min-width: 68px; color: rgba(245, 247, 250, 0.75); }}
                  #zyra-probe .probe-swatch {{ width: 14px; height: 14px; border: 1px solid rgba(245, 247, 250, 0.65); border-radius: 2px; background: transparent; display: inline-block; box-sizing: border-box; }}
                </style>
              </head>
              <body>
                <canvas id=\"zyra-globe\"></canvas>
{overlay_block}
                <script>
                  window.ZYRA_GLOBE_CONFIG = {config_json};
                </script>
                <script type=\"module\" src=\"assets/sphere.js\"></script>
              </body>
            </html>
            """
            ).strip()
            + "\n"
        )

    def _render_script(self) -> str:
        """Return the JavaScript module that boots the globe."""

        return (
            dedent(
                """
import * as THREE from "https://cdn.jsdelivr.net/npm/three@0.161.0/build/three.module.js";

(async function bootstrap() {
  const config = window.ZYRA_GLOBE_CONFIG || {};
  const canvas = document.getElementById("zyra-globe");
  if (!canvas) {
    console.warn("Zyra globe canvas element not found");
    return;
  }
  canvas.style.touchAction = "none";

  if (config.probe_enabled) {
    canvas.style.cursor = "crosshair";
  } else {
    canvas.style.cursor = "grab";
  }

  const probeContainer = document.getElementById("zyra-probe");
  const probeLatEl = document.querySelector("[data-probe-lat]");
  const probeLonEl = document.querySelector("[data-probe-lon]");
  const probeFrameEl = document.querySelector("[data-probe-frame]");
  const probeHexEl = document.querySelector("[data-probe-hex]");
  const probeSwatchEl = document.querySelector("[data-probe-swatch]");
  const probeGradientEl = document.querySelector("[data-probe-gradient]");
  const probeLutEl = document.querySelector("[data-probe-lut]");
  const probeValueEl = document.querySelector("[data-probe-value]");
  const probeUnitsEl = document.querySelector("[data-probe-units]");
  const controlsContainer = document.querySelector("[data-controls]");
  const playButton = document.querySelector("[data-controls-play]");
  const prevButton = document.querySelector("[data-controls-prev]");
  const nextButton = document.querySelector("[data-controls-next]");
  const frameTimestampEl = document.querySelector("[data-frame-timestamp]");
  const frameInfoContainer = document.querySelector("[data-frame-info]");

  if (!config.probe_enabled && probeContainer) {
    probeContainer.style.display = "none";
  }

  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  renderer.setPixelRatio(window.devicePixelRatio || 1);

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x050608);

  const camera = new THREE.PerspectiveCamera(
    45,
    window.innerWidth / window.innerHeight,
    0.1,
    1000,
  );
  const frames = Array.isArray(config.frames) ? config.frames : null;
  const totalFrames = frames ? frames.length : 0;
  const showControls = config.show_controls !== false;
  const controlsEnabled = Boolean(showControls && totalFrames > 1);
  const useLighting = Boolean(config.lighting);
  const autoRotate = Boolean(config.auto_rotate);
  const rotationSpeed = Number(config.rotation_speed || 0.005);
  const zoomSpeed = Number(config.zoom_speed || 0.003);
  let cameraDistance = Number(config.camera_distance) || 3;
  const minCameraDistance = Number(config.min_distance || 1.5);
  const maxCameraDistance = Number(config.max_distance || 12);
  const rotationClamp = Math.PI / 2 - 0.01;
  const pointerState = new Map();
  let lastPinchDistance = null;
  let isPointerDragging = false;
  let isPlaying = Boolean(config.animate === "time" && totalFrames > 1);
  const lookTarget = new THREE.Vector3(0, 0, 0);

  if (controlsContainer) {
    controlsContainer.style.display = controlsEnabled ? "flex" : "none";
  }
  if (frameInfoContainer && !totalFrames) {
    frameInfoContainer.style.display = "none";
  }

  function applyCameraDistance() {
    cameraDistance = Math.min(
      maxCameraDistance,
      Math.max(minCameraDistance, cameraDistance),
    );
    camera.position.set(0, 0, cameraDistance);
    camera.lookAt(lookTarget);
  }

  applyCameraDistance();

  const samplerCache = new Map();
  const textureCache = new Map();

  async function loadImageSampler(url) {
    try {
      const image = new Image();
      image.src = url;
      if (!url.startsWith("data:")) {
        image.crossOrigin = "anonymous";
      }
      await image.decode();
      const canvasSampler = document.createElement("canvas");
      canvasSampler.width = image.width;
      canvasSampler.height = image.height;
      const ctx = canvasSampler.getContext("2d");
      ctx.drawImage(image, 0, 0);
      const imageData = ctx.getImageData(0, 0, canvasSampler.width, canvasSampler.height);
      return {
        width: canvasSampler.width,
        height: canvasSampler.height,
        data: imageData.data,
      };
    } catch (error) {
      console.warn("Failed to load sampler image", url, error);
      return null;
    }
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
      console.warn("Failed to load JSON", url, error);
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
    const valueIdx = headers.findIndex((h) => h === "value" || h === "val" || h === "data" || h === "measurement");
    const labelIdx = headers.findIndex((h) =>
      h === "label" ||
      h === "popup" ||
      h === "name" ||
      h === "title" ||
      h === "text" ||
      h === "description"
    );
    const unitsIdx = headers.findIndex((h) => h === "units" || h === "unit");
    if (latIdx === -1 || lonIdx === -1 || (valueIdx === -1 && labelIdx === -1)) {
      return null;
    }
    const points = [];
    for (let i = 1; i < lines.length; i += 1) {
      const parts = lines[i].split(",").map((p) => p.trim());
      if (latIdx >= parts.length || lonIdx >= parts.length) {
        continue;
      }
      const lat = Number(parts[latIdx]);
      const lon = Number(parts[lonIdx]);
      if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
        continue;
      }
      const rawValue =
        valueIdx !== -1 && valueIdx < parts.length ? parts[valueIdx] : null;
      const rawLabel =
        labelIdx !== -1 && labelIdx < parts.length ? parts[labelIdx] : null;
      let value = null;
      let hasValue = false;
      if (rawValue != null && rawValue !== "") {
        const num = Number(rawValue);
        if (Number.isFinite(num)) {
          value = num;
          hasValue = true;
        } else {
          const str = String(rawValue).trim();
          if (str) {
            value = str;
            hasValue = true;
          }
        }
      }
      if (!hasValue && rawLabel) {
        const labelStr = String(rawLabel).trim();
        if (labelStr) {
          value = labelStr;
          hasValue = true;
        }
      }
      if (!hasValue) {
        continue;
      }
      const entry = { lat, lon, value };
      const label = rawLabel && String(rawLabel).trim() ? String(rawLabel).trim() : null;
      if (label && String(value) !== label) {
        entry.label = label;
      }
      if (unitsIdx !== -1 && unitsIdx < parts.length) {
        const units = String(parts[unitsIdx]).trim();
        if (units) {
          entry.units = units;
        }
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
      if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
        continue;
      }
      const rawValue =
        entry.value ??
        entry.val ??
        entry.data ??
        entry.measurement ??
        entry.popup ??
        entry.label ??
        entry.name ??
        entry.title ??
        entry.text ??
        null;
      const rawLabel =
        entry.label ?? entry.popup ?? entry.name ?? entry.title ?? entry.text ?? null;

      let value = null;
      let hasValue = false;
      if (rawValue !== undefined && rawValue !== null) {
        if (typeof rawValue === "number") {
          if (Number.isFinite(rawValue)) {
            value = rawValue;
            hasValue = true;
          }
        } else if (typeof rawValue === "boolean") {
          value = rawValue ? 1 : 0;
          hasValue = true;
        } else {
          const str = String(rawValue).trim();
          if (str) {
            const num = Number(str);
            if (Number.isFinite(num)) {
              value = num;
            } else {
              value = str;
            }
            hasValue = true;
          }
        }
      }
      if (!hasValue && rawLabel != null) {
        const labelStr = String(rawLabel).trim();
        if (labelStr) {
          value = labelStr;
          hasValue = true;
        }
      }
      if (!hasValue) {
        continue;
      }
      const point = { lat, lon, value };
      const label = rawLabel && String(rawLabel).trim() ? String(rawLabel).trim() : null;
      if (label && String(value) !== label) {
        point.label = label;
      }
      const units = entry.units ?? entry.unit ?? null;
      if (units != null) {
        const unitsStr = String(units).trim();
        if (unitsStr) {
          point.units = unitsStr;
        }
      }
      points.push(point);
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
      console.warn("Unsupported probe dataset format", url);
    } catch (error) {
      console.warn("Failed to load probe dataset", url, error);
    }
    return null;
  }

  function nearestProbe(lat, lon, dataset) {
    if (!dataset || !dataset.points || !dataset.points.length) {
      return null;
    }
    const latRad = THREE.MathUtils.degToRad(lat);
    const lonRad = THREE.MathUtils.degToRad(lon);
    let best = null;
    let bestScore = Infinity;
    for (const point of dataset.points) {
      const pLat = THREE.MathUtils.degToRad(point.lat);
      const pLon = THREE.MathUtils.degToRad(point.lon);
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

  const gradientSampler = config.probe_gradient
    ? await loadImageSampler(config.probe_gradient)
    : null;
  const lutTable = config.probe_lut ? await loadJson(config.probe_lut) : null;
  const probeDataset = config.probe_data
    ? await loadProbeDataset(config.probe_data)
    : null;

  const loader = new THREE.TextureLoader();

  const sphereGeometry = new THREE.SphereGeometry(1, 64, 64);
  const baseMaterialProps = {
    color: 0xffffff,
    wireframe: !config.texture && !(frames && frames.length),
  };
  const sphereMaterial = useLighting
    ? new THREE.MeshStandardMaterial(baseMaterialProps)
    : new THREE.MeshBasicMaterial(baseMaterialProps);

  let currentTextureUri = null;
  let currentFrameMeta = totalFrames ? frames[0] : null;
  let currentFrameIndex = 0;

  function prepareSampler(texture, uri) {
    if (!texture || !texture.image) {
      return;
    }
    const image = texture.image;
    const width = image.width;
    const height = image.height;
    if (!width || !height) {
      return;
    }
    const canvasSampler = document.createElement("canvas");
    canvasSampler.width = width;
    canvasSampler.height = height;
    const ctx = canvasSampler.getContext("2d");
    ctx.drawImage(image, 0, 0);
    const imageData = ctx.getImageData(0, 0, width, height);
    samplerCache.set(uri, {
      width,
      height,
      data: imageData.data,
    });
  }

  function ensureSampler(uri) {
    if (!uri || samplerCache.has(uri)) {
      return;
    }
    const cachedTexture = textureCache.get(uri);
    if (cachedTexture) {
      prepareSampler(cachedTexture, uri);
    }
  }

  function sampleTexture(uv) {
    const uri = currentTextureUri;
    if (!uri) {
      return null;
    }
    ensureSampler(uri);
    const sampler = samplerCache.get(uri);
    if (!sampler) {
      return null;
    }
    const { width, height, data } = sampler;
    const x = Math.min(width - 1, Math.max(0, Math.round(uv.x * (width - 1))));
    const y = Math.min(height - 1, Math.max(0, Math.round((1 - uv.y) * (height - 1))));
    const idx = (y * width + x) * 4;
    return {
      r: data[idx],
      g: data[idx + 1],
      b: data[idx + 2],
      a: data[idx + 3],
    };
  }

  function formatHex(color) {
    const toHex = (value) => value.toString(16).padStart(2, "0");
    return `#${toHex(color.r)}${toHex(color.g)}${toHex(color.b)}`.toUpperCase();
  }

  function formatValue(value) {
    if (value == null) {
      return "—";
    }
    if (typeof value === "string") {
      return value;
    }
    if (typeof value === "number") {
      if (!Number.isFinite(value)) {
        return "—";
      }
      if (Math.abs(value) >= 1000 || Math.abs(value) < 0.01) {
        return value.toExponential(2);
      }
      return value.toFixed(2);
    }
    if (typeof value === "boolean") {
      return value ? "true" : "false";
    }
    return String(value);
  }

  function mapGradient(color) {
    if (!gradientSampler) {
      return null;
    }
    const { width, height, data } = gradientSampler;
    if (!width || !height) {
      return null;
    }
    const row = Math.floor(height / 2);
    let bestIdx = 0;
    let bestScore = Infinity;
    for (let x = 0; x < width; x += 1) {
      const idx = (row * width + x) * 4;
      const dr = data[idx] - color.r;
      const dg = data[idx + 1] - color.g;
      const db = data[idx + 2] - color.b;
      const score = dr * dr + dg * dg + db * db;
      if (score < bestScore) {
        bestScore = score;
        bestIdx = x;
      }
    }
    return width > 1 ? bestIdx / (width - 1) : 0;
  }

  function lookupLut(hex) {
    if (!lutTable || !hex) {
      return null;
    }
    if (Array.isArray(lutTable)) {
      const entry = lutTable.find((item) => {
        if (typeof item !== "object" || !item) {
          return false;
        }
        const colorKey = item.color || item.hex || item.colour;
        return typeof colorKey === "string" && colorKey.toUpperCase() === hex;
      });
      if (entry && Object.prototype.hasOwnProperty.call(entry, "value")) {
        return entry.value;
      }
      if (entry && Object.prototype.hasOwnProperty.call(entry, "label")) {
        return entry.label;
      }
      return entry ?? null;
    }
    if (typeof lutTable === "object") {
      return (
        lutTable[hex] ??
        lutTable[hex.toLowerCase?.() || ""] ??
        null
      );
    }
    return null;
  }

  function formatIsoTimestamp(value) {
    if (!value) {
      return "—";
    }
    try {
      const date = new Date(value);
      if (!Number.isNaN(date.getTime())) {
        const iso = date.toISOString();
        if (
          date.getUTCHours() === 0 &&
          date.getUTCMinutes() === 0 &&
          date.getUTCSeconds() === 0
        ) {
          return iso.slice(0, 10);
        }
        return iso.replace("T", " ").replace("Z", " UTC");
      }
    } catch (formatError) {
      // ignore
    }
    return String(value);
  }

  function frameTimestampLabel(meta) {
    if (!meta) {
      return "—";
    }
    if (
      typeof meta.display_timestamp === "string" &&
      meta.display_timestamp.trim()
    ) {
      return meta.display_timestamp.trim();
    }
    if (typeof meta.label === "string" && meta.label.trim()) {
      return meta.label.trim();
    }
    if (typeof meta.timestamp === "string" && meta.timestamp.trim()) {
      return formatIsoTimestamp(meta.timestamp.trim());
    }
    if (meta.timestamp != null) {
      return formatIsoTimestamp(meta.timestamp);
    }
    return "—";
  }

  function updateControlsUI() {
    if (!controlsContainer || !controlsEnabled) {
      return;
    }
    if (playButton) {
      playButton.textContent = isPlaying ? "Pause" : "Play";
    }
    if (prevButton) {
      prevButton.disabled = totalFrames <= 1;
    }
    if (nextButton) {
      nextButton.disabled = totalFrames <= 1;
    }
  }

  function updateFrameHUD(meta) {
    if (frameTimestampEl) {
      frameTimestampEl.textContent = frameTimestampLabel(meta);
    }
  }

  function setPlaying(state) {
    isPlaying = Boolean(state);
    updateControlsUI();
  }

  function setFrame(index) {
    if (!frames || !frames.length) {
      return;
    }
    const total = frames.length;
    const nextIndex = ((index % total) + total) % total;
    currentFrameIndex = nextIndex;
    frameTime = 0;
    const meta = frames[currentFrameIndex];
    resolveTexture(meta.path, meta);
    updateFrameHUD(meta);
    updateControlsUI();
  }

  function stepFrame(delta) {
    setFrame(currentFrameIndex + delta);
  }

  if (controlsContainer && controlsEnabled) {
    if (playButton) {
      playButton.addEventListener("click", () => {
        setPlaying(!isPlaying);
      });
    }
    if (nextButton) {
      nextButton.addEventListener("click", () => {
        setPlaying(false);
        stepFrame(1);
      });
    }
    if (prevButton) {
      prevButton.addEventListener("click", () => {
        setPlaying(false);
        stepFrame(-1);
      });
    }
  }

  if (controlsEnabled) {
    document.addEventListener("keydown", (event) => {
      if (event.defaultPrevented) {
        return;
      }
      const tag = (event.target && event.target.tagName) || "";
      if (["INPUT", "TEXTAREA", "SELECT", "BUTTON"].includes(tag)) {
        return;
      }
      if (event.code === "Space") {
        event.preventDefault();
        setPlaying(!isPlaying);
      } else if (event.code === "ArrowRight") {
        event.preventDefault();
        setPlaying(false);
        stepFrame(1);
      } else if (event.code === "ArrowLeft") {
        event.preventDefault();
        setPlaying(false);
        stepFrame(-1);
      }
    });
  }

  function applyTexture(uri, texture, frameMeta) {
    texture.colorSpace = THREE.SRGBColorSpace;
    textureCache.set(uri, texture);
    sphereMaterial.map = texture;
    sphereMaterial.wireframe = false;
    sphereMaterial.needsUpdate = true;
    prepareSampler(texture, uri);
    if (frameMeta) {
      currentFrameMeta = frameMeta;
    }
    updateFrameHUD(frameMeta || currentFrameMeta);
    updateControlsUI();
  }

  function resolveTexture(uri, frameMeta) {
    if (!uri) {
      return;
    }
    currentTextureUri = uri;
    currentFrameMeta = frameMeta || currentFrameMeta;
    if (textureCache.has(uri)) {
      applyTexture(uri, textureCache.get(uri), frameMeta || currentFrameMeta);
      return;
    }
    loader.load(
      uri,
      (texture) => applyTexture(uri, texture, frameMeta || currentFrameMeta),
      undefined,
      (error) => console.warn("Failed to load texture", uri, error),
    );
  }

  const sphere = new THREE.Mesh(sphereGeometry, sphereMaterial);
  const globeGroup = new THREE.Group();
  globeGroup.add(sphere);
  scene.add(globeGroup);

  if (useLighting) {
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.7);
    scene.add(ambientLight);

    const directionalLight = new THREE.DirectionalLight(0xffffff, 0.6);
    directionalLight.position.set(5, 5, 5);
    scene.add(directionalLight);
  }

  function resizeRenderer() {
    const widthValue = config.width || window.innerWidth;
    const heightValue = config.height || window.innerHeight;
    renderer.setSize(widthValue, heightValue, false);
    camera.aspect = widthValue / heightValue;
    camera.updateProjectionMatrix();
    applyCameraDistance();
  }

  window.addEventListener("resize", resizeRenderer);
  resizeRenderer();

  const initialFrame = totalFrames ? frames[0] : null;
  if (initialFrame) {
    resolveTexture(initialFrame.path, initialFrame);
  } else if (config.texture) {
    resolveTexture(config.texture, null);
  }
  updateFrameHUD(initialFrame || currentFrameMeta);
  updateControlsUI();

  const raycaster = new THREE.Raycaster();
  const pointer = new THREE.Vector2();
  function setCursorDragging(active) {
    if (config.probe_enabled) {
      canvas.style.cursor = active ? "grabbing" : "crosshair";
    } else {
      canvas.style.cursor = active ? "grabbing" : "grab";
    }
  }

  function onPointerDown(event) {
    event.preventDefault();
    pointerState.set(event.pointerId, {
      x: event.clientX,
      y: event.clientY,
    });
    if (pointerState.size === 1) {
      isPointerDragging = true;
      setCursorDragging(true);
      if (canvas.setPointerCapture) {
        try {
          canvas.setPointerCapture(event.pointerId);
        } catch (captureError) {
          // ignore
        }
      }
    } else if (pointerState.size === 2) {
      const points = Array.from(pointerState.values());
      lastPinchDistance = Math.hypot(
        points[0].x - points[1].x,
        points[0].y - points[1].y,
      );
    }
    handlePointer(event);
  }

  function onPointerMove(event) {
    event.preventDefault();
    const previous = pointerState.get(event.pointerId);
    pointerState.set(event.pointerId, {
      x: event.clientX,
      y: event.clientY,
    });
    if (pointerState.size === 1 && previous && isPointerDragging) {
      const dx = event.clientX - previous.x;
      const dy = event.clientY - previous.y;
      globeGroup.rotation.y += dx * rotationSpeed;
      globeGroup.rotation.x += dy * rotationSpeed;
      globeGroup.rotation.x = Math.min(
        rotationClamp,
        Math.max(-rotationClamp, globeGroup.rotation.x),
      );
    } else if (pointerState.size === 2) {
      const points = Array.from(pointerState.values());
      const distance = Math.hypot(
        points[0].x - points[1].x,
        points[0].y - points[1].y,
      );
      if (lastPinchDistance != null) {
        const delta = distance - lastPinchDistance;
        cameraDistance -= delta * zoomSpeed;
        applyCameraDistance();
      }
      lastPinchDistance = distance;
    }
    handlePointer(event);
  }

  function releasePointer(event) {
    pointerState.delete(event.pointerId);
    if (canvas.releasePointerCapture) {
      try {
        canvas.releasePointerCapture(event.pointerId);
      } catch (releaseError) {
        // ignore
      }
    }
    if (pointerState.size < 2) {
      lastPinchDistance = null;
    }
    if (!pointerState.size) {
      isPointerDragging = false;
      setCursorDragging(false);
    }
  }

  function onPointerUp(event) {
    event.preventDefault();
    releasePointer(event);
    handlePointer(event);
  }

  function onPointerCancel(event) {
    releasePointer(event);
    clearProbe();
  }

  function onWheel(event) {
    event.preventDefault();
    cameraDistance += event.deltaY * zoomSpeed;
    applyCameraDistance();
  }

  canvas.addEventListener("pointerdown", onPointerDown, { passive: false });
  canvas.addEventListener("pointermove", onPointerMove, { passive: false });
  canvas.addEventListener("pointerup", onPointerUp, { passive: false });
  canvas.addEventListener("pointercancel", onPointerCancel, { passive: false });
  canvas.addEventListener("pointerleave", (event) => {
    releasePointer(event);
    clearProbe();
  });
  canvas.addEventListener("wheel", onWheel, { passive: false });

  function updateProbeDisplay(payload) {
    if (!probeLatEl || !probeLonEl) {
      return;
    }
    if (!payload) {
      probeLatEl.textContent = "—";
      probeLonEl.textContent = "—";
      if (probeFrameEl) probeFrameEl.textContent = "—";
      if (probeHexEl) probeHexEl.textContent = "—";
      if (probeGradientEl) probeGradientEl.textContent = "—";
      if (probeLutEl) probeLutEl.textContent = "—";
      if (probeValueEl) probeValueEl.textContent = "—";
      if (probeUnitsEl) probeUnitsEl.textContent = "—";
      if (probeSwatchEl) {
        probeSwatchEl.style.background = "transparent";
        probeSwatchEl.style.borderColor = "rgba(245, 247, 250, 0.65)";
      }
      return;
    }
    probeLatEl.textContent = `${payload.lat.toFixed(2)}°`;
    probeLonEl.textContent = `${payload.lon.toFixed(2)}°`;
    if (probeFrameEl) {
      if (payload.frameLabel) {
        probeFrameEl.textContent = payload.frameLabel;
      } else if (payload.frameTimestamp) {
        probeFrameEl.textContent = formatIsoTimestamp(payload.frameTimestamp);
      } else if (payload.frameIndex != null) {
        probeFrameEl.textContent = `#${payload.frameIndex + 1}`;
      } else {
        probeFrameEl.textContent = "—";
      }
    }
    if (probeHexEl) {
      probeHexEl.textContent = payload.hex || "—";
    }
    if (probeSwatchEl) {
      if (payload.hex) {
        probeSwatchEl.style.background = payload.hex;
        probeSwatchEl.style.borderColor = payload.hex;
      } else {
        probeSwatchEl.style.background = "transparent";
        probeSwatchEl.style.borderColor = "rgba(245, 247, 250, 0.65)";
      }
    }
    if (probeGradientEl) {
      probeGradientEl.textContent =
        payload.gradient != null ? `${(payload.gradient * 100).toFixed(1)}%` : "—";
    }
    if (probeLutEl) {
      probeLutEl.textContent = payload.lutValue != null ? String(payload.lutValue) : "—";
    }
    if (probeValueEl) {
      probeValueEl.textContent =
        payload.dataValue != null ? formatValue(payload.dataValue) : "—";
    }
    if (probeUnitsEl) {
      probeUnitsEl.textContent = payload.dataUnits ?? "—";
    }
  }

  function clearProbe() {
    updateProbeDisplay(null);
  }

  function handlePointer(event) {
    if (!config.probe_enabled) {
      return;
    }
    const rect = canvas.getBoundingClientRect();
    pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
    raycaster.setFromCamera(pointer, camera);
    const hits = raycaster.intersectObject(sphere);
    if (!hits.length) {
      clearProbe();
      return;
    }
    const hit = hits[0];
    let lat;
    let lon;
    if (hit.uv) {
      const u = hit.uv.x % 1;
      const v = hit.uv.y % 1;
      lon = u * 360 - 180;
      lat = v * 180 - 90;
    } else {
      globeGroup.updateMatrixWorld(true);
      const localPoint = globeGroup.worldToLocal(hit.point.clone()).normalize();
      lat = -THREE.MathUtils.radToDeg(Math.asin(localPoint.y));
      lon = THREE.MathUtils.radToDeg(Math.atan2(localPoint.z, localPoint.x));
    }
    if (lon > 180) {
      lon -= 360;
    }
    if (lon < -180) {
      lon += 360;
    }

    let hex = null;
    let gradientValue = null;
    let lutValue = null;
    let dataValue = null;
    let dataUnits = null;

    if (hit.uv) {
      const color = sampleTexture(hit.uv);
      if (color) {
        hex = formatHex(color);
        const gradientRatio = mapGradient(color);
        gradientValue = gradientRatio != null ? gradientRatio : null;
        lutValue = lookupLut(hex);
      }
    }

    if (probeDataset) {
      const nearest = nearestProbe(lat, lon, probeDataset);
      if (nearest) {
        dataValue = nearest.value;
        dataUnits = nearest.units ?? config.probe_units ?? null;
      }
    }

    updateProbeDisplay({
      lat,
      lon,
      hex,
      gradient: gradientValue,
      lutValue,
      dataValue,
      dataUnits,
      frameIndex: frames && frames.length ? currentFrameIndex : null,
      frameTimestamp:
        currentFrameMeta && currentFrameMeta.timestamp
          ? currentFrameMeta.timestamp
          : null,
      frameLabel: frameTimestampLabel(currentFrameMeta),
    });
  }

  if (config.probe_enabled) {
    clearProbe();
  }

  let lastTime = 0;
  let frameTime = 0;
  const frameDuration = Number(config.frame_duration) || 0.25;

  function render(time) {
    const delta = (time - lastTime) / 1000;
    lastTime = time;
    if (autoRotate && !isPointerDragging && pointerState.size === 0) {
      globeGroup.rotation.y += delta * 0.25;
    }
    if (
      config.animate === "time" &&
      frames &&
      frames.length > 1 &&
      isPlaying
    ) {
      frameTime += delta;
      if (frameTime >= frameDuration) {
        frameTime = 0;
        setFrame(currentFrameIndex + 1);
      }
    }
    renderer.render(scene, camera);
    requestAnimationFrame(render);
  }

  requestAnimationFrame(render);
})().catch((error) => {
  console.error("Zyra globe bootstrap failed", error);
});

"""
            ).strip()
            + "\n"
        )

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
        else:
            for entry in entries:
                entry["metadata"] = {
                    "elapsed_seconds": _elapsed_seconds(start_dt, entry["timestamp"])
                }
        return entries, meta_payload
