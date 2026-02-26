# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import numpy as np
import pytest
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import from_origin

from zyra.transform.raster import convert_geotiff_to_cog


def _create_test_raster(path: str, *, width: int = 256, height: int = 256) -> None:
    data = np.arange(width * height, dtype=np.uint16).reshape((height, width))
    profile = {
        "driver": "GTiff",
        "height": height,
        "width": width,
        "count": 1,
        "dtype": "uint16",
        "crs": "EPSG:3857",
        "transform": from_origin(-1_000_000, 1_000_000, 1_000, 1_000),
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data, 1)


def test_convert_geotiff_to_cog_reprojects_and_builds_overviews(tmp_path):
    src_path = tmp_path / "source.tif"
    dst_path = tmp_path / "output" / "cog.tif"
    _create_test_raster(str(src_path))

    result = convert_geotiff_to_cog(
        src_path,
        dst_path,
        dst_crs="EPSG:4326",
        resampling=Resampling.bilinear,
        overview_levels=(2,),
        overview_resampling=Resampling.nearest,
        blocksize=128,
        compression="LZW",
        predictor=2,
        overwrite=True,
    )

    assert result == dst_path
    assert dst_path.exists()

    with rasterio.open(dst_path) as ds:
        assert ds.crs.to_epsg() == 4326
        assert ds.profile.get("tiled")
        assert ds.profile.get("blockxsize") == 128
        assert ds.profile.get("blockysize") == 128
        assert (ds.profile.get("compress") or "").upper() == "LZW"
        assert ds.overviews(1) == [2]


def test_convert_geotiff_to_cog_requires_overwrite(tmp_path):
    src_path = tmp_path / "source.tif"
    dst_path = tmp_path / "cog.tif"
    _create_test_raster(str(src_path))

    # First conversion creates the file
    convert_geotiff_to_cog(src_path, dst_path, overwrite=True)

    with pytest.raises(FileExistsError):
        convert_geotiff_to_cog(src_path, dst_path, overwrite=False)
