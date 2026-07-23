# SPDX-License-Identifier: Apache-2.0
from unittest.mock import Mock

import pytest

from zyra.processing.video_processor import VideoProcessor


class TestBuildFfmpegCommand:
    def test_default_shape_unchanged(self):
        vp = VideoProcessor("/images", "/output/video.mp4")
        cmd = vp.build_ffmpeg_command(input_pattern="/images/*.png")
        assert cmd == (
            "ffmpeg -framerate 30 -pattern_type glob -i '/images/*.png'"
            " -r 30 -vcodec libx264 -pix_fmt yuv420p -y /output/video.mp4"
        )

    def test_size_adds_scale_pad_filter(self):
        vp = VideoProcessor("/images", "/output/video.mp4", size=(4096, 2048))
        cmd = vp.build_ffmpeg_command(input_pattern="/images/*.png")
        assert (
            "-vf 'scale=4096:2048:force_original_aspect_ratio=decrease,"
            "pad=4096:2048:(ow-iw)/2:(oh-ih)/2:color=black'"
        ) in cmd

    def test_basemap_chains_scale_pad_after_overlay(self):
        vp = VideoProcessor(
            "/images", "/output/video.mp4", basemap="/maps/base.png", size=(2048, 1024)
        )
        cmd = vp.build_ffmpeg_command(
            input_pattern="/images/*.png", basemap_path="/maps/base.png"
        )
        assert "-loop 1 -i /maps/base.png" in cmd
        assert (
            "-filter_complex '[0:v][1:v]overlay=shortest=1,"
            "scale=2048:1024:force_original_aspect_ratio=decrease,"
        ) in cmd
        assert "-vf" not in cmd

    def test_faststart_flag(self):
        vp = VideoProcessor("/images", "/output/video.mp4", faststart=True)
        cmd = vp.build_ffmpeg_command(input_pattern="/images/*.png")
        assert "-movflags +faststart" in cmd

    def test_fps_override(self):
        vp = VideoProcessor("/images", "/output/video.mp4", fps=30)
        cmd = vp.build_ffmpeg_command(fps=12, input_pattern="/images/*.png")
        assert "-framerate 12" in cmd
        assert "-r 12" in cmd


@pytest.fixture()
def video_processor_setup(monkeypatch):
    input_directory = "/images"
    output_file = "/output/video.mp4"
    video_processor = VideoProcessor(input_directory, output_file)

    # Mock setup
    mock_input = Mock()
    mock_output = Mock()

    monkeypatch.setattr("ffmpeg.input", lambda *args, **kwargs: mock_input)
    monkeypatch.setattr("ffmpeg.output", lambda *args, **kwargs: mock_output)

    # Mock the chained calls
    mock_output.overwrite_output.return_value.run = Mock()

    return video_processor, mock_input, mock_output


@pytest.mark.skip(
    reason="Test is skipped: ffmpeg dependency not available in test environment"
)
def test_process_video(video_processor_setup):
    video_processor, mock_input, mock_output = video_processor_setup
    video_processor.process_video()

    mock_input.assert_called_with(
        f"{video_processor.input_directory}/*.png", pattern_type="glob", framerate=30
    )
    mock_output.assert_called_with(
        video_processor.output_file, vcodec="libx264", pix_fmt="yuv420p", g=1
    )
