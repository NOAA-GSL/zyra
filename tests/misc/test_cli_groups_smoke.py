import io
import subprocess
import sys
from pathlib import Path
from typing import Optional

import pytest


def _run_cli(args, input_bytes: Optional[bytes] = None) -> subprocess.CompletedProcess:
    cmd = [sys.executable, "-m", "datavizhub.cli", *args]
    return subprocess.run(cmd, input=input_bytes, capture_output=True)


def _read_demo_nc_bytes() -> bytes:
    p = Path("tests/testdata/demo.nc")
    return p.read_bytes()


@pytest.mark.cli()
def test_process_decode_grib2_raw_passthrough_group(monkeypatch, capsysbinary):
    # process decode-grib2 should accept NetCDF on stdin and passthrough with --raw
    from datavizhub.cli import main

    demo = _read_demo_nc_bytes()
    fake_stdin = type("S", (), {"buffer": io.BytesIO(demo)})()
    monkeypatch.setattr(sys, "stdin", fake_stdin)

    rc = main(["process", "decode-grib2", "-", "--raw"])
    assert rc == 0
    captured = capsysbinary.readouterr()
    assert captured.out == demo
    assert captured.err == b""


@pytest.mark.cli()
def test_process_convert_format_autodetect_netcdf_group(monkeypatch, capsysbinary):
    # process convert-format should read NetCDF on stdin and emit NetCDF bytes
    from datavizhub.cli import main

    demo = _read_demo_nc_bytes()
    fake_stdin = type("S", (), {"buffer": io.BytesIO(demo)})()
    monkeypatch.setattr(sys, "stdin", fake_stdin)

    rc = main(["process", "convert-format", "-", "netcdf", "--stdout"])
    assert rc == 0
    captured = capsysbinary.readouterr()
    assert captured.out.startswith(b"CDF") or captured.out.startswith(b"\x89HDF")


@pytest.mark.cli()
def test_visualize_heatmap_npy_group(tmp_path: Path):
    # visualize heatmap from a small .npy array should produce a PNG
    try:
        import cartopy  # type: ignore  # noqa: F401
        import numpy as np  # type: ignore
    except Exception:
        pytest.skip("visualization dependencies not available")

    arr = (np.random.rand(32, 64) * 255).astype("float32")
    npy = tmp_path / "demo.npy"
    out = tmp_path / "out.png"
    np.save(npy, arr)

    res = _run_cli(
        [
            "visualize",
            "heatmap",
            "--input",
            str(npy),
            "--output",
            str(out),
            "--no-coastline",
            "--no-borders",
            "--no-gridlines",
        ]
    )
    assert res.returncode == 0, res.stderr.decode(errors="ignore")
    assert out.exists()
    # PNG signature
    sig = out.read_bytes()[:8]
    assert sig == b"\x89PNG\r\n\x1a\n"


@pytest.mark.cli()
def test_visualize_contour_npy_group(tmp_path: Path):
    # visualize contour from a small .npy array should produce a PNG
    try:
        import cartopy  # type: ignore  # noqa: F401
        import numpy as np  # type: ignore
    except Exception:
        pytest.skip("visualization dependencies not available")

    arr = (np.linspace(0, 1, 32 * 64).reshape(32, 64)).astype("float32")
    npy = tmp_path / "demo_contour.npy"
    out = tmp_path / "contour.png"
    np.save(npy, arr)

    res = _run_cli(
        [
            "visualize",
            "contour",
            "--input",
            str(npy),
            "--output",
            str(out),
            "--levels",
            "5",
            "--filled",
            "--no-coastline",
            "--no-borders",
            "--no-gridlines",
        ]
    )
    assert res.returncode == 0, res.stderr.decode(errors="ignore")
    assert out.exists()
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


@pytest.mark.cli()
def test_visualize_vector_npy_group(tmp_path: Path):
    # visualize vector from small U/V arrays should produce a PNG
    try:
        import cartopy  # type: ignore  # noqa: F401
        import numpy as np  # type: ignore
    except Exception:
        pytest.skip("visualization dependencies not available")

    u = (np.ones((16, 32)) * 0.5).astype("float32")
    v = (np.zeros((16, 32))).astype("float32")
    up = tmp_path / "u.npy"
    vp = tmp_path / "v.npy"
    out = tmp_path / "vec.png"
    np.save(up, u)
    np.save(vp, v)

    res = _run_cli(
        [
            "visualize",
            "vector",
            "--u",
            str(up),
            "--v",
            str(vp),
            "--output",
            str(out),
            "--no-coastline",
            "--no-borders",
            "--no-gridlines",
        ]
    )
    assert res.returncode == 0, res.stderr.decode(errors="ignore")
    assert out.exists()
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


# Optional: tile-based map rendering path (requires contextily and opt-in via env)
def _has_contextily_tiles_enabled() -> bool:
    import os

    try:
        import contextily  # type: ignore  # noqa: F401
    except Exception:
        return False
    return os.environ.get("DATAVIZHUB_RUN_TILE_TESTS") == "1"


@pytest.mark.cli()
@pytest.mark.skipif(
    not _has_contextily_tiles_enabled(),
    reason="contextily not installed or tile tests not enabled",
)
def test_visualize_contour_with_tiles(tmp_path: Path):
    import numpy as np  # type: ignore

    arr = (np.linspace(0, 1, 32 * 64).reshape(32, 64)).astype("float32")
    npy = tmp_path / "demo_contour_tiles.npy"
    out = tmp_path / "contour_tiles.png"
    np.save(npy, arr)

    res = _run_cli(
        [
            "visualize",
            "contour",
            "--input",
            str(npy),
            "--output",
            str(out),
            "--levels",
            "5",
            "--filled",
            "--map-type",
            "tile",
            "--tile-zoom",
            "1",
            "--no-coastline",
            "--no-borders",
            "--no-gridlines",
        ]
    )
    assert res.returncode == 0, res.stderr.decode(errors="ignore")
    assert out.exists()
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


@pytest.mark.cli()
@pytest.mark.skipif(
    not _has_contextily_tiles_enabled(),
    reason="contextily not installed or tile tests not enabled",
)
def test_visualize_vector_with_tiles(tmp_path: Path):
    import numpy as np  # type: ignore

    u = (np.ones((16, 32)) * 0.25).astype("float32")
    v = (np.ones((16, 32)) * 0.1).astype("float32")
    up = tmp_path / "u_tiles.npy"
    vp = tmp_path / "v_tiles.npy"
    out = tmp_path / "vec_tiles.png"
    np.save(up, u)
    np.save(vp, v)

    res = _run_cli(
        [
            "visualize",
            "vector",
            "--u",
            str(up),
            "--v",
            str(vp),
            "--output",
            str(out),
            "--map-type",
            "tile",
            "--tile-zoom",
            "1",
            "--no-coastline",
            "--no-borders",
            "--no-gridlines",
        ]
    )
    assert res.returncode == 0, res.stderr.decode(errors="ignore")
    assert out.exists()
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
