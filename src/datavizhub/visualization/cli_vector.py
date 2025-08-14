from __future__ import annotations

from datavizhub.visualization.vector_field_manager import VectorFieldManager
from datavizhub.utils.cli_helpers import configure_logging_from_env
from datavizhub.visualization.cli_utils import features_from_ns
import logging


def handle_vector(ns) -> int:
    """Handle ``visualize vector`` CLI subcommand."""
    configure_logging_from_env()
    mgr = VectorFieldManager(
        basemap=ns.basemap,
        extent=ns.extent,
        color=getattr(ns, "color", "#333333"),
        density=getattr(ns, "density", 0.2),
        scale=getattr(ns, "scale", None),
        streamlines=getattr(ns, "streamlines", False),
    )
    features = features_from_ns(ns)
    mgr.render(
        input_path=getattr(ns, "input", None),
        uvar=getattr(ns, "uvar", None),
        vvar=getattr(ns, "vvar", None),
        u=getattr(ns, "u", None),
        v=getattr(ns, "v", None),
        width=ns.width,
        height=ns.height,
        dpi=ns.dpi,
        crs=getattr(ns, "crs", None),
        reproject=getattr(ns, "reproject", False),
        map_type=getattr(ns, "map_type", "image"),
        tile_source=getattr(ns, "tile_source", None),
        tile_zoom=getattr(ns, "tile_zoom", 3),
        features=features,
    )
    out = mgr.save(ns.output)
    if out:
        logging.info(out)
    return 0
