# SPDX-License-Identifier: Apache-2.0
"""CLI handler for interactive globe renderers."""

from __future__ import annotations

import logging
import os
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from zyra.connectors.credentials import (
    CredentialResolutionError,
    resolve_credentials,
)
from zyra.utils.cli_helpers import configure_logging_from_env
from zyra.visualization.cli_utils import resolve_basemap_ref
from zyra.visualization.renderers import available, create


def _is_remote_ref(value: Any) -> bool:
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


def _renderer_options(ns: Any) -> dict[str, Any]:
    """Translate argparse namespace into renderer keyword options."""

    def _coerce_bool(val: Any) -> bool:
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            v = val.strip().lower()
            if v in {"false", "0", "no", "off"}:
                return False
            if v in {"true", "1", "yes", "on"}:
                return True
        return bool(val)

    def _parse_iso_timestamp(raw: str) -> tuple[datetime, bool, bool]:
        value = str(raw).strip()
        if not value:
            raise ValueError("time value cannot be empty")
        use_z = False
        if value.endswith("Z"):
            use_z = True
            value = value[:-1]
        try:
            dt = datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"Invalid ISO-8601 timestamp '{raw}'") from exc
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
            use_z = True
        has_time = "T" in value
        return dt, has_time, use_z

    def _format_iso_timestamp(dt: datetime, has_time: bool, use_z: bool) -> str:
        if has_time:
            base = dt.isoformat(timespec="seconds")
            if use_z:
                if base.endswith("+00:00"):
                    base = base[:-6]
                return base + "Z" if not base.endswith("Z") else base
            return base
        return dt.date().isoformat()

    def _parse_time_period(spec: str | None) -> timedelta:
        if spec is None:
            return timedelta(days=1)
        value = str(spec).strip().lower()
        if not value:
            raise ValueError("time period cannot be empty")

        def _seconds(multiplier: float) -> timedelta:
            return timedelta(seconds=multiplier)

        if value.startswith("p") and value.endswith("d"):
            try:
                days = float(value[1:-1])
            except ValueError as exc:
                raise ValueError(f"Invalid period '{spec}'") from exc
            return timedelta(days=days)
        if value.endswith("day") or value.endswith("days"):
            try:
                days = float(value.split("day")[0])
            except ValueError as exc:
                raise ValueError(f"Invalid period '{spec}'") from exc
            return timedelta(days=days)
        unit_map = {
            "d": 86400,
            "h": 3600,
            "m": 60,
            "s": 1,
        }
        for suffix, seconds in unit_map.items():
            if value.endswith(suffix):
                try:
                    magnitude = float(value[:-1])
                except ValueError as exc:
                    raise ValueError(f"Invalid period '{spec}'") from exc
                return _seconds(magnitude * seconds)
        try:
            magnitude = float(value)
            return _seconds(magnitude)
        except ValueError as exc:
            raise ValueError(f"Invalid period '{spec}'") from exc

    def _generate_time_series(
        start_raw: str,
        end_raw: str,
        period_spec: str | None,
    ) -> list[str]:
        start_dt, start_has_time, start_use_z = _parse_iso_timestamp(start_raw)
        end_dt, end_has_time, end_use_z = _parse_iso_timestamp(end_raw)
        if start_dt > end_dt:
            raise ValueError(
                f"tile-time-start '{start_raw}' must be before or equal to tile-time-end '{end_raw}'"
            )
        step = _parse_time_period(period_spec)
        if step.total_seconds() <= 0:
            raise ValueError("tile-time-period must be positive")
        has_time = start_has_time or end_has_time
        use_z = start_use_z or end_use_z
        if not has_time:
            start_dt = datetime.combine(start_dt.date(), datetime.min.time())
            end_dt = datetime.combine(end_dt.date(), datetime.min.time())
        values: list[str] = []
        current = start_dt
        tolerance = timedelta(microseconds=500)
        max_steps = 5000
        steps = 0
        while current <= end_dt + tolerance:
            values.append(_format_iso_timestamp(current, has_time, use_z))
            current = current + step
            steps += 1
            if steps > max_steps:
                raise ValueError(
                    "Too many time steps generated; adjust tile-time-period or range."
                )
        final_value = _format_iso_timestamp(end_dt, has_time, use_z)
        if final_value not in values:
            values.append(final_value)
        return values

    options: dict[str, Any] = {
        "animate": ns.animate,
        "probe_enabled": _coerce_bool(getattr(ns, "probe", True)),
    }
    if ns.width is not None:
        options["width"] = ns.width
    if ns.height is not None:
        options["height"] = ns.height
    if ns.texture:
        options["texture"] = ns.texture
    if ns.texture_pattern:
        options["texture_pattern"] = ns.texture_pattern
    if ns.frame_list:
        options["frame_list"] = ns.frame_list
    if ns.frame_cache:
        options["frame_cache"] = ns.frame_cache
    if getattr(ns, "date_format", None):
        options["date_format"] = ns.date_format
    if getattr(ns, "frame_duration", None) is not None:
        options["frame_duration"] = ns.frame_duration
    if getattr(ns, "show_controls", None) is not None:
        options["show_controls"] = _coerce_bool(ns.show_controls)
    if ns.title:
        options["title"] = ns.title
    if ns.description:
        options["description"] = ns.description
    if ns.probe_gradient:
        options["probe_gradient"] = ns.probe_gradient
    if ns.probe_lut:
        options["probe_lut"] = ns.probe_lut
    if options["probe_enabled"] and ns.probe_data:
        options["probe_data"] = ns.probe_data
    if ns.probe_units:
        options["probe_units"] = ns.probe_units
    if ns.probe_var:
        options["probe_var"] = ns.probe_var
    if getattr(ns, "video_source", None):
        options["video_source"] = ns.video_source
    if getattr(ns, "start", None):
        options["video_start"] = ns.start
    if getattr(ns, "end", None):
        options["video_end"] = ns.end
    if getattr(ns, "fps", None):
        options["video_fps"] = ns.fps
    if getattr(ns, "period_seconds", None) is not None:
        options["period_seconds"] = ns.period_seconds
    if getattr(ns, "frames_meta", None):
        options["frames_meta"] = ns.frames_meta
    legend = getattr(ns, "legend", None)
    if legend:
        options["legend"] = legend
    if getattr(ns, "tile_url", None):
        options["tile_url"] = ns.tile_url
    if getattr(ns, "tile_type", None):
        options["tile_type"] = ns.tile_type
    if getattr(ns, "tile_scheme", None):
        options["tile_scheme"] = ns.tile_scheme
    if getattr(ns, "tile_min_level", None) is not None:
        options["tile_min_level"] = ns.tile_min_level
    if getattr(ns, "tile_max_level", None) is not None:
        options["tile_max_level"] = ns.tile_max_level
    if getattr(ns, "tile_credit", None):
        options["tile_credit"] = ns.tile_credit
    if getattr(ns, "tile_token", None):
        options["tile_token"] = ns.tile_token
    tile_param_entries = getattr(ns, "tile_param", None)
    if tile_param_entries:
        params: dict[str, str] = {}
        for entry in tile_param_entries:
            if "=" not in entry:
                raise SystemExit(f"Invalid tile-param '{entry}', expected KEY=VALUE")
            key, value = entry.split("=", 1)
            key = key.strip()
            if not key:
                raise SystemExit(f"Invalid tile-param '{entry}', missing key")
            params[key] = value.strip()
        options["tile_params"] = params
    if getattr(ns, "tile_time_key", None):
        options["tile_time_key"] = ns.tile_time_key
    tile_time_values = getattr(ns, "tile_time_values", None)
    time_range_start = getattr(ns, "tile_time_start", None)
    time_range_end = getattr(ns, "tile_time_end", None)
    time_range_period = getattr(ns, "tile_time_period", None)
    if (time_range_start and not time_range_end) or (
        time_range_end and not time_range_start
    ):
        raise SystemExit(
            "tile-time-start and tile-time-end must both be provided together."
        )
    collected_time_values: list[str] = []
    if tile_time_values:
        for value in tile_time_values:
            value_str = str(value).strip()
            if value_str:
                collected_time_values.append(value_str)
    if time_range_start and time_range_end:
        try:
            generated_values = _generate_time_series(
                time_range_start, time_range_end, time_range_period
            )
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        collected_time_values.extend(generated_values)
        options["tile_time_start"] = time_range_start
        options["tile_time_end"] = time_range_end
        if time_range_period:
            options["tile_time_period"] = time_range_period
    if collected_time_values:
        dedup: dict[tuple[datetime, bool, bool], tuple[datetime, bool, bool]] = {}
        for entry in collected_time_values:
            dt, has_time, use_z = _parse_iso_timestamp(entry)
            dedup[(dt, has_time, use_z)] = (dt, has_time, use_z)
        sorted_entries = sorted(dedup.values(), key=lambda item: item[0])
        options["tile_time_values"] = [
            _format_iso_timestamp(dt, has_time, use_z)
            for dt, has_time, use_z in sorted_entries
        ]
    shared_gradients = getattr(ns, "shared_gradient", None)
    if isinstance(shared_gradients, dict) and shared_gradients:
        options["shared_gradients"] = dict(shared_gradients)
    if ns.time_key:
        options["time_key"] = ns.time_key
    if ns.time_format:
        options["time_format"] = ns.time_format
    if hasattr(ns, "lighting") and ns.lighting is not None:
        options["lighting"] = _coerce_bool(ns.lighting)
    if hasattr(ns, "auto_rotate") and ns.auto_rotate is not None:
        options["auto_rotate"] = _coerce_bool(ns.auto_rotate)
    if getattr(ns, "auto_rotate_speed", None) is not None:
        options["auto_rotate_speed"] = ns.auto_rotate_speed
    if ns.credential_file:
        options["credential_file"] = ns.credential_file
    if ns.auth:
        options["auth"] = ns.auth
    if getattr(ns, "verbose", False):
        options["debug_overlay"] = True
    creds_entries = getattr(ns, "credential", None)
    if creds_entries:
        try:
            resolved = resolve_credentials(
                creds_entries,
                credential_file=getattr(ns, "credential_file", None),
                namespace="visualize.globe",
            )
        except CredentialResolutionError as exc:
            raise SystemExit(str(exc)) from exc
        options["credentials"] = dict(resolved.values)
        options["credentials_masked"] = dict(resolved.masked)
    return options


