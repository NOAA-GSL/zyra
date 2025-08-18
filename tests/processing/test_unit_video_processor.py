from unittest.mock import Mock

import pytest
from datavizhub.processing.video_processor import VideoProcessor


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
