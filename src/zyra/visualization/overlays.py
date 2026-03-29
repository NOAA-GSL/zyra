# SPDX-License-Identifier: Apache-2.0
"""Overlay rendering helpers for ``visualize animate``."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Iterator, MutableMapping, Optional

import cartopy.crs as ccrs
from matplotlib.axes import Axes

from zyra.utils.iso8601 import to_datetime

# ----------------------------------------------------------------------------
# Data models


@dataclass
class OverlayFeature:
    geometry: dict[str, Any]
    properties: dict[str, Any]
    timestamp: Optional[datetime] = None


@dataclass
class OverlayDataset:
    alias: str
    path: Path
    style: str
    static_features: list[OverlayFeature] = field(default_factory=list)
    features_by_index: MutableMapping[int, list[OverlayFeature]] = field(
        default_factory=dict
    )

    def features_for_index(self, index: int) -> Iterable[OverlayFeature]:
        items = []
        items.extend(self.static_features)
        items.extend(self.features_by_index.get(index, []))
        return items


@dataclass
class OverlaySpec:
    alias: str
    path: Path
    style: str
    time_key: Optional[str]


# ----------------------------------------------------------------------------
# Style registry


class OverlayStyleError(ValueError):
    pass


def _coord_pair(coord: Iterable[Any]) -> tuple[float, float]:
    seq = list(coord)
    if len(seq) < 2:
        raise ValueError("Coordinate must have at least two values")
    return float(seq[0]), float(seq[1])


def _iter_points(geometry: dict[str, Any]) -> Iterator[tuple[float, float]]:
    geometry = geometry or {}
    gtype = geometry.get("type")
    if gtype == "Point":
        coords = geometry.get("coordinates")
        if coords:
            try:
                yield _coord_pair(coords)
            except ValueError:
                return
    elif gtype == "MultiPoint":
        for coords in geometry.get("coordinates", []):
            try:
                yield _coord_pair(coords)
            except ValueError:
                continue
    elif gtype == "GeometryCollection":
        for geom in geometry.get("geometries", []):
            yield from _iter_points(geom)


def _iter_polygon_rings(
    geometry: dict[str, Any],
) -> Iterator[list[tuple[float, float]]]:
    gtype = geometry.get("type")
    if gtype == "Polygon":
        coords = geometry.get("coordinates", [])
        if coords:
            points = []
            for coord in coords[0]:
                try:
                    points.append(_coord_pair(coord))
                except ValueError:
                    continue
            if points:
                yield points
    elif gtype == "MultiPolygon":
        for polygon in geometry.get("coordinates", []):
            if not polygon:
                continue
            points = []
            for coord in polygon[0]:
                try:
                    points.append(_coord_pair(coord))
                except ValueError:
                    continue
            if points:
                yield points
    elif gtype == "GeometryCollection":
        for geom in geometry.get("geometries", []):
            yield from _iter_polygon_rings(geom)


def draw_red_dots(ax: Axes, features: Iterable[OverlayFeature]) -> None:
    lons: list[float] = []
    lats: list[float] = []
    for feat in features:
        for lon, lat in _iter_points(feat.geometry):
            lons.append(lon)
            lats.append(lat)
    if not lons:
        return
    ax.scatter(
        lons,
        lats,
        transform=ccrs.PlateCarree(),
        color="#ff3b30",
        edgecolor="white",
        linewidth=0.5,
        s=24,
        zorder=5,
    )


def draw_magenta_outline(ax: Axes, features: Iterable[OverlayFeature]) -> None:
    for feat in features:
        for ring in _iter_polygon_rings(feat.geometry):
            if len(ring) < 2:
                continue
            lons = [lon for lon, _ in ring]
            lats = [lat for _, lat in ring]
            ax.plot(
                lons,
                lats,
                transform=ccrs.PlateCarree(),
                color="#ff00ff",
                linewidth=1.2,
                linestyle="-",
                zorder=4,
            )


STYLE_REGISTRY: dict[str, Any] = {
    "red-dots": draw_red_dots,
    "magenta-outline": draw_magenta_outline,
}


def resolve_style(style: str) -> Any:
    if style not in STYLE_REGISTRY:
        raise OverlayStyleError(f"Unsupported overlay style: {style}")
    return STYLE_REGISTRY[style]


# ----------------------------------------------------------------------------
# Loading and assignment


def parse_overlay_spec(text: str) -> OverlaySpec:
    alias: Optional[str] = None
    payload = text
    if "=" in text and not text.strip().startswith("/"):
        alias, payload = text.split("=", 1)
    if ":" in payload:
        path_str, style = payload.rsplit(":", 1)
    else:
        path_str, style = payload, "auto"
    path = Path(path_str).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"Overlay file not found: {path}")
    resolved_alias = alias or path.stem
    resolved_style = style if style != "auto" else infer_default_style(path)
    return OverlaySpec(resolved_alias, path, resolved_style, None)


def infer_default_style(path: Path) -> str:
    if path.suffix.lower() in {".geojson", ".json"}:
        try:
            with path.open("r", encoding="utf-8") as fp:
                data = json.load(fp)
            geom_type = data.get("features", [{}])[0].get("geometry", {}).get("type")
            if geom_type and "point" in geom_type.lower():
                return "red-dots"
        except Exception:
            pass
        return "magenta-outline"
    return "red-dots"


def build_overlay_datasets(
    specs: list[OverlaySpec],
    frame_times: list[datetime],
    *,
    default_time_key: Optional[str] = None,
    time_keys: Optional[dict[str, str]] = None,
    tolerance: timedelta = timedelta(minutes=15),
) -> list[OverlayDataset]:
    datasets: list[OverlayDataset] = []
    for spec in specs:
        time_key = spec.time_key
        if time_key is None and time_keys:
            time_key = time_keys.get(spec.alias)
        if time_key is None:
            time_key = default_time_key
        dataset = load_overlay_dataset(
            spec,
            frame_times=frame_times,
            time_key=time_key,
            tolerance=tolerance,
        )
        datasets.append(dataset)
    return datasets


def load_overlay_dataset(
    spec: OverlaySpec,
    *,
    frame_times: list[datetime],
    time_key: Optional[str],
    tolerance: timedelta,
) -> OverlayDataset:
    with spec.path.open("r", encoding="utf-8") as fp:
        payload = json.load(fp)
    features_raw = extract_features(payload)
    dataset = OverlayDataset(alias=spec.alias, path=spec.path, style=spec.style)
    assign_features(dataset, features_raw, frame_times, time_key, tolerance)
    return dataset


def extract_features(obj: dict[str, Any]) -> list[OverlayFeature]:
    features: list[OverlayFeature] = []
    if obj.get("type") == "FeatureCollection":
        for feat in obj.get("features", []):
            geometry = feat.get("geometry") or {}
            properties = feat.get("properties") or {}
            features.append(
                OverlayFeature(
                    geometry=geometry,
                    properties=properties,
                )
            )
    elif obj.get("type") == "Feature":
        features.append(
            OverlayFeature(
                geometry=obj.get("geometry") or {},
                properties=obj.get("properties") or {},
            )
        )
    else:
        raise ValueError("Overlay data must be a GeoJSON FeatureCollection or Feature")
    return features


def assign_features(
    dataset: OverlayDataset,
    features: list[OverlayFeature],
    frame_times: list[datetime],
    time_key: Optional[str],
    tolerance: timedelta,
) -> None:
    if not frame_times:
        dataset.static_features.extend(features)
        return
    for feat in features:
        timestamp = None
        if time_key:
            raw = feat.properties.get(time_key)
            timestamp = to_datetime(raw) if raw is not None else None
        feat.timestamp = timestamp
        if timestamp is None:
            dataset.static_features.append(feat)
            continue
        idx = _match_frame_index(frame_times, timestamp, tolerance)
        if idx is None:
            dataset.static_features.append(feat)
        else:
            dataset.features_by_index.setdefault(idx, []).append(feat)


def _match_frame_index(
    frame_times: list[datetime],
    target: datetime,
    tolerance: timedelta,
) -> Optional[int]:
    best_idx = None
    best_delta = None
    for idx, frame_time in enumerate(frame_times):
        delta = abs(frame_time - target)
        if best_delta is None or delta < best_delta:
            best_delta = delta
            best_idx = idx
    if best_idx is None or best_delta is None:
        return None
    if best_delta > tolerance:
        return None
    return best_idx


class OverlayRenderer:
    """Draw overlay datasets on Matplotlib axes."""

    def __init__(self, datasets: list[OverlayDataset]):
        self.datasets = datasets

    def draw(self, ax: Axes, frame_index: int) -> None:
        for dataset in self.datasets:
            style_fn = resolve_style(dataset.style)
            features = list(dataset.features_for_index(frame_index))
            if not features:
                continue
            style_fn(ax, features)

    def describe(self) -> list[dict[str, str]]:
        entries: list[dict[str, str]] = []
        for dataset in self.datasets:
            entries.append(
                {
                    "alias": dataset.alias,
                    "path": str(dataset.path),
                    "style": dataset.style,
                }
            )
        return entries