def _resolve_resource_option(
    ns: Any,
    attr: str,
    label: str,
    guards: list[object],
) -> None:
    """Resolve packaged asset references (pkg:..., bare names) to filesystem paths."""

    raw = getattr(ns, attr, None)
    if not raw:
        return
    raw_str = str(raw)
    if _is_remote_ref(raw_str):
        setattr(ns, attr, _normalize_remote_ref(raw_str))
        return
    resolved, guard = resolve_basemap_ref(raw)
    if resolved is None:
        raise SystemExit(f"{label} file not found: {raw}")
    setattr(ns, attr, resolved)
    if guard is not None:
        guards.append(guard)


def _resolve_resource_options(ns: Any, guards: list[object]) -> None:
    for attr, label in (
        ("texture", "Texture"),
        ("legend", "Legend"),
        ("probe_gradient", "Probe gradient"),
        ("probe_lut", "Probe LUT"),
        ("probe_data", "Probe data"),
    ):
        _resolve_resource_option(ns, attr, label, guards)


def _parse_shared_gradient_entry(entry: str) -> tuple[str, str]:
    raw = str(entry).strip()
    if not raw:
        raise SystemExit("shared-gradient entry cannot be empty")
    separators = ("=", "|", ":", ",")
    name = None
    value = None
    for sep in separators:
        if sep in raw:
            name, value = raw.split(sep, 1)
            break
    if name is None or value is None:
        raise SystemExit(
            f"Invalid shared-gradient '{entry}'. Expected NAME=PATH or NAME|PATH."
        )
    name = name.strip()
    value = value.strip()
    if not name:
        raise SystemExit(f"Shared gradient missing name: '{entry}'")
    if not value:
        raise SystemExit(f"Shared gradient missing path: '{entry}'")
    return name, value


