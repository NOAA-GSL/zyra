# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import logging
import os

from zyra.utils.cli_helpers import configure_logging_from_env
from zyra.visualization.cli_utils import features_from_ns


def handle_interactive(ns) -> int:
    """Handle ``visualize interactive`` CLI subcommand."""
    if getattr(ns, "verbose", False):
        os.environ["ZYRA_VERBOSITY"] = "debug"
    elif getattr(ns, "quiet", False):
        os.environ["ZYRA_VERBOSITY"] = "quiet"
    if getattr(ns, "trace", False):
        os.environ["ZYRA_SHELL_TRACE"] = "1"
    configure_logging_from_env()
    # Lazy import to reduce startup cost when visualization isn't used
    from zyra.visualization.interactive_manager import InteractiveManager

    mgr = InteractiveManager(engine=ns.engine, extent=ns.extent, cmap=ns.cmap)
    features = features_from_ns(ns)

    # Vector-specific passthrough
    extra = {}
    if ns.mode == "vector":
        extra.update(
            {
                "uvar": getattr(ns, "uvar", None),
                "vvar": getattr(ns, "vvar", None),
                "u": getattr(ns, "u", None),
                "v": getattr(ns, "v", None),
                "density": getattr(ns, "density", 0.2),
                "scale": getattr(ns, "scale", 1.0),
                "color": getattr(ns, "color", "#333333"),
                "streamlines": getattr(ns, "streamlines", False),
            }
        )

    mgr.render(
        input_path=ns.input,
        var=ns.var,
        mode=ns.mode,
        engine=ns.engine,
        cmap=ns.cmap,
        features=features,
        colorbar=ns.colorbar,
        label=ns.label,
        units=ns.units,
        timestamp=ns.timestamp,
        timestamp_loc=ns.timestamp_loc,
        tiles=ns.tiles,
        zoom=ns.zoom,
        width=ns.width,
        height=ns.height,
        **extra,
    )
    out = mgr.save(ns.output)
    if out:
        logging.info(out)
    return 0
