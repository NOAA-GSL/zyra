# SPDX-License-Identifier: Apache-2.0
"""CLI handler for the ``visualize sos`` (Science On a Sphere) subcommand.

This wires :class:`zyra.visualization.plot_manager.PlotManager` to the CLI so
that gridded data can be rendered as Science On a Sphere (SOS) frames. SOS
frames are full-globe, PlateCarree, 2:1, edge-to-edge images. A fixed color
range (``--vmin``/``--vmax``) keeps the color scaling identical across every
frame in a sequence, which avoids the flicker that results from per-frame
self-scaling.

Both single-input (``--input``/``--output``) and batch (``--inputs``/
``--output-dir``) rendering are supported so that frame sequences for an
animation can be produced in one invocation.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from zyra.utils.cli_helpers import configure_logging_from_env
from zyra.visualization.cli_utils import (
    load_data_array,
    resolve_basemap_ref,
    resolve_extent,
)


def _render_one(
    ns,
    src: str,
    dest: str,
) -> str | None:
    """Render a single SOS frame from ``src`` to ``dest``.

    Returns the output path on success, or ``None`` on failure.
    """
    from zyra.visualization.plot_manager import PlotManager

    arr = load_data_array(
        src,
        var=getattr(ns, "var", None),
        xarray_engine=getattr(ns, "xarray_engine", None),
    )
    # Treat NaN/inf as transparent so missing data does not skew the rendering.
    import numpy as np

    arr = np.ma.masked_invalid(arr)

    bmap, guard = resolve_basemap_ref(getattr(ns, "basemap", None))
    try:
        pm = PlotManager(basemap=bmap, image_extent=ns.extent, base_cmap=ns.cmap)
        return pm.sos_plot_data(
            arr,
            custom_cmap=ns.cmap,
            output_path=dest,
            width=ns.width,
            height=ns.height,
            dpi=ns.dpi,
            flip_data=bool(getattr(ns, "flip", False)),
            vmin=getattr(ns, "vmin", None),
            vmax=getattr(ns, "vmax", None),
        )
    finally:
        if guard is not None:
            try:
                guard.close()
            except Exception:
                pass


def handle_sos(ns) -> int:
    """Handle the ``visualize sos`` CLI subcommand.

    Renders one or more gridded inputs as Science On a Sphere frames using
    :class:`PlotManager`, with a fixed ``--vmin``/``--vmax`` color range for
    flicker-free frame sequences.

    Argument errors surface as a clean logged error with exit code 2
    instead of a bare exit 1 — the same contract
    ``handle_heatmap``/``handle_contour`` use. Render failures keep
    raising ``SystemExit`` deliberately, so a pipeline never treats an
    empty or failed render as success.
    """
    try:
        return _handle_sos_impl(ns)
    except ValueError as exc:
        logging.error(str(exc))
        return 2


def _handle_sos_impl(ns) -> int:
    if getattr(ns, "verbose", False):
        os.environ["ZYRA_VERBOSITY"] = "debug"
    elif getattr(ns, "quiet", False):
        os.environ["ZYRA_VERBOSITY"] = "quiet"
    if getattr(ns, "trace", False):
        os.environ["ZYRA_SHELL_TRACE"] = "1"
    configure_logging_from_env()

    # Normalize/validate --extent so both the CLI spelling (--extent w e s n)
    # and the Domain API's repeated-flag expansion resolve consistently, and
    # the full-globe default is applied when unset.
    ns.extent = resolve_extent(ns)

    # Batch mode: --inputs with --output-dir
    if getattr(ns, "inputs", None):
        outdir = getattr(ns, "output_dir", None)
        if not outdir:
            raise ValueError("--output-dir is required when using --inputs")
        outdir_p = Path(outdir)
        outdir_p.mkdir(parents=True, exist_ok=True)
        outputs: list[str] = []
        failures: list[str] = []
        for src in ns.inputs:
            dest = outdir_p / f"{Path(str(src)).stem}.png"
            out = _render_one(ns, src, str(dest))
            if out:
                logging.info(out)
                outputs.append(out)
            else:
                failures.append(str(src))
        try:
            print(json.dumps({"outputs": outputs}))
        except Exception:
            pass
        # Surface render failures as a non-zero exit so that `zyra run`
        # pipelines do not treat a failed/empty render as success.
        if failures:
            raise SystemExit(
                f"Failed to render {len(failures)} SOS frame(s): {', '.join(failures)}"
            )
        return 0

    # Single input mode
    if not getattr(ns, "input", None):
        raise ValueError("--input or --inputs is required")
    if not getattr(ns, "output", None):
        raise ValueError("--output is required when using --input")
    out = _render_one(ns, ns.input, ns.output)
    if not out:
        raise SystemExit(f"Failed to render SOS frame from {ns.input}")
    logging.info(out)
    return 0


def register_sos_cli(subparsers: Any) -> None:
    """Register the ``sos`` subcommand on a provided subparsers object.

    Shared by both the CLI registration path
    (:func:`zyra.visualization.cli_register.register_cli`) and the API manifest
    path (:func:`zyra.visualization.register_cli`) to keep the parser definition
    in a single place.
    """
    p_sos = subparsers.add_parser(
        "sos",
        help="Visualization: render Science On a Sphere frames",
        description=(
            "Render gridded data as Science On a Sphere (SOS) frames: full-globe, "
            "PlateCarree, 2:1, edge-to-edge PNGs. Use a fixed --vmin/--vmax range to "
            "keep color scaling identical across a frame sequence (flicker-free). "
            "Supports single (--input/--output) and batch (--inputs/--output-dir) modes."
        ),
    )
    p_sos.add_argument("--input", help="Path to .nc or .npy input")
    p_sos.add_argument(
        # action="extend" on --inputs so both arg-expansion styles work:
        # the pipeline runner emits `--inputs a b c` while the Domain API
        # executor emits repeated `--inputs a --inputs b`. Plain nargs="+"
        # keeps only the last of those, silently dropping every earlier
        # input. Same reason --bounds/--extent use it.
        "--inputs",
        nargs="+",
        action="extend",
        help="Multiple input paths for batch rendering",
    )
    p_sos.add_argument("--var", help="Variable name for NetCDF inputs")
    p_sos.add_argument(
        "--output",
        help="Output PNG path (required when using --input)",
    )
    p_sos.add_argument(
        "--output-dir",
        dest="output_dir",
        help="Directory to write outputs (required when using --inputs)",
    )
    p_sos.add_argument(
        "--basemap",
        help="Optional basemap (path, bare image name, or pkg:ref) drawn under the data",
    )
    # extent flags use action="extend" with default=None: the Domain API
    # runner expands list args as repeated flags (--extent w --extent e ...)
    # which nargs=4 cannot parse, and argparse's extend action appends to
    # a list default. handle_sos applies the full-globe default and
    # validates length via cli_utils.resolve_extent.
    p_sos.add_argument(
        "--extent",
        nargs="+",
        type=float,
        action="extend",
        default=None,
        help="west east south north (default: global -180 180 -90 90)",
    )
    p_sos.add_argument("--width", type=int, default=4096, help="Output width (px)")
    p_sos.add_argument("--height", type=int, default=2048, help="Output height (px)")
    p_sos.add_argument("--dpi", type=int, default=96)
    p_sos.add_argument("--cmap", default="YlOrBr", help="Colormap name")
    p_sos.add_argument(
        "--vmin",
        type=float,
        help="Fixed minimum data value for color scaling (recommended for sequences)",
    )
    p_sos.add_argument(
        "--vmax",
        type=float,
        help="Fixed maximum data value for color scaling (recommended for sequences)",
    )
    p_sos.add_argument(
        "--flip",
        action="store_true",
        help="Flip data vertically before rendering (for north-up grids)",
    )
    p_sos.add_argument(
        "--xarray-engine",
        dest="xarray_engine",
        help="xarray engine for NetCDF inputs (e.g., netcdf4, h5netcdf, scipy)",
    )
    p_sos.add_argument(
        "--verbose", action="store_true", help="Verbose logging for this command"
    )
    p_sos.add_argument(
        "--quiet", action="store_true", help="Quiet logging for this command"
    )
    p_sos.add_argument(
        "--trace",
        action="store_true",
        help="Shell-style trace of key steps and external commands",
    )
    p_sos.set_defaults(func=handle_sos)
