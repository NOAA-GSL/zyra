# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from zyra.utils.cli_helpers import configure_logging_from_env
from zyra.visualization.cli_utils import features_from_ns, resolve_basemap_ref


def handle_vector(ns) -> int:
    """Handle ``visualize vector`` CLI subcommand."""
    # Lazy import to reduce startup cost when visualization isn't used
    from zyra.visualization.vector_field_manager import VectorFieldManager

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
        outdir_p = Path(outdir)
        outdir_p.mkdir(parents=True, exist_ok=True)
        features = features_from_ns(ns)
        outputs = []
        for src in ns.inputs:
            bmap, guard = resolve_basemap_ref(getattr(ns, "basemap", None))
            mgr = VectorFieldManager(
                basemap=bmap,
                extent=ns.extent,
                color=getattr(ns, "color", "#333333"),
                density=getattr(ns, "density", 0.2),
                scale=getattr(ns, "scale", None),
                streamlines=getattr(ns, "streamlines", False),
            )
            mgr.render(
                input_path=src,
                uvar=getattr(ns, "uvar", None),
                vvar=getattr(ns, "vvar", None),
                u=getattr(ns, "u", None),
                v=getattr(ns, "v", None),
                xarray_engine=getattr(ns, "xarray_engine", None),
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
        if getattr(ns, "input", None):
            logging.info("+ input='%s'", ns.input)
        if getattr(ns, "output", None):
            logging.info("+ output='%s'", ns.output)
        logging.info("+ extent=%s", " ".join(map(str, ns.extent)))
        logging.info("+ size=%dx%d dpi=%d", ns.width, ns.height, ns.dpi)
        if bmap:
            logging.info("+ basemap='%s'", bmap)
    mgr = VectorFieldManager(
        basemap=bmap,
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
        xarray_engine=getattr(ns, "xarray_engine", None),
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
    if guard is not None:
        try:
            guard.close()
        except Exception:
            pass
    return 0