def _resolve_shared_gradients(ns: Any, guards: list[object]) -> None:
    raw_entries = getattr(ns, "shared_gradient", None)
    if not raw_entries:
        return
    entries = [raw_entries] if isinstance(raw_entries, str) else list(raw_entries)
    mapping: dict[str, str] = {}
    for entry in entries:
        name, raw_path = _parse_shared_gradient_entry(entry)
        if _is_remote_ref(raw_path):
            mapping[name] = _normalize_remote_ref(raw_path)
            continue
        resolved, guard = resolve_basemap_ref(raw_path)
        if resolved is None:
            raise SystemExit(f"Shared gradient file not found: {raw_path}")
        mapping[name] = resolved
        if guard is not None:
            guards.append(guard)
    ns.shared_gradient = mapping


def handle_globe(ns: Any) -> int:
    """Handle ``visualize globe`` subcommand."""

    if getattr(ns, "verbose", False):
        os.environ["ZYRA_VERBOSITY"] = "debug"
    elif getattr(ns, "quiet", False):
        os.environ["ZYRA_VERBOSITY"] = "quiet"
    if getattr(ns, "trace", False):
        os.environ["ZYRA_SHELL_TRACE"] = "1"

    configure_logging_from_env()

    renderer_slugs = sorted(r.slug for r in available())
    if ns.target not in renderer_slugs:
        raise SystemExit(
            f"Unknown globe renderer '{ns.target}'. Available: {', '.join(renderer_slugs)}"
        )

    guards: list[object] = []
    try:
        _resolve_resource_options(ns, guards)
        _resolve_shared_gradients(ns, guards)
        renderer = create(ns.target, **_renderer_options(ns))
        bundle = renderer.build(output_dir=Path(ns.output))
    finally:
        for guard in guards:
            with suppress(Exception):
                guard.close()

    logging.info("Generated globe bundle at %s", bundle.index_html)
    if bundle.assets:
        logging.debug(
            "Bundle assets: %s",
            ", ".join(
                str(path.relative_to(bundle.output_dir)) for path in bundle.assets
            ),
        )
    return 0
