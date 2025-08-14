from __future__ import annotations

from datavizhub.visualization.timeseries_manager import TimeSeriesManager
from datavizhub.utils.cli_helpers import configure_logging_from_env
import logging


def handle_timeseries(ns) -> int:
    """Handle ``visualize timeseries`` CLI subcommand."""
    configure_logging_from_env()
    mgr = TimeSeriesManager(title=getattr(ns, "title", None), xlabel=getattr(ns, "xlabel", None), ylabel=getattr(ns, "ylabel", None), style=getattr(ns, "style", "line"))
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
