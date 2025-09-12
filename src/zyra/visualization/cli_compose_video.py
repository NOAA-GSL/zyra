# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional  # noqa: F401  (kept for type hints in signatures)

from zyra.utils.cli_helpers import configure_logging_from_env
from zyra.visualization.cli_utils import resolve_basemap_ref


def handle_compose_video(ns) -> int:
    """Handle ``visualize compose-video`` CLI subcommand."""
    # Map per-command verbosity to env before configuring logging
    if getattr(ns, "verbose", False):
        os.environ["ZYRA_VERBOSITY"] = "debug"
    elif getattr(ns, "quiet", False):
        os.environ["ZYRA_VERBOSITY"] = "quiet"
    if getattr(ns, "trace", False):
        os.environ["ZYRA_SHELL_TRACE"] = "1"
    configure_logging_from_env()
    # Lazy import to avoid pulling ffmpeg dependencies unless needed
    from zyra.processing.video_processor import VideoProcessor

    out = str(ns.output).strip()
    if out.startswith("-"):
        raise SystemExit(
            "--output cannot start with '-' (may be interpreted as an option)"
        )
    out_path = Path(out).expanduser().resolve()
    from zyra.utils.env import env

    safe_root = env("SAFE_OUTPUT_ROOT")
    if safe_root:
        try:
            _ = out_path.resolve().relative_to(Path(safe_root).expanduser().resolve())
        except Exception as err:
            raise SystemExit("--output is outside of allowed output root") from err
    # Pre-flight: frames directory must exist and contain at least one image
    frames_dir = Path(ns.frames).expanduser()
    if not frames_dir.exists() or not frames_dir.is_dir():
        raise SystemExit(f"Frames directory not found: {frames_dir}")
    try:
        exts = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".dds"}
        if getattr(ns, "glob", None):
            has_images = any(frames_dir.glob(ns.glob))
        else:
            has_images = any(
                f.is_file() and f.suffix.lower() in exts for f in frames_dir.iterdir()
            )
    except Exception:
        has_images = False
    if not has_images:
        logging.error(
            "No frame images found in %s (expected extensions: %s)",
            str(frames_dir),
            ", ".join(sorted(exts)),
        )
        return 2

    # Ensure the output directory exists
    try:
        if out_path.parent and not out_path.parent.exists():
            out_path.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        # Defer to VideoProcessor/ffmpeg errors if directory cannot be created
        pass

    # Resolve optional basemap reference. Accept the following forms:
    #   - Absolute/relative filesystem path (unchanged)
    #   - Bare filename present under zyra.assets/images (e.g., "earth_vegetation.jpg")
    #   - Packaged reference: "pkg:package/resource" (e.g., pkg:zyra.assets/images/earth_vegetation.jpg)
    basemap_path, basemap_guard = resolve_basemap_ref(getattr(ns, "basemap", None))

    vp = VideoProcessor(
        input_directory=ns.frames,
        output_file=str(out_path),
        basemap=basemap_path,
        fps=ns.fps,
        input_glob=getattr(ns, "glob", None),
    )
    # Emit set -x style trace context
    if os.environ.get("ZYRA_SHELL_TRACE"):
        logging.info("+ cwd='%s'", str(Path.cwd()))
        logging.info("+ frames_dir='%s'", str(frames_dir))
        if getattr(ns, "glob", None):
            logging.info("+ glob='%s'", str(ns.glob))
        if basemap_path:
            logging.info("+ basemap='%s'", basemap_path)
    if not vp.validate():
        logging.warning("ffmpeg/ffprobe not available; skipping video composition")
        return 0
    try:
        result = vp.process(fps=ns.fps)
    finally:
        if basemap_guard is not None:
            try:
                basemap_guard.close()
            except Exception:
                pass
    if not result:
        logging.error(
            "Video composition failed; see debug logs above for ffmpeg output"
        )
        return 2
    vp.save(str(out_path))
    logging.info(str(out_path))
    return 0
