import logging
import shlex
import subprocess
from pathlib import Path
from typing import Any, Optional

from zyra.processing.base import DataProcessor


class VideoProcessor(DataProcessor):
    """Create videos from image sequences via FFmpeg.

    Processes image frames into a cohesive video file. Optionally overlays a
    static basemap beneath the frames. Requires system FFmpeg and FFprobe to
    be installed and accessible on PATH.

    Parameters
    ----------
    input_directory : str
        Directory where input images are stored.
    output_file : str
        Destination path for the rendered video file.
    basemap : str, optional
        Optional background image path to overlay beneath frames.

    Examples
    --------
    Render a video from PNG frames::

        from zyra.processing.video_processor import VideoProcessor

        vp = VideoProcessor(input_directory="./frames", output_file="./out.mp4")
        vp.load("./frames")
        vp.process()
        vp.save("./out.mp4")
    """

    def __init__(
        self,
        input_directory: str,
        output_file: str,
        basemap: Optional[str] = None,
        fps: int = 30,
    ):
        self.input_directory = input_directory
        self.output_file = output_file
        self.basemap = basemap
        self.fps = int(fps)

    FEATURES = {"load", "process", "save", "validate"}

    # --- DataProcessor interface --------------------------------------------------------
    def load(self, input_source: Any) -> None:
        """Set or update the input directory.

        Parameters
        ----------
        input_source : Any
            Path to the directory containing input frames. Converted to str.
        """
        self.input_directory = str(input_source)

    def process(self, **kwargs: Any) -> Optional[str]:
        """Compile image frames into a video.

        Returns
        -------
        str or None
            The output file path on success; ``None`` if processing failed.
        """
        fps = int(kwargs.get("fps", self.fps))
        success = self.process_video(fps=fps)
        return self.output_file if success else None

    def save(self, output_path: Optional[str] = None) -> Optional[str]:
        """Finalize the configured output path.

        Parameters
        ----------
        output_path : str, optional
            If provided, updates the configured output path before returning it.

        Returns
        -------
        str or None
            The output path the processor will write or has written to.
        """
        if output_path:
            self.output_file = output_path
        return self.output_file

    def validate(self) -> bool:
        """Check FFmpeg/FFprobe availability.

        Returns
        -------
        bool
            True if FFmpeg and FFprobe executables are available.
        """
        return self.check_ffmpeg_installed()

    # --- Original implementation --------------------------------------------------------
    def check_ffmpeg_installed(self) -> bool:
        """Check that FFmpeg and FFprobe are available on PATH.

        Returns
        -------
        bool
            True when both tools return version info without error.
        """
        try:
            result_ffmpeg = subprocess.run(
                ["ffmpeg", "-version"], capture_output=True, text=True
            )
            if result_ffmpeg.returncode != 0:
                logging.error("FFmpeg is not installed or not found in system path.")
                return False
            result_ffprobe = subprocess.run(
                ["ffprobe", "-version"], capture_output=True, text=True
            )
            if result_ffprobe.returncode != 0:
                logging.error("FFprobe is not installed or not found in system path.")
                return False
            return True
        except Exception as e:
            logging.error(f"An error occurred while checking FFmpeg installation: {e}")
            return False

    def process_video(self, *, fps: int | None = None) -> bool:
        """Build the video using FFmpeg from frames in ``input_directory``.

        Notes
        -----
        - Uses glob pattern matching on the first file's extension to include
          all frames with that extension in the directory.
        - When ``basemap`` is provided, overlays frames on top of the basemap.
        - Logs FFmpeg output lines at debug level.
        """
        if not self.check_ffmpeg_installed():
            logging.error("Cannot process video as FFmpeg is not installed.")
            return False
        try:
            input_dir = Path(self.input_directory)
            logging.debug("Scanning directory for files...")
            files = sorted(
                [f for f in input_dir.iterdir() if f.is_file()], key=lambda f: f.name
            )
            if not files:
                logging.error("No files found in the video input directory.")
                return False
            logging.debug(f"Found {len(files)} files.")
            file_extension = files[0].suffix
            input_pattern = f"{self.input_directory}/*{file_extension}"
            logging.debug(f"Processing files with extension: {file_extension}")
            output_path = self.output_file
            ffmpeg_cmd = "ffmpeg"
            if self.basemap:
                ffmpeg_cmd += f" -framerate {fps or self.fps} -loop 1 -i {self.basemap}"
            ffmpeg_cmd += (
                f" -framerate {fps or self.fps} -pattern_type glob -i '{input_pattern}'"
            )
            if self.basemap:
                ffmpeg_cmd += " -filter_complex '[0:v][1:v]overlay=shortest=1'"
            ffmpeg_cmd += f" -r {fps or self.fps} -vcodec libx264 -pix_fmt yuv420p -y {output_path}"
            logging.info(f"Starting video processing using:{ffmpeg_cmd}")
            cmd = shlex.split(ffmpeg_cmd)
            with subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
            ) as proc:
                for line in proc.stdout:
                    logging.debug(line.strip())
            logging.debug("Video processing complete.")
            logging.info(f"Video created at {self.output_file}")
            # Consider success if the expected output file exists
            try:
                if Path(self.output_file).exists():
                    return True
            except Exception:
                pass
            return False
        except Exception as e:
            logging.error(f"An error occurred: {e}")
            return False

    def validate_video_file(self, video_file: str) -> bool:
        """Validate codec, resolution, and frame rate of an output video.

        Parameters
        ----------
        video_file : str
            Path to the video file to validate.

        Returns
        -------
        bool
            True if video matches allowed codec/resolution/frame rate.
        """
        if not self.check_ffmpeg_installed():
            logging.error("Cannot validate video file as FFmpeg is not installed.")
            return False
        valid_codecs = ["h264", "hevc"]
        valid_resolutions = ["1920x1080", "2048x1024", "4096x2048", "3600x1800"]
        valid_frame_rates = ["30"]
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name,width,height,r_frame_rate",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            video_file,
        ]
        process = subprocess.run(cmd, capture_output=True, text=True)
        if process.returncode != 0:
            logging.error(f"FFprobe error: {process.stderr}")
            return False
        output = process.stdout.splitlines()
        if len(output) < 4:
            logging.error("Could not retrieve all video properties.")
            return False
        codec, width, height, frame_rate_str = output
        resolution = f"{width}x{height}"
        # Safely parse r_frame_rate which is typically a fraction like "30000/1001"
        try:
            if "/" in frame_rate_str:
                num_s, den_s = frame_rate_str.split("/", 1)
                # Avoid converting a zero denominator; treat as invalid
                den_s_stripped = den_s.strip()
                try:
                    if float(den_s_stripped) == 0.0:
                        logging.error(
                            "Frame rate reports zero denominator: %s", frame_rate_str
                        )
                        return False
                except ValueError:
                    logging.error(
                        "Frame rate denominator is not a valid float: %s", den_s
                    )
                    return False
                num = float(num_s)
                den = float(den_s_stripped)
                frame_rate = float(num) / float(den)
            else:
                frame_rate = float(frame_rate_str)
        except ValueError:
            logging.error(f"Unable to parse frame rate: {frame_rate_str}")
            return False
        # Tolerance-based frame rate validation
        tolerance = 0.05
        valid_frame_rates_float = [float(fps) for fps in valid_frame_rates]
        if codec not in valid_codecs:
            logging.error(f"Invalid codec: {codec}")
            return False
        if resolution not in valid_resolutions:
            logging.error(f"Invalid resolution: {resolution}")
            return False
        if not any(
            abs(frame_rate - valid_fps) <= tolerance
            for valid_fps in valid_frame_rates_float
        ):
            logging.error(
                f"Invalid frame rate: {frame_rate} (expected one of {valid_frame_rates})"
            )
            return False
        logging.info(f"{video_file} is a valid video file")
        return True

    def validate_frame_count(self, video_file: str, expected_frame_count: int) -> bool:
        """Validate the total number of frames in a video.

        Parameters
        ----------
        video_file : str
            Path to the video file to inspect.
        expected_frame_count : int
            Expected total number of frames.

        Returns
        -------
        bool
            True when expected frame count matches the probed value.
        """
        if not self.check_ffmpeg_installed():
            logging.error("Cannot validate frame count as FFmpeg is not installed.")
            return False
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-count_frames",
            "-show_entries",
            "stream=nb_read_frames",
            "-of",
            "default=nokey=1:noprint_wrappers=1",
            video_file,
        ]
        process = subprocess.run(cmd, capture_output=True, text=True)
        if process.returncode != 0:
            logging.error(f"FFprobe error: {process.stderr}")
            return False
        total_frames = process.stdout.strip()
        if not total_frames.isdigit() or int(total_frames) != expected_frame_count:
            logging.error(
                f"Invalid frame count: expected {expected_frame_count}, got {total_frames}"
            )
            return False
        logging.info(
            f"{video_file} has the correct number of frames ({expected_frame_count})"
        )
        return True
