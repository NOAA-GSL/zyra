from __future__ import annotations

import sys

from datavizhub.visualization.cli_utils import features_from_ns
from pathlib import Path
import subprocess, shlex
from datavizhub.utils.cli_helpers import configure_logging_from_env
import logging


def handle_animate(ns) -> int:
    """Handle ``visualize animate`` CLI subcommand."""
    configure_logging_from_env()
    # Batch mode for animate: --inputs with --output-dir
    if getattr(ns, 'inputs', None):
        if not ns.output_dir:
            raise SystemExit("--output-dir is required when using --inputs")
        from datavizhub.visualization.animate_manager import AnimateManager
        from datavizhub.processing.video_processor import VideoProcessor
        outdir = Path(ns.output_dir); outdir.mkdir(parents=True, exist_ok=True)
        features = features_from_ns(ns)
        videos = []
        for src in ns.inputs:
            base = Path(str(src)).stem
            frames_dir = outdir / base
            mgr = AnimateManager(mode=ns.mode, basemap=ns.basemap, extent=ns.extent, output_dir=str(frames_dir))
            mgr.render(
                input_path=src,
                var=ns.var,
                mode=ns.mode,
                xarray_engine=getattr(ns, "xarray_engine", None),
                cmap=ns.cmap,
                levels=ns.levels,
                vmin=ns.vmin,
                vmax=ns.vmax,
                width=ns.width,
                height=ns.height,
                dpi=ns.dpi,
                output_dir=str(frames_dir),
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
            if ns.to_video:
                mp4 = outdir / f"{base}.mp4"
                vp = VideoProcessor(input_directory=str(frames_dir), output_file=str(mp4), fps=ns.fps)
                if vp.validate():
                    vp.process(fps=ns.fps)
                    vp.save(str(mp4))
                    videos.append(str(mp4))
        # Optional: combine grid
        if getattr(ns, 'combine_to', None) and videos:
            cols = int(getattr(ns, 'grid_cols', 2) or 2)
            rows = (len(videos) + cols - 1) // cols
            # ffmpeg xstack grid
            # Build inputs
            inputs = " ".join(f"-i {shlex.quote(v)}" for v in videos)
            filter_desc = f"xstack=inputs={len(videos)}:layout="
            # layout positions
            layout = []
            for idx in range(len(videos)):
                r = idx // cols
                c = idx % cols
                layout.append(f"w{c}*{c}|h{r}*{r}")
            # Simpler: zero-offset tiled; assume same dimensions, ffmpeg xstack default arranges by tile=colsxrows
            filter_desc = f"xstack=inputs={len(videos)}:layout=0_0|w0_0|0_h0|w0_h0"
            # For >4 videos, fallback to simple horizontal stack (best effort)
            if len(videos) > 4:
                filter_desc = f"hstack=inputs={len(videos)}"
            cmd = f"ffmpeg {inputs} -filter_complex {shlex.quote(filter_desc)} -r {ns.fps} -vcodec libx264 -pix_fmt yuv420p -y {shlex.quote(ns.combine_to)}"
            try:
                subprocess.run(shlex.split(cmd), check=False)
                logging.info(ns.combine_to)
            except Exception:
                logging.warning("Failed to compose grid video")
        return 0
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
        xarray_engine=getattr(ns, "xarray_engine", None),
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
