# SPDX-License-Identifier: Apache-2.0
"""Value-exact grayscale frames for data-encoded video.

The heatmap path renders a *picture*: values go through a colormap,
get composited over a basemap, and reach ffmpeg as RGB. By render time
the numbers are gone, and "no data" carries whatever was underneath.

This writes the *data* instead. Each frame is an 8-bit grayscale PNG
whose luma is the value normalised against ``vmin``/``vmax``, and a
JSON sidecar carries the palette and scale so the client can colour it
at display time. That makes transparency exact, makes a dataset
repalettable without re-encoding, and keeps the values available for a
readout under the cursor.

**This deliberately does not reuse the figure pipeline.**
``HeatmapManager.render`` builds a cartopy axes and saves with
``bbox_inches="tight"``; cartopy refits the extent to the axes aspect
and the rasteriser resamples. Asking it for exactly the source grid
(1799x1059) returns 1799x899. Resampling is fine for a picture and
fatal for a value encoding, so this is a short path that never touches
matplotlib for the raster. Matplotlib is used only to evaluate the
palette for the sidecar, where it is the same colormap the picture
path would have used — that equivalence is the point.

See ``docs/DATA_ENCODED_VIDEO_PLAN.md`` in the terraviz repo.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

#: Number of palette stops written to the sidecar. Matches the 8-bit
#: luma channel the client samples — more stops cannot express more.
SIDECAR_STOPS = 256


def normalize_to_luma(
    data: Any,
    *,
    vmin: float,
    vmax: float,
):
    """Normalise ``data`` to 8-bit codes against a fixed scale.

    ``vmin``/``vmax`` are required and never inferred. A per-frame
    autoscale would make luma mean something different in every frame
    of the same dataset — the value under the cursor would change as
    the animation played, with nothing on screen to indicate it.

    NaN and masked entries become 0, which is both ``vmin`` and the
    "nothing measured here" code the palette's transparent range
    covers. Values outside the range clamp rather than wrap, so an
    outlier reads as saturated instead of as its own opposite.
    """
    import numpy as np

    if vmin is None or vmax is None:
        raise ValueError("--vmin and --vmax are required for data-encoded output")
    span = float(vmax) - float(vmin)
    if not np.isfinite(span) or span == 0:
        raise ValueError(
            f"--vmin and --vmax must be finite and distinct (got {vmin}, {vmax})"
        )

    arr = np.asarray(data)
    if np.ma.isMaskedArray(data):
        arr = np.ma.filled(data.astype("float64"), np.nan)
    arr = arr.astype("float64", copy=False)
    if arr.ndim != 2:
        raise ValueError(f"Data must be a 2-D grid for luma output (got {arr.ndim}-D)")

    t = (arr - float(vmin)) / span
    t = np.clip(t, 0.0, 1.0)
    # NaN survives clip; zero it explicitly so nodata lands on 0.
    t = np.where(np.isfinite(t), t, 0.0)
    return np.rint(t * 255.0).astype("uint8")


def resize_nearest(codes, width: int | None, height: int | None):
    """Resize an 8-bit code array by nearest-neighbour index selection.

    Nearest only, and never by default. Any interpolating resampler
    averages across the nodata/data boundary and produces values that
    were never measured; the same reason the downstream encoder scales
    with ``flags=neighbor``. Passing no size writes the source grid
    unchanged, which is the recommended path.
    """
    import numpy as np

    src_h, src_w = codes.shape
    out_w = int(width) if width else src_w
    out_h = int(height) if height else src_h
    if out_w == src_w and out_h == src_h:
        return codes
    if out_w <= 0 or out_h <= 0:
        raise ValueError("--width and --height must be positive")
    rows = np.minimum((np.arange(out_h) * src_h) // out_h, src_h - 1)
    cols = np.minimum((np.arange(out_w) * src_w) // out_w, src_w - 1)
    return codes[rows[:, None], cols[None, :]]


def write_luma_png(
    data: Any,
    output_path: str,
    *,
    vmin: float,
    vmax: float,
    width: int | None = None,
    height: int | None = None,
) -> str:
    """Write ``data`` as an 8-bit grayscale PNG. Returns the path."""
    from PIL import Image

    codes = resize_nearest(normalize_to_luma(data, vmin=vmin, vmax=vmax), width, height)
    # Mode "L" is a single 8-bit channel — no palette, no colour
    # profile, nothing between the array and the file.
    Image.fromarray(codes, mode="L").save(output_path, format="PNG", optimize=True)
    return output_path


def build_color_scale(
    palette_spec: dict | None,
    *,
    vmin: float,
    vmax: float,
    units: str | None = None,
) -> dict:
    """Build the sidecar the client colours the frames with.

    The palette is evaluated through the *same* ``ColormapManager``
    construction the picture path uses, then sampled at
    ``SIDECAR_STOPS`` positions. Sampling the real colormap rather than
    re-deriving one means a data-encoded dataset and its colourised
    predecessor agree on colour by construction, instead of by two
    implementations happening to match.

    With no palette the result is a plain black→white ramp, so a
    dataset published without ``--cmap-file`` is still viewable and
    still probeable.
    """
    import numpy as np

    span = float(vmax) - float(vmin)
    if not np.isfinite(span) or span == 0:
        raise ValueError(
            f"--vmin and --vmax must be finite and distinct (got {vmin}, {vmax})"
        )

    ts = np.linspace(0.0, 1.0, SIDECAR_STOPS)
    rgba = _sample_palette(palette_spec, ts, vmin=float(vmin), vmax=span + float(vmin))

    scale: dict[str, Any] = {
        "stops": [
            {"t": round(float(t), 6), "rgba": [int(c) for c in row]}
            for t, row in zip(ts, rgba, strict=True)
        ],
        "vmin": float(vmin),
        "vmax": float(vmax),
    }
    if units:
        scale["units"] = str(units)
    transparent = _transparent_range(palette_spec)
    if transparent:
        scale["transparentRange"] = transparent
    return scale


def _sample_palette(
    palette_spec: dict | None,
    ts: Sequence[float],
    *,
    vmin: float,
    vmax: float,
):
    """Evaluate a palette at normalised positions, returning 0-255 RGBA."""
    import numpy as np

    if not palette_spec:
        grey = np.rint(np.asarray(ts) * 255.0).astype("uint8")
        out = np.zeros((len(ts), 4), dtype="uint8")
        out[:, 0] = out[:, 1] = out[:, 2] = grey
        out[:, 3] = 255
        return out

    from zyra.visualization.colormap_manager import ColormapManager

    ptype = palette_spec.get("type")
    if ptype == "classified":
        cmap, norm = ColormapManager.create_custom_classified_cmap(
            palette_spec["entries"]
        )
        # A classified palette is defined against DATA values, so walk
        # back through vmin/vmax before applying the norm — otherwise
        # the bands land at the wrong values whenever the encode range
        # differs from the palette's own bounds.
        values = np.asarray(ts) * (vmax - vmin) + vmin
        return np.rint(np.asarray(cmap(norm(values))) * 255.0).astype("uint8")

    cmap = ColormapManager.create_custom_cmap(
        base_cmap=palette_spec.get("base", "YlOrBr"),
        transparent_range=int(palette_spec.get("transparent_range", 1)),
        blend_range=int(palette_spec.get("blend_range", 8)),
        overall_alpha=float(palette_spec.get("overall_alpha", 1.0)),
    )
    return np.rint(np.asarray(cmap(np.asarray(ts))) * 255.0).astype("uint8")


def _transparent_range(palette_spec: dict | None) -> float | None:
    """The palette's no-data band as a fraction of the code range.

    ``transparent_range`` is expressed in colormap entries out of 256,
    which is also the client's luma resolution, so the conversion is a
    plain divide. Classified palettes have no equivalent — their
    transparency is per-band and already carried in the stops.
    """
    if not palette_spec or palette_spec.get("type") != "continuous":
        return None
    raw = palette_spec.get("transparent_range")
    if raw is None:
        return None
    value = float(raw) / 256.0
    return round(value, 6) if 0 < value < 1 else None
