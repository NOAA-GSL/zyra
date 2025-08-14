from __future__ import annotations

import sys

from datavizhub.processing.video_processor import VideoProcessor
from datavizhub.utils.cli_helpers import configure_logging_from_env
import logging


def handle_compose_video(ns) -> int:
    """Handle ``visualize compose-video`` CLI subcommand."""
    configure_logging_from_env()
    vp = VideoProcessor(input_directory=ns.frames, output_file=ns.output, basemap=getattr(ns, "basemap", None), fps=ns.fps)
    if not vp.validate():
        logging.warning("ffmpeg/ffprobe not available; skipping video composition")
        return 0
    vp.process(fps=ns.fps)
    vp.save(ns.output)
    logging.info(ns.output)
    return 0
