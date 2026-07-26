# SPDX-License-Identifier: Apache-2.0
"""Basemap image placement vs. the viewport (#284).

``add_basemap_cartopy`` took one ``extent`` and used it for two
different things: the viewport handed to ``ax.set_extent``, and the
geographic extent the background image covers. Those coincide only when
the view is global, so a regional ``--extent`` stretched the whole world
into that box — a North America view rendering Eurasia inside it.

The fixtures here build their own basemap rather than using
``zyra.assets.images``: those are Git LFS-tracked, and a checkout
without the objects fetched has pointer files that ``imread`` cannot
parse, which would make these tests pass for the wrong reason.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("cartopy")
pytest.importorskip("matplotlib")

import matplotlib  # noqa: E402

matplotlib.use("Agg")

import cartopy.crs as ccrs  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import image as mpimg  # noqa: E402

from zyra.visualization.basemap import add_basemap_cartopy  # noqa: E402

# A North America viewport, in [west, east, south, north].
VIEWPORT = [-135.0, -60.0, 21.0, 53.0]


def _write_global_basemap(path):
    """A black 1°/px world with a white block over Australia.

    The block sits far outside `VIEWPORT`, which is what makes the
    assertion a clean boolean: placed correctly the block is off-screen,
    while squashing the globe into the viewport drags it into frame.
    """
    img = np.zeros((180, 360, 3), dtype="uint8")
    # lon 100..140E, lat 20..60S -> rows/cols in a north-up 1°/px grid.
    img[110:150, 280:320] = 255
    mpimg.imsave(str(path), img)


def _render(tmp_path, basemap):
    fig = plt.figure(figsize=(6, 3), dpi=50)
    ax = fig.add_subplot(1, 1, 1, projection=ccrs.PlateCarree())
    add_basemap_cartopy(ax, VIEWPORT, image_path=str(basemap))
    out = tmp_path / "render.png"
    fig.savefig(out, bbox_inches="tight", pad_inches=0)
    plt.close(fig)
    return np.asarray(mpimg.imread(str(out)))[..., :3]


def test_regional_viewport_does_not_drag_in_the_whole_globe(tmp_path):
    basemap = tmp_path / "world.png"
    _write_global_basemap(basemap)

    rendered = _render(tmp_path, basemap)

    # Rendered floats in 0..1; the marker is pure white.
    bright = (rendered > 0.9).all(axis=-1).mean()
    assert bright == 0.0, (
        "the Australia marker is outside the North America viewport, so it "
        f"must not appear; {bright:.1%} of the render is white, which means "
        "the global image was squashed into the viewport"
    )


def test_explicit_image_extent_is_honored(tmp_path):
    """A caller may declare that the image covers only the viewport.

    This is the case the old code got right by accident, and it has to
    keep working — an image whose extent genuinely is the viewport
    should fill the frame.
    """
    basemap = tmp_path / "region.png"
    img = np.full((32, 75, 3), 255, dtype="uint8")
    mpimg.imsave(str(basemap), img)

    fig = plt.figure(figsize=(6, 3), dpi=50)
    ax = fig.add_subplot(1, 1, 1, projection=ccrs.PlateCarree())
    add_basemap_cartopy(ax, VIEWPORT, image_path=str(basemap), image_extent=VIEWPORT)
    out = tmp_path / "region_render.png"
    fig.savefig(out, bbox_inches="tight", pad_inches=0)
    plt.close(fig)

    rendered = np.asarray(mpimg.imread(str(out)))[..., :3]
    bright = (rendered > 0.9).all(axis=-1).mean()
    assert (
        bright > 0.9
    ), f"image declared at the viewport should fill it, got {bright:.1%}"


def test_unreadable_basemap_warns_instead_of_failing_silently(tmp_path, caplog):
    """An asset that will not parse must say so.

    Git LFS pointer files are the motivating case: `imread` raises, the
    render comes out blank, and before this the exception was swallowed
    with no message at all.
    """
    bad = tmp_path / "pointer.jpg"
    bad.write_text("version https://git-lfs.github.com/spec/v1\noid sha256:deadbeef\n")

    fig = plt.figure(figsize=(4, 2), dpi=50)
    ax = fig.add_subplot(1, 1, 1, projection=ccrs.PlateCarree())
    with caplog.at_level("WARNING"):
        add_basemap_cartopy(ax, VIEWPORT, image_path=str(bad))
    plt.close(fig)

    assert "pointer.jpg" in caplog.text
    assert "could not be drawn" in caplog.text
