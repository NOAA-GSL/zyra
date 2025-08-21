from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from zyra.utils.cli_helpers import configure_logging_from_env
from zyra.visualization.cli_utils import features_from_ns


def handle_animate(ns) -> int:
    """Handle ``visualize animate`` CLI subcommand."""
    configure_logging_from_env()
    # Batch mode for animate: --inputs with --output-dir
    if getattr(ns, "inputs", None):
        if not ns.output_dir:
            raise SystemExit("--output-dir is required when using --inputs")
        from zyra.processing.video_processor import VideoProcessor
        from zyra.visualization.animate_manager import AnimateManager

        outdir = Path(ns.output_dir)
        outdir.mkdir(parents=True, exist_ok=True)
        features = features_from_ns(ns)
        videos = []
        for src in ns.inputs:
            base = Path(str(src)).stem
            frames_dir = outdir / base
            mgr = AnimateManager(
                mode=ns.mode,
                basemap=ns.basemap,
                extent=ns.extent,
                output_dir=str(frames_dir),
            )
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
                vp = VideoProcessor(
                    input_directory=str(frames_dir), output_file=str(mp4), fps=ns.fps
                )
                if vp.validate():
                    vp.process(fps=ns.fps)
                    vp.save(str(mp4))
                    videos.append(str(mp4))
        # Optional: combine grid
        if getattr(ns, "combine_to", None) and videos:
            cols = int(getattr(ns, "grid_cols", 2) or 2)
            try:
                cmd = _build_ffmpeg_grid_args(
                    videos=videos,
                    fps=int(ns.fps),
                    output=str(ns.combine_to),
                    grid_mode=str(getattr(ns, "grid_mode", "grid")),
                    cols=cols,
                )
                subprocess.run(cmd, check=False)
                logging.info(ns.combine_to)
            except Exception as err:
                logging.warning("Failed to compose grid video")
                raise SystemExit("ffmpeg grid composition failed") from err
        return 0
    if ns.mode == "particles":
        from zyra.processing.video_processor import VideoProcessor
        from zyra.visualization.vector_particles_manager import (
            VectorParticlesManager,
        )

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
            # Validate and normalize output file path
            to_video = str(ns.to_video).strip()
            if to_video.startswith("-"):
                raise SystemExit(
                    "--to-video cannot start with '-' (may be interpreted as an option)"
                )
            out_path = Path(to_video).expanduser().resolve()
            from zyra.utils.env import env

            safe_root = env("SAFE_OUTPUT_ROOT")
            if safe_root:
                try:
                    _ = out_path.resolve().relative_to(
                        Path(safe_root).expanduser().resolve()
                    )
                except Exception as err:
                    raise SystemExit(
                        "--to-video is outside of allowed output root"
                    ) from err
            vp = VideoProcessor(
                input_directory=frames_dir, output_file=str(out_path), fps=ns.fps
            )
            if not vp.validate():
                logging.warning(
                    "ffmpeg/ffprobe not available; skipping video composition"
                )
            else:
                vp.process(fps=ns.fps)
                vp.save(str(out_path))
                logging.info(str(out_path))
        return 0

    from zyra.processing.video_processor import VideoProcessor
    from zyra.visualization.animate_manager import AnimateManager

    mgr = AnimateManager(
        mode=ns.mode, basemap=ns.basemap, extent=ns.extent, output_dir=ns.output_dir
    )
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
        to_video = str(ns.to_video).strip()
        if to_video.startswith("-"):
            raise SystemExit(
                "--to-video cannot start with '-' (may be interpreted as an option)"
            )
        out_path = Path(to_video).expanduser().resolve()
        from zyra.utils.env import env

        safe_root = env("SAFE_OUTPUT_ROOT")
        if safe_root:
            try:
                _ = out_path.resolve().relative_to(
                    Path(safe_root).expanduser().resolve()
                )
            except Exception as err:
                raise SystemExit(
                    "--to-video is outside of allowed output root"
                ) from err
        vp = VideoProcessor(
            input_directory=frames_dir, output_file=str(out_path), fps=ns.fps
        )
        if not vp.validate():
            logging.warning("ffmpeg/ffprobe not available; skipping video composition")
        else:
            vp.process(fps=ns.fps)
            vp.save(str(out_path))
            logging.info(str(out_path))
    return 0


def _build_ffmpeg_grid_args(
    *, videos: list[str], fps: int, output: str, grid_mode: str, cols: int
) -> list[str]:
    """Build a safe ffmpeg command args list to compose multiple MP4s.

    - grid_mode 'grid' uses xstack with positions derived from first input size (w0,h0)
    - grid_mode 'hstack' composes horizontally with hstack
    - Returns a list of arguments suitable for subprocess.run without shell=True
    """
    if not videos:
        raise ValueError("No input videos provided")
    if cols <= 0:
        raise ValueError("cols must be >= 1")
    if not isinstance(fps, int) or fps <= 0:
        raise ValueError("fps must be a positive integer")
    if not isinstance(output, str) or not output.strip():
        raise ValueError("output must be a non-empty string path")
    if output.lstrip().startswith("-"):
        # Prevent ffmpeg from interpreting output as an option
        raise ValueError(
            "output filename cannot start with '-' (may be interpreted as an option)"
        )
    out_path = Path(output).expanduser().resolve()
    from zyra.utils.env import env

    safe_root = env("SAFE_OUTPUT_ROOT")
    if safe_root:
        try:
            _ = out_path.resolve().relative_to(Path(safe_root).expanduser().resolve())
        except Exception as err:
            raise ValueError("output is outside of allowed output root") from err
    if out_path.parent:
        out_path.parent.mkdir(parents=True, exist_ok=True)
    args: list[str] = ["ffmpeg"]
    for v in videos:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("invalid input video path")
        if v.lstrip().startswith("-"):
            # Prevent ffmpeg from interpreting a bare input path as an option value
            raise ValueError(
                "input video path cannot start with '-' (may be interpreted as an option)"
            )
        # Resolve and ensure it's a file to reduce the chance of injecting options via paths
        vp = Path(v).expanduser().resolve()
        if vp.name.startswith("-"):
            raise ValueError(
                "input video basename cannot start with '-' (may be interpreted as an option)"
            )
        if not vp.is_file():
            raise ValueError(f"input video not found: {vp}")
        args.extend(["-i", str(vp)])
    if grid_mode == "hstack":
        filter_desc = f"hstack=inputs={len(videos)}"
    else:
        # Build xstack layout using first input dimensions (w0,h0) as tile size.
        layout_entries: list[str] = []
        for idx in range(len(videos)):
            r = idx // cols
            c = idx % cols
            x = "0" if c == 0 else f"w0*{c}"
            y = "0" if r == 0 else f"h0*{r}"
            layout_entries.append(f"{x}_{y}")
        filter_desc = f"xstack=inputs={len(videos)}:layout=" + "|".join(layout_entries)
    args.extend(
        [
            "-filter_complex",
            filter_desc,
            "-r",
            str(fps),
            "-vcodec",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-y",
            str(out_path),
        ]
    )
    return args
