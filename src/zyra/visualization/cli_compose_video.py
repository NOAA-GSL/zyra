from __future__ import annotations

import logging
from pathlib import Path

from zyra.utils.cli_helpers import configure_logging_from_env


def handle_compose_video(ns) -> int:
    """Handle ``visualize compose-video`` CLI subcommand."""
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
    vp = VideoProcessor(
        input_directory=ns.frames,
        output_file=str(out_path),
        basemap=getattr(ns, "basemap", None),
        fps=ns.fps,
    )
    if not vp.validate():
        logging.warning("ffmpeg/ffprobe not available; skipping video composition")
        return 0
    vp.process(fps=ns.fps)
    vp.save(str(out_path))
    logging.info(str(out_path))
    return 0
