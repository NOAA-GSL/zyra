# SPDX-License-Identifier: Apache-2.0
import json
from datetime import datetime, timedelta

import cartopy.crs as ccrs
import matplotlib.pyplot as plt

from zyra.visualization.overlays import (
    OverlayRenderer,
    build_overlay_datasets,
    parse_overlay_spec,
)


def _dt(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def test_build_overlay_datasets_assigns_by_time(tmp_path):
    data = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [-97.5, 35.5]},
                "properties": {"issued": "2025-03-14T15:00:00Z"},
            },
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [-97.4, 35.6]},
                "properties": {"issued": "2025-03-14T15:05:00Z"},
            },
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [-97.3, 35.7]},
                "properties": {},
            },
        ],
    }
    path = tmp_path / "detections.geojson"
    path.write_text(json.dumps(data), encoding="utf-8")

    spec = parse_overlay_spec(f"{path}:red-dots")
    spec.time_key = "issued"

    frame_times = [
        _dt("2025-03-14T15:00:00Z"),
        _dt("2025-03-14T15:05:00Z"),
    ]

    datasets = build_overlay_datasets(
        [spec],
        frame_times=frame_times,
        tolerance=timedelta(minutes=2),
    )
    dataset = datasets[0]

    frame0 = list(dataset.features_for_index(0))
    frame1 = list(dataset.features_for_index(1))

    assert len(frame0) == 2  # includes static feature
    assert len(frame1) == 2

    static = [f for f in dataset.static_features]
    assert len(static) == 1
    assert static[0].properties == {}


def test_overlay_renderer_draw(tmp_path):
    payload = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [-97.6, 35.4],
                            [-97.4, 35.4],
                            [-97.4, 35.6],
                            [-97.6, 35.6],
                            [-97.6, 35.4],
                        ]
                    ],
                },
                "properties": {},
            }
        ],
    }
    path = tmp_path / "warnings.geojson"
    path.write_text(json.dumps(payload), encoding="utf-8")

    spec = parse_overlay_spec(f"{path}:magenta-outline")
    datasets = build_overlay_datasets(
        [spec],
        frame_times=[_dt("2025-03-14T15:00:00Z")],
    )
    renderer = OverlayRenderer(datasets)

    fig, ax = plt.subplots(subplot_kw={"projection": ccrs.PlateCarree()})
    renderer.draw(ax, 0)
    # Matplotlib adds Line2D for outline
    lines = [
        artist for artist in ax.get_children() if artist.__class__.__name__ == "Line2D"
    ]
    assert lines, "Expected overlay line to be drawn"
    plt.close(fig)
