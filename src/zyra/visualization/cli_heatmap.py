# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from zyra.utils.cli_helpers import configure_logging_from_env
from zyra.visualization.cli_utils import features_from_ns, resolve_basemap_ref


def handle_heatmap(ns) -> int:
    """Handle ``visualize heatmap`` CLI subcommand.

    Input/validation errors (unsupported suffix, missing --var,
    GeoTIFF band out of range, missing rasterio) surface as a clean
    logged error with exit code 2 instead of a traceback.
    """
    try:
        return _handle_heatmap_impl(ns)
    except ValueError as exc:
        logging.error(str(exc))
        return 2


def _handle_heatmap_impl(ns) -> int:
    # Lazy import to reduce startup cost when visualization isn't used
    from zyra.visualization.heatmap_manager import HeatmapManager

    if getattr(ns, "verbose", False):
        os.environ["ZYRA_VERBOSITY"] = "debug"
    elif getattr(ns, "quiet", False):
        os.environ["ZYRA_VERBOSITY"] = "quiet"
    if getattr(ns, "trace", False):
        os.environ["ZYRA_SHELL_TRACE"] = "1"
    configure_logging_from_env()
    from zyra.visualization.cli_utils import resolve_cmap_args, resolve_extent

    ns.extent = resolve_extent(ns)
    cmap, norm = resolve_cmap_args(ns)
    if not getattr(ns, "inputs", None) and not getattr(ns, "input", None):
        raise ValueError(
            "--input is required (or use --inputs with --output-dir for batch rendering)"
        )
    # --output-names is positional against --inputs, so in single-input
    # mode there is nothing for it to line up with. Say so rather than
    # accepting it and renaming nothing.
    if getattr(ns, "output_names", None) and not getattr(ns, "inputs", None):
        raise ValueError(
            "--output-names applies to --inputs batch mode; use --output to name a single --input"
        )
    # Batch mode: --inputs with --output-dir
    if getattr(ns, "inputs", None):
        outdir = getattr(ns, "output_dir", None)
        if not outdir:
            raise ValueError("--output-dir is required when using --inputs")
        features = features_from_ns(ns)
        from zyra.utils.cli_helpers import resolve_batch_output_names

        dest_names = resolve_batch_output_names(
            [str(x) for x in ns.inputs],
            getattr(ns, "output_names", None),
            derive=lambda src: f"{Path(str(src)).stem}.png",
        )
        outdir_p = Path(outdir)
        outdir_p.mkdir(parents=True, exist_ok=True)
        outputs = []
        for idx, src in enumerate(ns.inputs):
            bmap, guard = resolve_basemap_ref(getattr(ns, "basemap", None))
            mgr = HeatmapManager(basemap=bmap, extent=ns.extent)
            mgr.render(
                input_path=src,
                var=ns.var,
                xarray_engine=getattr(ns, "xarray_engine", None),
                band=getattr(ns, "band", 1),
                width=ns.width,
                height=ns.height,
                dpi=ns.dpi,
                cmap=cmap,
                norm=norm,
                vmin=getattr(ns, "vmin", None),
                vmax=getattr(ns, "vmax", None),
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
            dest = outdir_p / dest_names[idx]
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
        _maybe_write_legend(ns, cmap, norm)
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
    mgr = HeatmapManager(basemap=bmap, extent=ns.extent)
    features = features_from_ns(ns)
    mgr.render(
        input_path=ns.input,
        var=ns.var,
        xarray_engine=getattr(ns, "xarray_engine", None),
        band=getattr(ns, "band", 1),
        width=ns.width,
        height=ns.height,
        dpi=ns.dpi,
        cmap=cmap,
        norm=norm,
        vmin=getattr(ns, "vmin", None),
        vmax=getattr(ns, "vmax", None),
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
    _maybe_write_legend(ns, cmap, norm)
    return 0


def _maybe_write_legend(ns, cmap, norm) -> None:
    """Write the standalone legend when --legend-file was requested."""
    legend_file = getattr(ns, "legend_file", None)
    if not legend_file:
        return
    from zyra.visualization.cli_utils import write_legend

    out = write_legend(
        legend_file,
        cmap=cmap,
        norm=norm,
        vmin=getattr(ns, "vmin", None),
        vmax=getattr(ns, "vmax", None),
        label=getattr(ns, "label", None),
        orientation=getattr(ns, "legend_orientation", "horizontal"),
    )
    logging.info(out)
