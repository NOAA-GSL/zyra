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

    vp = VideoProcessor(
        input_directory=ns.frames,
        output_file=str(out_path),
        basemap=getattr(ns, "basemap", None),
        fps=ns.fps,
        input_glob=getattr(ns, "glob", None),
    )
    if not vp.validate():
        logging.warning("ffmpeg/ffprobe not available; skipping video composition")
        return 0
    vp.process(fps=ns.fps)
    vp.save(str(out_path))
    logging.info(str(out_path))
    return 0
