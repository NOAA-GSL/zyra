# SPDX-License-Identifier: Apache-2.0
"""Helpers that back the ``zyra process video-transcode`` CLI command.

The helper functions in this module wrap FFmpeg/FFprobe so that callers can
transcode modern video assets into legacy SOS formats (and vice versa).  The
entry point ``run_video_transcode`` is designed for the CLI wiring in
``zyra.processing.__init__`` but the rich docstrings also enable Sphinx
autodoc coverage for downstream consumers.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shlex
import shutil
import string
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import Any, Iterable, Sequence

from zyra.utils.cli_helpers import sanitize_for_log


def normalise_extra_args(raw: Sequence[str] | None) -> list[str]:
    """Split repeatable ``--extra-args`` chunks into individual FFmpeg flags."""

    parsed: list[str] = []
    for chunk in raw or []:
        if chunk:
            parsed.extend(shlex.split(chunk))
    return parsed


class VideoTranscodeError(RuntimeError):
    """Raised when FFmpeg or FFprobe encounters an unrecoverable issue."""


@dataclass(slots=True)
class VideoTranscodeConfig:
    """Container for CLI options that control a transcoding run."""

    input_spec: str
    output: Path | None
    container: str
    codec: str
    audio_codec: str | None
    audio_bitrate: str | None
    scale: str | None
    fps: float | None
    bitrate: str
    pix_fmt: str
    preset: str | None
    crf: int | None
    gop: int | None
    extra_args: list[str]
    metadata_requested: bool
    metadata_out: Path | None
    sos_legacy: bool
    no_overwrite: bool


@dataclass(slots=True)
class TranscodeTask:
    """Represents a single FFmpeg invocation."""

    input_arg: str
    output_path: Path
    is_sequence: bool


@dataclass(slots=True)
class TranscodeResult:
    """Result of a completed FFmpeg invocation."""

    source: str
    output: Path
    metadata: dict[str, Any] | None


class VideoTranscoder:
    """Orchestrates one or more FFmpeg invocations for the CLI.

    Parameters
    ----------
    config:
        Normalised CLI configuration that defines codecs, bitrate, metadata
        capture, and positional inputs.
    """

    DEFAULT_CONTAINER_EXT = {
        "mp4": ".mp4",
        "webm": ".webm",
        "mov": ".mov",
        "mpg": ".mpg",
    }
    DEFAULT_CODECS = {
        "mp4": "h264",
        "webm": "vp9",
        "mov": "h264",
        "mpg": "mpeg2video",
    }
    DEFAULT_AUDIO_CODECS = {
        "mp4": "aac",
        "webm": "opus",
        "mov": "aac",
        "mpg": "mp2",
    }

    def __init__(self, config: VideoTranscodeConfig):
        self.config = config
        self.ffmpeg_path = self._resolve_binary("ffmpeg", "ZYRA_FFMPEG_PATH")
        if not self.ffmpeg_path:
            raise VideoTranscodeError(
                "ffmpeg binary not found in PATH. Install FFmpeg to use video-transcode."
            )
        self.ffprobe_path = self._resolve_binary("ffprobe", "ZYRA_FFPROBE_PATH")

    # -- public API -----------------------------------------------------------------
    def run(self) -> list[TranscodeResult]:
        """Execute FFmpeg for each derivable task and return metadata results."""

        tasks = self._build_tasks()
        results: list[TranscodeResult] = []
        for task in tasks:
            results.append(self._run_single(task))
        return results

    # -- helper plumbing ------------------------------------------------------------
    @staticmethod
    def from_namespace(args: Any) -> VideoTranscodeConfig:
        """Construct a config from an argparse namespace."""

        container = getattr(args, "container", "mp4")
        codec_arg = getattr(args, "codec", None)
        sos_legacy = bool(getattr(args, "sos_legacy", False))
        bitrate_arg = getattr(args, "bitrate", None)
        pix_fmt_arg = getattr(args, "pix_fmt", None)
        fps = getattr(args, "fps", None)
        audio_codec_arg = getattr(args, "audio_codec", None)
        metadata_requested = bool(
            getattr(args, "write_metadata", False)
            or getattr(args, "metadata_out", None)
            or getattr(args, "verbose", False)
        )
        codec = codec_arg or VideoTranscoder.DEFAULT_CODECS.get(container, "h264")
        audio_codec = audio_codec_arg or VideoTranscoder.DEFAULT_AUDIO_CODECS.get(
            container
        )
        bitrate = bitrate_arg or "8M"
        pix_fmt = pix_fmt_arg or "yuv420p"
        if sos_legacy:
            if codec_arg is None:
                codec = "libxvid"
            if audio_codec_arg is None:
                audio_codec = "mp2"
            if fps is None:
                fps = 30.0
            if bitrate_arg is None:
                bitrate = "25M"
            if pix_fmt_arg is None:
                pix_fmt = "yuv420p"
            if container == "mpg":
                if codec_arg is None:
                    logging.warning(
                        "SOS legacy preset normally emits .mp4 files. Received --to mpg;"
                        " defaulting codec to mpeg2video for MPEG-2 compatibility. Use"
                        " --codec to override if you truly need a different payload."
                    )
                    codec = "mpeg2video"
                else:
                    logging.warning(
                        "SOS legacy preset normally emits .mp4 files. Received --to mpg with"
                        " explicit codec '%s'; ensure the display expects that combination."
                        " Consider sticking with .mp4 for libxvid playlists or switching to"
                        " --codec mpeg2video for standard MPEG-2.",
                        codec_arg,
                    )
        metadata_out = getattr(args, "metadata_out", None)
        metadata_path = Path(metadata_out) if metadata_out else None
        output = getattr(args, "output", None)
        output_path = Path(output) if output else None
        extra_args = normalise_extra_args(getattr(args, "extra_args", None))
        return VideoTranscodeConfig(
            input_spec=args.input,
            output=output_path,
            container=container,
            codec=codec,
            audio_codec=audio_codec,
            audio_bitrate=getattr(args, "audio_bitrate", None),
            scale=getattr(args, "scale", None),
            fps=fps,
            bitrate=bitrate,
            pix_fmt=pix_fmt,
            preset=getattr(args, "preset", None),
            crf=getattr(args, "crf", None),
            gop=getattr(args, "gop", None),
            extra_args=extra_args,
            metadata_requested=metadata_requested,
            metadata_out=metadata_path,
            sos_legacy=sos_legacy,
            no_overwrite=bool(getattr(args, "no_overwrite", False)),
        )

    # -- private helpers ------------------------------------------------------------
    @staticmethod
    def _resolve_binary(cmd: str, env_var: str) -> str | None:
        override = os.environ.get(env_var)
        if override:
            return override
        return shutil.which(cmd)

    def _build_tasks(self) -> list[TranscodeTask]:
        spec = self.config.input_spec
        if _looks_like_sequence(spec):
            return [self._build_sequence_task(spec)]
        path = Path(spec)
        if path.is_dir():
            inputs = sorted(p for p in path.iterdir() if p.is_file())
            if not inputs:
                raise VideoTranscodeError(
                    f"No files found in input directory '{path}'."
                )
            return self._build_batch_tasks(inputs, root=path)
        if path.is_file():
            return [self._build_file_task(path)]
        matches = sorted(Path(p) for p in _expand_glob(spec))
        if matches:
            return self._build_batch_tasks(matches)
        raise VideoTranscodeError(
            f"Input '{spec}' not found or pattern resolved empty."
        )

    def _build_file_task(
        self, input_path: Path, root: Path | None = None
    ) -> TranscodeTask:
        output = self._resolve_output_for_file(input_path, root=root)
        return TranscodeTask(str(input_path), output, False)

    def _build_batch_tasks(
        self, inputs: Sequence[Path], root: Path | None = None
    ) -> list[TranscodeTask]:
        out_arg = self.config.output
        if out_arg and out_arg.suffix:
            raise VideoTranscodeError(
                "For batch transcoding provide --output as a directory path."
            )
        resolved_root = root
        pattern_root = _pattern_root(self.config.input_spec)
        if resolved_root is None:
            resolved_root = _common_root(inputs)
            if pattern_root is not None and (resolved_root is None or len(inputs) == 1):
                resolved_root = pattern_root
        if resolved_root is None:
            resolved_root = pattern_root
        results: list[TranscodeTask] = []
        for inp in inputs:
            results.append(self._build_file_task(inp, root=resolved_root))
        return results

    def _build_sequence_task(self, pattern: str) -> TranscodeTask:
        parent = Path(pattern).parent
        if not parent.exists():
            raise VideoTranscodeError(
                f"Sequence directory '{parent}' does not exist for pattern '{pattern}'."
            )
        default_name = _default_sequence_basename(Path(pattern).stem)
        output = self._resolve_output_for_sequence(parent, default_name)
        return TranscodeTask(pattern, output, True)

    def _resolve_output_for_file(
        self, input_path: Path, root: Path | None = None
    ) -> Path:
        ext = self._extension
        out_arg = self.config.output
        if out_arg:
            if out_arg.suffix:
                out_arg.parent.mkdir(parents=True, exist_ok=True)
                return out_arg
            out_dir = out_arg
            out_dir.mkdir(parents=True, exist_ok=True)
            if root and _is_relative_to(input_path, root):
                relative = input_path.relative_to(root)
            else:
                relative = Path(input_path.name)
            target = (out_dir / relative).with_suffix(ext)
            target.parent.mkdir(parents=True, exist_ok=True)
            return target
        return input_path.with_suffix(ext)

    def _resolve_output_for_sequence(self, parent: Path, basename: str) -> Path:
        ext = self._extension
        filename = f"{basename}{ext}"
        out_arg = self.config.output
        if out_arg:
            if out_arg.exists() and out_arg.is_dir():
                return out_arg / filename
            if out_arg.suffix:
                out_arg.parent.mkdir(parents=True, exist_ok=True)
                return out_arg
            out_arg.mkdir(parents=True, exist_ok=True)
            return out_arg / filename
        parent.mkdir(parents=True, exist_ok=True)
        return parent / filename

    @property
    def _extension(self) -> str:
        return self.DEFAULT_CONTAINER_EXT.get(self.config.container, ".mp4")

    def _run_single(self, task: TranscodeTask) -> TranscodeResult:
        cmd = self._build_ffmpeg_cmd(task)
        logging.info("Running FFmpeg: %s", sanitize_for_log(" ".join(cmd)))
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            if stderr:
                logging.error(stderr)
            raise VideoTranscodeError("ffmpeg exited with non-zero status")
        metadata = None
        if self.config.metadata_requested or self.config.metadata_out:
            metadata = self._probe_metadata(task.output_path)
        return TranscodeResult(task.input_arg, task.output_path, metadata)

    def _build_ffmpeg_cmd(self, task: TranscodeTask) -> list[str]:
        cfg = self.config
        cmd: list[str] = [self.ffmpeg_path]
        cmd.append("-n" if cfg.no_overwrite else "-y")
        loglevel = os.environ.get("ZYRA_VERBOSITY")
        if loglevel == "quiet":
            cmd += ["-loglevel", "error"]
        elif loglevel == "debug":
            cmd += ["-loglevel", "info"]
        input_fps = (
            cfg.fps
            if cfg.fps
            else (30.0 if cfg.sos_legacy and task.is_sequence else None)
        )
        if task.is_sequence and input_fps:
            cmd += ["-framerate", str(input_fps)]
        cmd += ["-i", task.input_arg]
        filters: list[str] = []
        if cfg.scale:
            filters.append(_render_scale_filter(cfg.scale))
        if filters:
            cmd += ["-vf", ",".join(filters)]
        cmd += ["-c:v", cfg.codec]
        if cfg.pix_fmt:
            cmd += ["-pix_fmt", cfg.pix_fmt]
        if cfg.bitrate:
            cmd += ["-b:v", cfg.bitrate]
        if cfg.fps:
            cmd += ["-r", str(cfg.fps)]
        if cfg.preset:
            cmd += ["-preset", cfg.preset]
        if cfg.crf is not None:
            cmd += ["-crf", str(cfg.crf)]
        if cfg.gop is not None:
            cmd += ["-g", str(cfg.gop)]
        if cfg.audio_codec:
            cmd += ["-c:a", cfg.audio_codec]
        if cfg.audio_bitrate:
            cmd += ["-b:a", cfg.audio_bitrate]
        cmd.extend(cfg.extra_args)
        cmd.append(str(task.output_path))
        return cmd

    def _probe_metadata(self, output_path: Path) -> dict[str, Any] | None:
        if not self.ffprobe_path:
            logging.warning(
                "ffprobe not available; skipping metadata capture for %s",
                output_path,
            )
            return None
        probe_cmd = [
            self.ffprobe_path,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_streams",
            "-show_format",
            str(output_path),
        ]
        result = subprocess.run(probe_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            if stderr:
                logging.warning("ffprobe failed: %s", stderr)
            return None
        try:
            payload = json.loads(result.stdout or "{}")
        except json.JSONDecodeError:
            logging.warning("Could not parse ffprobe output for %s", output_path)
            return None
        video_stream = _first_stream_of_type(payload.get("streams", []), "video")
        audio_stream = _first_stream_of_type(payload.get("streams", []), "audio")
        fmt = payload.get("format", {})
        return {
            "output": str(output_path),
            "duration": fmt.get("duration"),
            "size": fmt.get("size"),
            "bit_rate": fmt.get("bit_rate"),
            "video_codec": video_stream.get("codec_name") if video_stream else None,
            "width": video_stream.get("width") if video_stream else None,
            "height": video_stream.get("height") if video_stream else None,
            "frame_rate": video_stream.get("r_frame_rate") if video_stream else None,
            "audio_codec": audio_stream.get("codec_name") if audio_stream else None,
        }


def run_video_transcode(args: Any) -> int:
    """Entry point used by the CLI to drive FFmpeg/FFprobe transcoding."""

    try:
        config = VideoTranscoder.from_namespace(args)
        transcoder = VideoTranscoder(config)
        results = transcoder.run()
        _emit_metadata(results, config)
        return 0
    except VideoTranscodeError as exc:
        logging.error(str(exc))
        return 2


def _render_scale_filter(value: str) -> str:
    candidate = value.strip()
    if not candidate:
        return "scale=-2:-2"
    lowered = candidate.lower()
    if lowered.startswith("scale="):
        return candidate
    if lowered.startswith(("w=", "width=")):
        width_expr = candidate.split("=", 1)[1]
        return f"scale={_normalize_scale_dim(width_expr)}:-2"
    if lowered.startswith(("h=", "height=")):
        height_expr = candidate.split("=", 1)[1]
        return f"scale=-2:{_normalize_scale_dim(height_expr)}"
    for sep in (":", "x", "X"):
        if sep in candidate:
            width_expr, height_expr = candidate.split(sep, 1)
            return f"scale={_normalize_scale_dim(width_expr)}:{_normalize_scale_dim(height_expr)}"
    if candidate.isdigit():
        return f"scale=-2:{candidate}"
    if lowered in {"auto", "?", "keep"}:
        return "scale=-2:-2"
    return candidate if lowered.startswith("scale") else f"scale={candidate}"


def _normalize_scale_dim(dim: str) -> str:
    token = dim.strip()
    if not token:
        return "-2"
    lowered = token.lower()
    if lowered in {"auto", "?", "keep"}:
        return "-2"
    if lowered in {"width", "w"}:
        return "iw"
    if lowered in {"height", "h"}:
        return "ih"
    return token


def _default_sequence_basename(stem: str) -> str:
    no_printf = _PRINTF_FORMAT_PATTERN.sub("", stem)
    no_brace = _BRACE_FORMAT_PATTERN.sub("", no_printf)
    trimmed = no_brace.strip().rstrip("_-. ")
    without_digits = trimmed.rstrip(string.digits)
    return without_digits or "transcoded"


# Matches printf placeholders (e.g., %04d, %2$05d) used in FFmpeg sequences
_PRINTF_FORMAT_PATTERN = re.compile(r"%(?:\d+\$)?0?\d*(?:\.\d+)?[diuoxX]")
# Matches brace-style templates (e.g., {0001..0100}) seen in some workflows
_BRACE_FORMAT_PATTERN = re.compile(r"\{[^}]*\}")
# Specific pattern to detect printf digit sequences for sequence detection
_PRINTF_SEQUENCE_PATTERN = re.compile(r"%(?:0?\d+)?d")
# Specific pattern to detect brace ranges like {0001..0100} or {1:100}
_BRACE_SEQUENCE_PATTERN = re.compile(r"\{\d+(?:\.\.|:)\d+(?::\d+)?\}")


def _looks_like_sequence(spec: str) -> bool:
    return bool(
        _PRINTF_SEQUENCE_PATTERN.search(spec) or _BRACE_SEQUENCE_PATTERN.search(spec)
    )


def _expand_glob(pattern: str) -> Iterable[str]:
    path = Path(pattern)
    if not path.is_absolute():
        return [str(match) for match in Path().glob(pattern)]
    anchor = path.anchor or os.sep
    base = Path(anchor)
    relative = pattern[len(anchor) :].lstrip("/\\")
    if not relative:
        relative = "."
    return [str(match) for match in base.glob(relative)]


def _first_stream_of_type(
    streams: Iterable[dict[str, Any]], kind: str
) -> dict[str, Any] | None:
    for stream in streams:
        if stream.get("codec_type") == kind:
            return stream
    return None


def _emit_metadata(
    results: list[TranscodeResult], config: VideoTranscodeConfig
) -> None:
    records = [
        {
            "input": item.source,
            "output": str(item.output),
            "metadata": item.metadata,
        }
        for item in results
        if item.metadata is not None
    ]
    if config.metadata_out:
        config.metadata_out.parent.mkdir(parents=True, exist_ok=True)
        config.metadata_out.write_text(json.dumps(records, indent=2))
        logging.info("Wrote metadata to %s", config.metadata_out)
    if config.metadata_requested:
        logging.info(json.dumps(records, indent=2))


def _common_root(paths: Sequence[Path]) -> Path | None:
    if not paths:
        return None
    parts_lists = [p.parts for p in paths]
    if not parts_lists:
        return None
    min_len = min(len(parts) for parts in parts_lists)
    shared_parts: list[str] = []
    for idx in range(min_len):
        segment = parts_lists[0][idx]
        if all(parts[idx] == segment for parts in parts_lists):
            shared_parts.append(segment)
        else:
            break
    if not shared_parts:
        return None
    common_path = Path(*shared_parts)
    if len(paths) == 1:
        return paths[0].parent
    if paths[0] == common_path:
        return common_path.parent
    return common_path


def _pattern_root(pattern: str) -> Path | None:
    pure = PurePath(pattern)
    parts: list[str] = []
    for part in pure.parts:
        if any(ch in part for ch in "*?[]"):
            break
        parts.append(part)
    if not parts:
        return None
    return Path(*parts)


def _is_relative_to(path: Path, root: Path) -> bool:
    return path.is_relative_to(root)
