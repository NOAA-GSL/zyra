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
    # Data-encoded output is a different artifact, not a different
    # style of the same one: it never builds a figure, never composites
    # a basemap, and must not resample. Branch before any of that —
    # including before resolve_cmap_args, whose rules are about the
    # figure. It rejects --vmin/--vmax alongside a classified palette
    # because a picture takes its bounds from the palette table; a
    # data-encoded frame *requires* them, since they define what luma
    # means. Running it first made classified + --data-encoded
    # impossible to invoke even though _sample_palette handles it.
    if getattr(ns, "data_encoded", False):
        return _handle_data_encoded(ns)

    from zyra.visualization.cli_utils import resolve_cmap_args, resolve_extent

    ns.extent = resolve_extent(ns)
    cmap, norm = resolve_cmap_args(ns)

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


def _reject_figure_canvas_args(ns) -> None:
    """Refuse --width/--height/--dpi in data-encoded mode.

    These size a matplotlib figure. A data-encoded frame is written at
    the source grid and never builds one, so honouring them would mean
    resampling values nobody measured — which is the failure this whole
    output exists to avoid. Accepting them and quietly doing something
    else is worse than refusing: the caller reads the flag they passed,
    sees a file, and has no way to learn the size never applied.

    Refusing rather than warning matches how this module already treats
    a meaningless combination — --output-names without --inputs, and
    --vmin/--vmax against a classified palette both exit 2. Regridding
    belongs upstream, where it is a deliberate and inspectable step.

    Only non-default values are refused. argparse cannot distinguish an
    omitted flag from one passed at its default, so `--width 1024` is
    indistinguishable from silence here and slips through. The API
    model has no such blind spot — its fields default to None — and
    rejects any value at all, so the two surfaces differ only in that
    the API is the stricter one.
    """
    from zyra.visualization.cli_register import (
        HEATMAP_DEFAULT_DPI,
        HEATMAP_DEFAULT_HEIGHT,
        HEATMAP_DEFAULT_WIDTH,
    )

    supplied = [
        name
        for name, default in (
            ("--width", HEATMAP_DEFAULT_WIDTH),
            ("--height", HEATMAP_DEFAULT_HEIGHT),
            ("--dpi", HEATMAP_DEFAULT_DPI),
        )
        if getattr(ns, name.lstrip("-"), default) not in (None, default)
    ]
    if supplied:
        raise ValueError(
            f"{'/'.join(supplied)} cannot be used with --data-encoded: the frame is "
            "written at the source grid, and resizing it would average values that "
            "were never measured. Regrid upstream instead."
        )


def _handle_data_encoded(ns) -> int:
    """Write value-exact grayscale frames plus the palette sidecar.

    Mirrors the picture path's single/batch shapes and its
    ValueError -> exit-2 contract, but shares none of its rendering:
    the figure pipeline refits the extent to the axes aspect and
    resamples, which is fine for a picture and fatal for a value
    encoding.

    The legend still comes from --legend-file on the picture path and
    matters more than before, since the frames are now unreadable by
    eye.
    """
    from zyra.visualization.luma_writer import write_luma_png

    vmin = getattr(ns, "vmin", None)
    vmax = getattr(ns, "vmax", None)
    if vmin is None or vmax is None:
        raise ValueError("--vmin and --vmax are required with --data-encoded")
    _reject_figure_canvas_args(ns)

    palette = None
    cmap_file = getattr(ns, "cmap_file", None)
    if cmap_file:
        from zyra.visualization.cli_utils import load_palette_spec

        palette = load_palette_spec(cmap_file)

    def _load(src: str):
        from zyra.visualization.cli_utils import load_data_array

        return load_data_array(
            src,
            var=getattr(ns, "var", None),
            xarray_engine=getattr(ns, "xarray_engine", None),
            band=getattr(ns, "band", 1),
        )

    def _write(src: str, dest: str) -> str:
        # Deliberately NOT plumbing --width/--height through. They
        # default to 1024x512 for the figure path, and applying a
        # picture's default canvas size to a data raster would
        # resample every frame by default — silently averaging values
        # that were never measured, which is the exact failure this
        # whole path exists to avoid. A data-encoded frame is written
        # at the source grid; regrid upstream if a different grid is
        # wanted, where the resampling is a deliberate, inspectable
        # step rather than a side effect of a canvas default.
        arr = _load(src)
        out = write_luma_png(arr, dest, vmin=float(vmin), vmax=float(vmax))
        logging.info("+ data-encoded %s at %dx%d", dest, arr.shape[1], arr.shape[0])
        return out

    outputs: list[str] = []
    if getattr(ns, "inputs", None):
        outdir = getattr(ns, "output_dir", None)
        if not outdir:
            raise ValueError("--output-dir is required when using --inputs")
        from zyra.utils.cli_helpers import resolve_batch_output_names

        dest_names = resolve_batch_output_names(
            [str(x) for x in ns.inputs],
            getattr(ns, "output_names", None),
            derive=lambda src: f"{Path(str(src)).stem}.png",
        )
        outdir_p = Path(outdir)
        outdir_p.mkdir(parents=True, exist_ok=True)
        for idx, src in enumerate(ns.inputs):
            out = _write(str(src), str(outdir_p / dest_names[idx]))
            logging.info(out)
            outputs.append(out)
        try:
            print(json.dumps({"outputs": outputs}))
        except Exception:
            pass
    else:
        out = _write(str(ns.input), str(ns.output))
        logging.info(out)
        outputs.append(out)

    _maybe_write_color_scale(ns, palette, vmin, vmax)
    return 0


def _maybe_write_color_scale(ns, palette, vmin, vmax) -> None:
    """Write the sidecar when --color-scale-file was requested.

    Optional, so a caller can render frames in one invocation and the
    sidecar in another — but a data-encoded dataset published without
    one renders as raw grayscale, so the omission is worth a warning.
    """
    from zyra.visualization.luma_writer import build_color_scale

    dest = getattr(ns, "color_scale_file", None)
    if not dest:
        logging.warning(
            "--data-encoded without --color-scale-file: the frames carry "
            "values but nothing describes the palette or scale"
        )
        return
    scale = build_color_scale(
        palette, vmin=float(vmin), vmax=float(vmax), units=getattr(ns, "units", None)
    )
    Path(dest).parent.mkdir(parents=True, exist_ok=True)
    Path(dest).write_text(json.dumps(scale), encoding="utf-8")
    logging.info(dest)


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
