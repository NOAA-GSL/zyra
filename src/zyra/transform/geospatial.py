# SPDX-License-Identifier: Apache-2.0
"""Utilities for preparing geospatial datasets (shapefiles, CSV points) for animation."""

from __future__ import annotations

import csv
import json
import math
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

import shapefile  # pyshp

try:  # Python 3.9+
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - fallback for very old interpreters
    from backports.zoneinfo import ZoneInfo  # type: ignore

from zyra.utils.io_utils import open_output

_DEFAULT_SHAPE_TIME_FORMATS: Sequence[str] = (
    "%m/%d %I:%M %p",
    "%m/%d %I%M %p",
    "%m/%d %H:%M",
    "%m/%d %H%M",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d %I:%M %p",
)

_DEFAULT_CSV_TIME_FORMATS: Sequence[str] = (
    "%I:%M:%S %p",
    "%I:%M %p",
    "%H:%M:%S",
    "%H:%M",
)


def _coerce_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        if isinstance(value, float) and math.isnan(value):
            return None
        return int(value)
    except (ValueError, TypeError):
        return None


def _prepare_fallback_datetime(
    *,
    year: int | None,
    month: int | None,
    day: int | None,
    fallback_date: date | None,
) -> datetime | None:
    base_date = fallback_date
    if base_date is None:
        if year is None and month is None and day is None:
            return None
        year = year if year is not None else 1900
        month = month if month is not None else 1
        day = day if day is not None else 1
        try:
            base_date = date(year, month, day)
        except ValueError:
            return None
    return datetime.combine(base_date, datetime.min.time())


def _parse_local_datetime(
    value: str,
    *,
    timezone_name: str,
    formats: Sequence[str],
    fallback_dt: datetime | None,
) -> tuple[str | None, str | None]:
    value = (value or "").strip()
    if not value:
        return None, None
    zone = ZoneInfo(timezone_name)
    for fmt in formats:
        try:
            parsed = datetime.strptime(value, fmt)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=zone)
        else:  # pragma: no cover - rarely used, but handle tz-aware strings
            parsed = parsed.astimezone(zone)
        # Patch in fallback components when strptime supplied defaults
        if fallback_dt is not None:
            if parsed.year == 1900:
                parsed = parsed.replace(year=fallback_dt.year)
            if parsed.month == 1 and parsed.day == 1:
                parsed = parsed.replace(
                    month=fallback_dt.month,
                    day=fallback_dt.day,
                )
        # Avoid propagating 1900-01-01 without fallback context
        if parsed.year == 1900 and fallback_dt is None:
            continue
        local_iso = parsed.isoformat()
        utc_iso = parsed.astimezone(timezone.utc).isoformat()
        return local_iso, utc_iso
    return None, None


def shapefile_to_geojson(
    input_path: str | Path,
    *,
    time_fields: Iterable[str] | None = None,
    time_formats: Sequence[str] | None = None,
    timezone_name: str = "UTC",
    year_field: str | None = None,
    month_field: str | None = None,
    day_field: str | None = None,
    default_year: int | None = None,
    fallback_date: date | None = None,
    local_time_property: str = "time_local_iso",
    utc_time_property: str = "time_utc_iso",
) -> dict[str, Any]:
    """Convert a shapefile into a GeoJSON FeatureCollection.

    Parameters enable basic timestamp normalization by specifying which fields
    contain local time strings (``time_fields``) and optional contextual clues
    (`year_field`, `month_field`, `day_field`, or ``fallback_date``).
    """

    shp_path = Path(input_path)
    if not shp_path.exists():
        raise FileNotFoundError(f"Shapefile not found: {shp_path}")

    time_fields = tuple(time_fields or ("LocalTime",))
    time_formats = time_formats or _DEFAULT_SHAPE_TIME_FORMATS

    reader = shapefile.Reader(str(shp_path))
    field_names = [f[0] for f in reader.fields[1:]]  # skip deletion flag

    features: list[dict[str, Any]] = []
    for idx in range(len(reader)):
        record = reader.record(idx)
        shape = reader.shape(idx)
        props: dict[str, Any] = {}
        for f_idx, name in enumerate(field_names):
            value = record[f_idx]
            if isinstance(value, float) and math.isnan(value):
                value = None
            props[name] = value

        local_str: str | None = None
        for candidate in time_fields:
            if candidate in props and props[candidate]:
                local_str = str(props[candidate])
                break

        year_val = _coerce_int(props.get(year_field)) if year_field else default_year
        month_val = _coerce_int(props.get(month_field)) if month_field else None
        day_val = _coerce_int(props.get(day_field)) if day_field else None
        fallback_dt = _prepare_fallback_datetime(
            year=year_val,
            month=month_val,
            day=day_val,
            fallback_date=fallback_date,
        )
        local_iso, utc_iso = (None, None)
        if local_str is not None:
            local_iso, utc_iso = _parse_local_datetime(
                local_str,
                timezone_name=timezone_name,
                formats=time_formats,
                fallback_dt=fallback_dt,
            )
        props[local_time_property] = local_iso
        props[utc_time_property] = utc_iso

        geometry = getattr(shape, "__geo_interface__", None)
        if not geometry:
            geometry = {
                "type": "Polygon",
                "coordinates": shape.points,
            }
        feature: dict[str, Any] = {
            "type": "Feature",
            "geometry": geometry,
            "properties": props,
        }
        bbox = getattr(shape, "bbox", None)
        if bbox:
            feature["bbox"] = [float(v) for v in bbox]
        features.append(feature)

    collection: dict[str, Any] = {
        "type": "FeatureCollection",
        "features": features,
        "metadata": {
            "source": str(shp_path),
            "feature_count": len(features),
            "timezone": timezone_name,
            "time_fields": list(time_fields),
        },
    }
    if getattr(reader, "bbox", None):
        collection["bbox"] = [float(v) for v in reader.bbox]
    return collection


