from __future__ import annotations

import sys

from datavizhub.visualization.cli_utils import features_from_ns
from datavizhub.utils.cli_helpers import configure_logging_from_env
import logging


def handle_animate(ns) -> int:
    """Handle ``visualize animate`` CLI subcommand."""
    configure_logging_from_env()
    if ns.mode == "particles":
        from datavizhub.visualization.vector_particles_manager import VectorParticlesManager
        from datavizhub.processing.video_processor import VideoProcessor

        mgr = VectorParticlesManager(basemap=ns.basemap, extent=ns.extent)
        manifest = mgr.render(
            input_path=ns.input,
            uvar=ns.uvar,
            vvar=ns.vvar,
            u=ns.u,
            v=ns.v,
            seed=ns.seed,
            particles=ns.particles,
            custom_seed=ns.custom_seed,
            dt=ns.dt,
            steps_per_frame=ns.steps_per_frame,
            method=ns.method,
            color=ns.color,
            size=ns.size,
            width=ns.width,
            height=ns.height,
            dpi=ns.dpi,
            # CRS handling
            crs=getattr(ns, "crs", None),
            reproject=getattr(ns, "reproject", False),
            output_dir=ns.output_dir,
        )
        out = mgr.save(ns.manifest)
        if out:
            logging.info(out)
        if ns.to_video:
            frames_dir = ns.output_dir
            vp = VideoProcessor(input_directory=frames_dir, output_file=ns.to_video, fps=ns.fps)
            if not vp.validate():
                logging.warning("ffmpeg/ffprobe not available; skipping video composition")
            else:
                vp.process(fps=ns.fps)
                vp.save(ns.to_video)
                logging.info(ns.to_video)
        return 0

    from datavizhub.visualization.animate_manager import AnimateManager
    from datavizhub.processing.video_processor import VideoProcessor

    mgr = AnimateManager(mode=ns.mode, basemap=ns.basemap, extent=ns.extent, output_dir=ns.output_dir)
    features = features_from_ns(ns)
    manifest = mgr.render(
        input_path=ns.input,
        var=ns.var,
        mode=ns.mode,
        cmap=ns.cmap,
        levels=ns.levels,
        vmin=ns.vmin,
        vmax=ns.vmax,
        width=ns.width,
        height=ns.height,
        dpi=ns.dpi,
        output_dir=ns.output_dir,
        colorbar=getattr(ns, "colorbar", False),
        label=getattr(ns, "label", None),
        units=getattr(ns, "units", None),
        show_timestamp=getattr(ns, "show_timestamp", False),
        timestamps_csv=getattr(ns, "timestamps_csv", None),
        timestamp_loc=getattr(ns, "timestamp_loc", "lower_right"),
        # Vector-specific config
        u=ns.u,
        v=ns.v,
        uvar=ns.uvar,
        vvar=ns.vvar,
        density=getattr(ns, "density", 0.2),
        scale=getattr(ns, "scale", None),
        color=getattr(ns, "color", "#333333"),
        features=features,
        map_type=getattr(ns, "map_type", "image"),
        tile_source=getattr(ns, "tile_source", None),
        tile_zoom=getattr(ns, "tile_zoom", 3),
        # CRS
        crs=getattr(ns, "crs", None),
        reproject=getattr(ns, "reproject", False),
    )
    out = mgr.save(ns.manifest)
    if out:
        logging.info(out)
    if ns.to_video:
        frames_dir = ns.output_dir
        vp = VideoProcessor(input_directory=frames_dir, output_file=ns.to_video, fps=ns.fps)
        if not vp.validate():
            logging.warning("ffmpeg/ffprobe not available; skipping video composition")
        else:
            vp.process(fps=ns.fps)
            vp.save(ns.to_video)
            logging.info(ns.to_video)
    return 0
