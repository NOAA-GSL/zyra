import os
import tempfile

import numpy as np


def test_heatmap_manager_colorbar_axes():
    try:
        from datavizhub.visualization import HeatmapManager
        import matplotlib
    except Exception as e:
        import pytest

        pytest.skip(f"Visualization deps missing: {e}")

    data = np.random.rand(10, 20)
    hm = HeatmapManager()
    fig = hm.render(data, width=200, height=100, dpi=100, colorbar=True, label="Value", units="m/s")
    # Expect at least two axes: main + colorbar
    assert hasattr(fig, "axes") and len(fig.axes) >= 2
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "cb.png")
        path = hm.save(out)
        assert path and os.path.exists(path)
        assert os.path.getsize(path) > 0

