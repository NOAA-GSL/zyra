# SPDX-License-Identifier: Apache-2.0
"""Regional --extent must crop the viewport, not stamp a world map.

The managers hardcoded ``ax.set_global()``, so a regional render (e.g.
an HRRR CONUS product) wasted ~96% of the frame on empty world map.
``apply_view_extent`` crops to the configured extent and preserves the
global view for the full-globe default.
"""

from __future__ import annotations

import os

import numpy as np
import pytest

# Skip Cartopy-heavy tests unless explicitly enabled (repo convention,
# matching tests/visualization/test_managers.py).
_has_cartopy = False
try:  # pragma: no cover - import guard
    import cartopy  # noqa: F401

    _has_cartopy = True
except Exception:
    pass

_skip_cartopy_heavy = (not _has_cartopy) or os.environ.get(
    "DATAVIZHUB_RUN_CARTOPY_TESTS"
) != "1"
pytestmark = pytest.mark.skipif(
    _skip_cartopy_heavy,
    reason="Cartopy-heavy tests require cartopy and opt-in (DATAVIZHUB_RUN_CARTOPY_TESTS=1)",
)

import matplotlib  # noqa: E402

matplotlib.use("Agg")

from zyra.visualization.heatmap_manager import HeatmapManager  # noqa: E402
from zyra.visualization.styles import DEFAULT_EXTENT  # noqa: E402

CONUS = [-134.12, -60.89, 21.12, 52.63]


def _render(extent):
    mgr = HeatmapManager(extent=extent)
    data = np.random.rand(20, 40).astype("float32")
    fig = mgr.render(data)
    assert fig is not None
    geo_axes = [a for a in fig.axes if hasattr(a, "get_extent")]
    assert geo_axes, "no GeoAxes found on rendered figure"
    return geo_axes[0].get_extent()


def test_regional_extent_crops_viewport():
    west, east, south, north = _render(CONUS)
    assert west == pytest.approx(CONUS[0], abs=0.5)
    assert east == pytest.approx(CONUS[1], abs=0.5)
    assert south == pytest.approx(CONUS[2], abs=0.5)
    assert north == pytest.approx(CONUS[3], abs=0.5)


def test_default_extent_stays_global():
    west, east, south, north = _render(list(DEFAULT_EXTENT))
    assert east - west == pytest.approx(360.0, abs=1.0)
    assert north - south == pytest.approx(180.0, abs=1.0)
