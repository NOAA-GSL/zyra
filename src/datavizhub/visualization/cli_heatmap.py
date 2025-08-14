from __future__ import annotations

from datavizhub.visualization.heatmap_manager import HeatmapManager
from datavizhub.utils.cli_helpers import configure_logging_from_env
import logging
from datavizhub.visualization.cli_utils import features_from_ns


def handle_heatmap(ns) -> int:
    """Handle ``visualize heatmap`` CLI subcommand."""
    configure_logging_from_env()
    mgr = HeatmapManager(basemap=ns.basemap, extent=ns.extent)
    features = features_from_ns(ns)
    mgr.render(
        input_path=ns.input,
        var=ns.var,
        width=ns.width,
        height=ns.height,
        dpi=ns.dpi,
        cmap=ns.cmap,
        colorbar=getattr(ns, "colorbar", False),
        label=getattr(ns, "label", None),
        units=getattr(ns, "units", None),
        map_type=getattr(ns, "map_type", "image"),
        tile_source=getattr(ns, "tile_source", None),
        tile_zoom=getattr(ns, "tile_zoom", 3),
        features=features,
        timestamp=getattr(ns, "timestamp", None),
        timestamp_loc=getattr(ns, "timestamp_loc", "lower_right"),
        crs=getattr(ns, "crs", None),
        reproject=getattr(ns, "reproject", False),
    )
    out = mgr.save(ns.output)
    if out:
        logging.info(out)
    return 0
