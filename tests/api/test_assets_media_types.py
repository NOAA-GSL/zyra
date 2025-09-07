from __future__ import annotations

from pathlib import Path

from zyra.api.utils.assets import infer_assets


def _touch(p: Path) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"")
    return p


def test_infer_assets_media_types(tmp_path) -> None:
    # Map of extension to expected media type from our helper
    cases = {
        ".nc": "application/x-netcdf",
        ".tif": "image/tiff",
        ".mp4": "video/mp4",
        ".grib2": "application/grib2",
        ".json": "application/json",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".zip": "application/zip",
    }
    for ext, expected in cases.items():
        f = _touch(tmp_path / f"test{ext}")
        assets = infer_assets("decimate", "local", {"path": str(f), "input": "-"})
        assert assets, f"No assets inferred for {ext}"
        mt = assets[0].media_type
        assert (
            mt == expected
        ), f"Media type mismatch for {ext}: got {mt}, expected {expected}"
