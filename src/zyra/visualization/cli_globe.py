# SPDX-License-Identifier: Apache-2.0
"""CLI handler for interactive globe renderers."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from zyra.utils.cli_helpers import configure_logging_from_env
from zyra.visualization.renderers import available, create


def _renderer_options(ns: Any) -> dict[str, Any]:
    """Translate argparse namespace into renderer keyword options."""

    options: dict[str, Any] = {
        "animate": ns.animate,
        "probe_enabled": ns.probe,
    }
    if ns.width is not None:
        options["width"] = ns.width
    if ns.height is not None:
        options["height"] = ns.height
    if ns.texture:
        options["texture"] = ns.texture
    if ns.texture_pattern:
        options["texture_pattern"] = ns.texture_pattern
    if ns.frame_list:
        options["frame_list"] = ns.frame_list
    if ns.frame_cache:
        options["frame_cache"] = ns.frame_cache
    if ns.probe_gradient:
        options["probe_gradient"] = ns.probe_gradient
    if ns.probe_lut:
        options["probe_lut"] = ns.probe_lut
    if ns.legend_texture:
        options["legend_texture"] = ns.legend_texture
    if ns.shared_gradient:
        options["shared_gradient"] = ns.shared_gradient
    if ns.time_key:
        options["time_key"] = ns.time_key
    if ns.time_format:
        options["time_format"] = ns.time_format
    if ns.credential:
        options["credentials"] = list(ns.credential)
    if ns.credential_file:
        options["credential_file"] = ns.credential_file
    if ns.auth:
        options["auth"] = ns.auth
    return options


def handle_globe(ns: Any) -> int:
    """Handle ``visualize globe`` subcommand."""

    if getattr(ns, "verbose", False):
        os.environ["ZYRA_VERBOSITY"] = "debug"
    elif getattr(ns, "quiet", False):
        os.environ["ZYRA_VERBOSITY"] = "quiet"
    if getattr(ns, "trace", False):
        os.environ["ZYRA_SHELL_TRACE"] = "1"

    configure_logging_from_env()

    renderer_slugs = sorted(r.slug for r in available())
    if ns.target not in renderer_slugs:
        raise SystemExit(
            f"Unknown globe renderer '{ns.target}'. Available: {', '.join(renderer_slugs)}"
        )

    renderer = create(ns.target, **_renderer_options(ns))
    bundle = renderer.build(output_dir=Path(ns.output))

    logging.info("Generated globe bundle at %s", bundle.index_html)
    if bundle.assets:
        logging.debug(
            "Bundle assets: %s",
            ", ".join(
                str(path.relative_to(bundle.output_dir)) for path in bundle.assets
            ),
        )
    return 0
