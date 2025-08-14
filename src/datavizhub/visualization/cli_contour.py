from __future__ import annotations

from datavizhub.utils.cli_helpers import parse_levels_arg, configure_logging_from_env
import logging
from datavizhub.visualization.contour_manager import ContourManager
from datavizhub.visualization.cli_utils import features_from_ns


def handle_contour(ns) -> int:
    """Handle ``visualize contour`` CLI subcommand."""
    configure_logging_from_env()
    mgr = ContourManager(basemap=ns.basemap, extent=ns.extent, filled=getattr(ns, "filled", False))
    features = features_from_ns(ns)
    levels_val = parse_levels_arg(getattr(ns, "levels", 10))
    mgr.render(
        input_path=ns.input,
        var=ns.var,
        width=ns.width,
        height=ns.height,
        dpi=ns.dpi,
        cmap=ns.cmap,
        levels=levels_val,
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
