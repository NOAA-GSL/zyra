import logging
import shlex
import subprocess
from pathlib import Path


class VideoProcessor:
    """
    VideoProcessor is a class designed to facilitate video processing tasks,
    specifically for creating videos from a sequence of images. This class provides
    functionalities to compile individual image frames into a cohesive video file,
    making it ideal for applications such as time-lapse videos, animations, or real-time
    video of data where a series of images need to be sequentially combined into a video
    format.

    Leveraging the 'ffmpeg-python' package, a wrapper around the FFmpeg application, the
    VideoProcessor handles the intricacies of video encoding and formatting. TODO: Users
    can specify input and output parameters, including frame rate, resolution, and
    codecs, to customize the video creation process according to their requirements.

    Usage:
    Initialize the class with the input directory containing image frames and the desired
    output video file path. Call the `process_video` method to start the video processing
    and creation procedure. The class handles the sorting and sequencing of image frames
    and provides options to apply additional video processing filters if needed.

    Example:
    ```python
    video_processor = VideoProcessor('/path/to/image_frames', '/path/to/output/video.mp4')
    video_processor.process_video()
    ```

    Note:
    Ensure that FFmpeg is installed on your system, as 'ffmpeg-python' is a wrapper
    and does not include the FFmpeg executable. Also, be mindful of the image formats and
    naming conventions in the input directory, as they should be consistent for optimal processing.
    """

    def __init__(self, input_directory, output_file, basemap=None):
        """
        Initialize the VideoProcessor with input directory and output file.

        Args:
            input_directory (str): Directory where the input images are stored.
            output_file (str): Path for the output video file.
            basemap (str): Path to image file to use as a background image for videos
        """
        self.input_directory = input_directory
        self.output_file = output_file
        self.basemap = basemap

    def check_ffmpeg_installed(self):
        """
        Checks if FFmpeg and FFprobe are installed on the system.
        """
        try:
            # Check ffmpeg
            result_ffmpeg = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
            if result_ffmpeg.returncode != 0:
                logging.error("FFmpeg is not installed or not found in system path.")
                return False

            # Check ffprobe
            result_ffprobe = subprocess.run(["ffprobe", "-version"], capture_output=True, text=True)
            if result_ffprobe.returncode != 0:
                logging.error("FFprobe is not installed or not found in system path.")
                return False

            # Both checks passed
            return True
        except Exception as e:
            logging.error(f"An error occurred while checking FFmpeg installation: {e}")
            return False

    def process_video(self):
        """
        Process all files of the same type as the first file in the input directory and compile them into a video.
        Assumes that the input directory contains image files suitable for video compilation. The basemap is optional.
        """
        if not self.check_ffmpeg_installed():
            # If FFmpeg is not installed, log the error and exit the method
            logging.error("Cannot process video as FFmpeg is not installed.")
            return

        try:
            # Initialize Path object for the input directory
            input_dir = Path(self.input_directory)
            logging.debug("Scanning directory for files...")
            files = sorted(
                [f for f in input_dir.iterdir() if f.is_file()], key=lambda f: f.name
            )

            if not files:
                logging.error("No files found in the video input directory.")
                return

            logging.debug(f"Found {len(files)} files.")

            # Determine the extension of the first file and construct file pattern
            file_extension = files[0].suffix
            input_pattern = f"{self.input_directory}/*{file_extension}"
            logging.debug(f"Processing files with extension: {file_extension}")

            # Constructing the ffmpeg command
            output_path = self.output_file
            ffmpeg_cmd = "ffmpeg"

            # Check if basemap is provided and adjust command accordingly
            if self.basemap:
                basemap_path = self.basemap
                ffmpeg_cmd += f" -framerate 30 -loop 1 -i {basemap_path}"

            ffmpeg_cmd += f" -framerate 30 -pattern_type glob -i '{input_pattern}'"

            # Apply overlay filter if basemap is used, else proceed with image sequence only
            if self.basemap:
                ffmpeg_cmd += " -filter_complex '[0:v][1:v]overlay=shortest=1'"

            ffmpeg_cmd += f" -vcodec libx264 -pix_fmt yuv420p -y {output_path}"

            logging.info(f"Starting video processing using:{ffmpeg_cmd}")

            # Use shlex to ensure the command is split correctly
            cmd = shlex.split(ffmpeg_cmd)

            # Start the ffmpeg process
            with subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
            ) as proc:
                for line in proc.stdout:
                    logging.debug(line.strip())  # Log the ffmpeg output in real-time

            logging.debug("Video processing complete.")
            logging.info(f"Video created at {self.output_file}")

        except Exception as e:
            logging.error(f"An error occurred: {e}")

    def validate_video_file(self, video_file):
        """
        Validates the video file's codec, resolution, and frame rate using FFmpeg.

        Args:
            video_file (str): Path to the video file to validate.

        Returns:
            bool: True if the video meets the specified criteria, False otherwise.
        """
        if not self.check_ffmpeg_installed():
            # If FFmpeg is not installed, log the error and exit the method
            logging.error("Cannot validate video file as FFmpeg is not installed.")
            return False

        # Define valid video properties
        valid_codecs = ["h264", "hevc"]
        valid_resolutions = [
            "1920x1080",
            "2048x1024",
            "4096x2048",
            "3600x1800",
        ]  # Format: 'widthxheight'
        valid_frame_rates = ["30"]

        # Construct and run the FFmpeg command to get video file properties
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

        # Check if FFprobe command failed
        if process.returncode != 0:
            logging.error(f"FFprobe error: {process.stderr}")
            return False

        # Parse the FFprobe output
        output = process.stdout.splitlines()
        if len(output) < 4:  # Ensure all needed properties are present
            logging.error("Could not retrieve all video properties.")
            return False

        codec, width, height, frame_rate_str = output
        resolution = f"{width}x{height}"
        # Safely evaluate frame rate from a fraction
        frame_rate = (
            round(
                eval(frame_rate_str.split("/")[0]) / eval(frame_rate_str.split("/")[1])
            )
            if "/" in frame_rate_str
            else int(frame_rate_str)
        )

        # Validate video properties
        if codec not in valid_codecs:
            logging.error(f"Invalid codec: {codec}")
            return False
        if resolution not in valid_resolutions:
            logging.error(f"Invalid resolution: {resolution}")
            return False
        if str(frame_rate) not in valid_frame_rates:
            logging.error(f"Invalid frame rate: {frame_rate}")
            return False

        logging.info(f"{video_file} is a valid video file")
        return True

    def validate_frame_count(self, video_file, expected_frame_count):
        """
        Validates the number of frames in the video file against the expected frame count.

        Args:
            video_file (str): Path to the video file to validate.
            expected_frame_count (int): The expected number of frames in the video.

        Returns:
            bool: True if the video contains the expected number of frames, False otherwise.
        """
        if not self.check_ffmpeg_installed():
            logging.error("Cannot validate frame count as FFmpeg is not installed.")
            return False

        # Construct and run the FFprobe command to get the total frame count
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

        # Retrieve the total frame count from FFprobe output
        total_frames = process.stdout.strip()

        # Validate the total number of frames
        if not total_frames.isdigit() or int(total_frames) != expected_frame_count:
            logging.error(f"Invalid frame count: expected {expected_frame_count}, got {total_frames}")
            return False

        logging.info(f"{video_file} has the correct number of frames ({expected_frame_count})")
        return True
