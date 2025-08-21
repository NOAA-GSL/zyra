from __future__ import annotations

import logging

from zyra.utils.cli_helpers import configure_logging_from_env


def handle_timeseries(ns) -> int:
    """Handle ``visualize timeseries`` CLI subcommand."""
    configure_logging_from_env()
    # Lazy import to reduce startup cost when visualization isn't used
    from zyra.visualization.timeseries_manager import TimeSeriesManager

    mgr = TimeSeriesManager(
        title=getattr(ns, "title", None),
        xlabel=getattr(ns, "xlabel", None),
        ylabel=getattr(ns, "ylabel", None),
        style=getattr(ns, "style", "line"),
    )
    mgr.render(
        input_path=ns.input,
        x=getattr(ns, "x", None),
        y=getattr(ns, "y", None),
        var=getattr(ns, "var", None),
        width=ns.width,
        height=ns.height,
        dpi=ns.dpi,
    )
    out = mgr.save(ns.output)
    if out:
        logging.info(out)
    return 0
