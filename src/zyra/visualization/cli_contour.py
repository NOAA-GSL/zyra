# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import logging
import os
from pathlib import Path

from zyra.utils.cli_helpers import configure_logging_from_env, parse_levels_arg
from zyra.visualization.cli_utils import features_from_ns, resolve_basemap_ref


def handle_contour(ns) -> int:
    """Handle ``visualize contour`` CLI subcommand."""
    # Lazy import to reduce startup cost when visualization isn't used
    from zyra.visualization.contour_manager import ContourManager

    if getattr(ns, "verbose", False):
        os.environ["ZYRA_VERBOSITY"] = "debug"
    elif getattr(ns, "quiet", False):
        os.environ["ZYRA_VERBOSITY"] = "quiet"
    if getattr(ns, "trace", False):
        os.environ["ZYRA_SHELL_TRACE"] = "1"
    configure_logging_from_env()
    # Batch mode
    if getattr(ns, "inputs", None):
        outdir = getattr(ns, "output_dir", None)
        if not outdir:
            raise SystemExit("--output-dir is required when using --inputs")
        features = features_from_ns(ns)
        outdir_p = Path(outdir)
        outdir_p.mkdir(parents=True, exist_ok=True)
        import json

        outputs = []
        levels_val = parse_levels_arg(getattr(ns, "levels", 10))
        for src in ns.inputs:
            bmap, guard = resolve_basemap_ref(getattr(ns, "basemap", None))
            mgr = ContourManager(
                basemap=bmap,
                extent=ns.extent,
                filled=getattr(ns, "filled", False),
            )
            mgr.render(
                input_path=src,
                var=ns.var,
                xarray_engine=getattr(ns, "xarray_engine", None),
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
            base = Path(str(src)).stem
            dest = outdir_p / f"{base}.png"
            out = mgr.save(str(dest))
            if out:
                logging.info(out)
                outputs.append(out)
            if guard is not None:
                try:
                    guard.close()
                except Exception:
                    pass
        try:
            print(json.dumps({"outputs": outputs}))
        except Exception:
            pass
        return 0
    bmap, guard = resolve_basemap_ref(getattr(ns, "basemap", None))
    if os.environ.get("ZYRA_SHELL_TRACE"):
        logging.info("+ input='%s'", ns.input)
        if getattr(ns, "output", None):
            logging.info("+ output='%s'", ns.output)
        logging.info("+ extent=%s", " ".join(map(str, ns.extent)))
        logging.info("+ size=%dx%d dpi=%d", ns.width, ns.height, ns.dpi)
        if bmap:
            logging.info("+ basemap='%s'", bmap)
    mgr = ContourManager(
        basemap=bmap, extent=ns.extent, filled=getattr(ns, "filled", False)
    )
    features = features_from_ns(ns)
    levels_val = parse_levels_arg(getattr(ns, "levels", 10))
    mgr.render(
        input_path=ns.input,
        var=ns.var,
        xarray_engine=getattr(ns, "xarray_engine", None),
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
    if guard is not None:
        try:
            guard.close()
        except Exception:
            pass
    return 0
