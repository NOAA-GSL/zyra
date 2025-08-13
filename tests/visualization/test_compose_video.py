import os
import tempfile


def test_cli_compose_video_smoke():
    try:
        # No hard dependency on ffmpeg; we just ensure graceful behavior
        import matplotlib.pyplot as plt
    except Exception as e:
        import pytest

        pytest.skip(f"Visualization deps missing: {e}")

    import subprocess, sys

    with tempfile.TemporaryDirectory() as td:
        frames = os.path.join(td, "frames")
        os.makedirs(frames, exist_ok=True)
        # Create two tiny frames
        for i in range(2):
            fig = plt.figure(figsize=(1, 1), dpi=50)
            plt.text(0.5, 0.5, f"{i}", ha="center", va="center")
            fig.savefig(os.path.join(frames, f"frame_{i:04d}.png"))
            plt.close(fig)
        out = os.path.join(td, "out.mp4")
        cmd = [
            sys.executable,
            "-m",
            "datavizhub.cli",
            "compose-video",
            "--frames",
            frames,
            "-o",
            out,
            "--fps",
            "12",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        # Should return 0 regardless of ffmpeg availability (graceful skip)
        assert proc.returncode == 0, proc.stderr
        # If ffmpeg is present, an MP4 may be created; if not, that's fine
        # We just care that the command doesn't error out.