def write_shapefile_geojson(
    input_path: str | Path,
    output_path: str | Path,
    *,
    indent: int = 2,
    **kwargs: Any,
) -> None:
    payload = shapefile_to_geojson(input_path, **kwargs)
    with open_output(str(output_path)) as fh:
        fh.write(json.dumps(payload, indent=indent).encode("utf-8"))


def csv_points_to_geojson(
    input_csv: str | Path,
    *,
    lat_field: str = "Lat",
    lon_field: str = "Lon",
    local_time_fields: Iterable[str] | None = None,
    utc_time_fields: Iterable[str] | None = None,
    time_formats: Sequence[str] | None = None,
    timezone_name: str = "UTC",
    event_date: date | None = None,
    local_time_property: str = "time_local_iso",
    utc_time_property: str = "time_utc_iso",
) -> dict[str, Any]:
    """Convert a CSV table with latitude/longitude columns to GeoJSON points."""

    csv_path = Path(input_csv)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    local_time_fields = tuple(local_time_fields or ("Time (CDT)",))
    utc_time_fields = tuple(utc_time_fields or ("Time (Z)",))
    time_formats = time_formats or _DEFAULT_CSV_TIME_FORMATS

    features: list[dict[str, Any]] = []
    with csv_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            lat_val = row.get(lat_field)
            lon_val = row.get(lon_field)
            if not lat_val or not lon_val:
                continue
            try:
                lat = float(lat_val)
                lon = float(lon_val)
            except ValueError:
                continue

            local_str: str | None = None
            for field in local_time_fields:
                value = row.get(field)
                if value:
                    local_str = value
                    break

            fallback_dt = None
            if event_date is not None:
                fallback_dt = datetime.combine(event_date, datetime.min.time())

            local_iso, utc_iso = (None, None)
            if local_str:
                local_iso, utc_iso = _parse_local_datetime(
                    local_str,
                    timezone_name=timezone_name,
                    formats=time_formats,
                    fallback_dt=fallback_dt,
                )

            if utc_iso is None:
                for field in utc_time_fields:
                    value = (row.get(field) or "").strip()
                    if not value:
                        continue
                    try:
                        parsed = datetime.strptime(value, "%H:%M")
                    except ValueError:
                        continue
                    if event_date is None:
                        break
                    parsed = parsed.replace(
                        year=event_date.year,
                        month=event_date.month,
                        day=event_date.day,
                        tzinfo=timezone.utc,
                    )
                    utc_iso = parsed.isoformat()
                    if local_iso is None:
                        local_iso = parsed.astimezone(
                            ZoneInfo(timezone_name)
                        ).isoformat()
                    break

            props = dict(row)
            props[local_time_property] = local_iso
            props[utc_time_property] = utc_iso

            features.append(
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [lon, lat],
                    },
                    "properties": props,
                }
            )

    bbox = None
    if features:
        lons = [feat["geometry"]["coordinates"][0] for feat in features]
        lats = [feat["geometry"]["coordinates"][1] for feat in features]
        bbox = [min(lons), min(lats), max(lons), max(lats)]

    return {
        "type": "FeatureCollection",
        "features": features,
        "bbox": bbox,
        "metadata": {
            "source": str(csv_path),
            "feature_count": len(features),
            "timezone": timezone_name,
            "lat_field": lat_field,
            "lon_field": lon_field,
            "local_time_fields": list(local_time_fields),
            "utc_time_fields": list(utc_time_fields),
        },
    }


def write_csv_points_geojson(
    input_csv: str | Path,
    output_path: str | Path,
    *,
    indent: int = 2,
    **kwargs: Any,
) -> None:
    payload = csv_points_to_geojson(input_csv, **kwargs)
    with open_output(str(output_path)) as fh:
        fh.write(json.dumps(payload, indent=indent).encode("utf-8"))


__all__ = [
    "shapefile_to_geojson",
    "write_shapefile_geojson",
    "csv_points_to_geojson",
    "write_csv_points_geojson",
]
