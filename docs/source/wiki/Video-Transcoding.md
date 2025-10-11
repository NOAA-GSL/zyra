This page walks through modern usage patterns for `zyra process video-transcode`, including SOS legacy workflows, batch processing, and advanced FFmpeg tweaks. Copy or adapt this content into the live wiki once reviewed.

## Overview

- **Command:** `zyra process video-transcode <input> [options]`
- **Purpose:** Wrap FFmpeg/ffprobe to convert videos or image sequences into modern containers (MP4/WebM/MOV) or SOS legacy outputs.
- **Key features:**
  - Single-file, directory, glob, or FFmpeg image-sequence inputs
  - Automatic codec defaults per container (`mp4` → `h264`, `mpg` → `mpeg2video`, etc.)
  - SOS preset (`--sos-legacy`) for NOAA Science On a Sphere playlists
  - Batch mirroring that preserves relative directory structure when targeting an output folder
  - Metadata capture via ffprobe (`--write-metadata`, `--metadata-out`)

## Prerequisites

- FFmpeg and ffprobe must be installed and on `PATH` (or exported via `ZYRA_FFMPEG_PATH` / `ZYRA_FFPROBE_PATH`).
- Optional: set `ZYRA_VERBOSITY=debug` to surface the constructed FFmpeg command.

Verify binaries:

```bash
$ ffmpeg -version
$ ffprobe -version
```

## Getting Started

### 1. Re-encode a single legacy `.mpg` to modern H.264

```bash
zyra process video-transcode legacy/input.mpg \
  --to mp4 \
  --codec h264 \
  -o modern/output.mp4
```

- Automatically adds `-y` (overwrite) unless `--no-overwrite` is set.
- Defaults to `yuv420p` pixel format for broad compatibility.

### 2. Preserve directory structure for a batch conversion

```bash
zyra process video-transcode data/raw_videos \
  --to mp4 \
  --output data/modern_videos \
  --extra-args "-movflags +faststart"
```

- Any subdirectories under `data/raw_videos` are mirrored relative to `data/modern_videos`.
- The `--extra-args` flag is repeatable; each value is split with `shlex`, so quoting works as expected.

### 3. Transcode a glob of image sequences

```bash
zyra process video-transcode "staging/*/*.jpg" \
  --fps 30 \
  --pix-fmt yuv420p \
  --output data/renders
```

- The CLI detects globs or `%0Xd` patterns and places the `-framerate` flag *before* `-i`, matching FFmpeg requirements.
- Use `--scale` (e.g., `--scale 1920x1080`) to resize on the fly.

### 4. SOS legacy preset (recommended `.mp4` output)

```bash
zyra process video-transcode assets/frames/frame%04d.jpg \
  --sos-legacy \
  -o legacy/sphere_loop.mp4
```

- Applies defaults: `-framerate 30`, `-b:v 25M`, `-c:v libxvid`, `-pix_fmt yuv420p`, `--codec libxvid`, `--audio-codec mp2`.
- SOS workflows overwhelmingly expect `.mp4` filenames even when packed with Xvid, so the CLI keeps `.mp4` unless you explicitly switch containers.

### 5. SOS legacy preset with `.mpg` container (MPEG-2)

```bash
zyra process video-transcode assets/frames/frame%04d.jpg \
  --sos-legacy \
  --to mpg \
  -o legacy/sphere_loop.mpg
```

- The CLI warns that `.mp4` is preferred but auto-switches to `mpeg2video` when you request `--to mpg`.
- Provide `--codec libxvid` if you truly need Xvid inside the MPEG program stream.

## Metadata Workflows

Capture ffprobe output to disk and emit it in the logs:

```bash
zyra process video-transcode samples/ocean.mpg \
  --to mp4 \
  --write-metadata \
  --metadata-out data/meta/ocean.json
```

- `metadata_out` is written as JSON array (one entry per input) containing duration, codec, resolution, bit rate, etc.
- When ffprobe is missing the CLI logs a warning and continues.

## Advanced Options

| Option | Notes |
|--------|-------|
| `--scale HEIGHT` or `WIDTHxHEIGHT` | Uses FFmpeg `scale` filter (`--scale 1080` → `scale=-2:1080`). |
| `--fps` / `--framerate` | Applies both input `-framerate` (for sequences) and output `-r`. |
| `--pix-fmt` | Defaults to `yuv420p`. Override for 10-bit pipelines (e.g., `yuv420p10le`). |
| `--audio-codec` / `--audio-bitrate` | Select AAC, Opus, MP2, etc. |
| `--preset`, `--crf`, `--gop` | Passed straight through to FFmpeg encoders that support them. |
| `--extra-args` | Repeatable; `--extra-args "-movflags +faststart" --extra-args "-max_muxing_queue_size 2048"`. |
| `--no-overwrite` | Switches FFmpeg to `-n`. Useful for incremental reruns. |

## Troubleshooting

- **`ffmpeg binary not found`** – Install FFmpeg and ensure it’s on `PATH`. On macOS: `brew install ffmpeg`. On Ubuntu/Debian: `sudo apt-get install ffmpeg`.
- **Directory write errors** – Make sure the output directory is within the workspace or export `ZYRA_OUTPUT_DIR` via environment variables if running inside limited sandboxes.
- **Codec/container mismatch warnings** – The CLI surfaces warnings when combinations are uncommon (e.g., `--to webm --codec libxvid`). Choose one of the supported pairings (`mp4-h264`, `webm-vp9`, `mpg-mpeg2video`, etc.).
- **Batch glob doesn’t mirror hierarchy** – Ensure the glob includes subdirectories (e.g., `"frames/*/*.jpg"`). The CLI derives the root from the non-glob portion of the pattern.

## Manual Validation Checklist

1. Run `poetry run ruff format . && poetry run ruff check .` before committing changes.
2. Execute targeted tests: `poetry run pytest -q tests/processing/test_video_transcode.py`.
3. Manual spot checks:
   - Single-file `.mpg` → `.mp4` conversion.
   - SOS preset from a JPG sequence (confirm `.mp4` default and warning when forcing `.mpg`).
   - Directory or glob batch to validate relative structure mirroring and extra FFmpeg args.

## Future Enhancements (tracked in plan)

- Optional hardware acceleration flags (`--hwaccel cuda|vaapi`).
- Parallel batch execution for large directories.
- Additional presets (e.g., automatic `-movflags +faststart`, watermarks, etc.).
