import pytest
import subprocess
import sys


@pytest.mark.cli
def test_heatmap_tiles_smoke(tmp_path):
    out_file = tmp_path / "heatmap_tiles.png"
    cmd = [
        sys.executable,
        "-m",
        "datavizhub.cli",
        "heatmap",
        "--input",
        "samples/demo.npy",
        "--output",
        str(out_file),
        "--map-type",
        "tile",
        "--tile-zoom",
        "2",
    ]
    result = subprocess.run(cmd)
    assert result.returncode == 0
    assert out_file.exists()


@pytest.mark.cli
def test_animate_tiles_smoke(tmp_path):
    out_dir = tmp_path / "frames"
    manifest = tmp_path / "manifest.json"
    cmd = [
        sys.executable,
        "-m",
        "datavizhub.cli",
        "animate",
        "--mode",
        "heatmap",
        "--input",
        "samples/demo.npy",
        "--output-dir",
        str(out_dir),
        "--manifest",
        str(manifest),
        "--map-type",
        "tile",
        "--tile-zoom",
        "2",
        "--width",
        "320",
        "--height",
        "160",
    ]
    result = subprocess.run(cmd)
    assert result.returncode == 0
    assert manifest.exists()
    # At least the first frame should exist
    first = out_dir / "frame_0000.png"
    assert first.exists()


@pytest.mark.cli
def test_contour_tiles_smoke(tmp_path):
    out_file = tmp_path / "contour_tiles.png"
    cmd = [
        sys.executable,
        "-m",
        "datavizhub.cli",
        "contour",
        "--input",
        "samples/demo.npy",
        "--output",
        str(out_file),
        "--levels",
        "5",
        "--filled",
        "--map-type",
        "tile",
        "--tile-zoom",
        "2",
    ]
    result = subprocess.run(cmd)
    assert result.returncode == 0
    assert out_file.exists()
