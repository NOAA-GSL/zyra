# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import contextlib
from typing import Optional

try:  # Prefer standard library importlib.resources
    from importlib import resources as importlib_resources
except Exception:  # pragma: no cover - fallback for very old Python
    import importlib_resources  # type: ignore

from zyra.visualization.styles import DEFAULT_EXTENT, MAP_STYLES


def load_geotiff_array(input_path: str, *, band: int = 1):
    """Read one band of a GeoTIFF as float32 with nodata mapped to NaN.

    NaN renders transparent in the raster visualizers, so warp fill and
    masked regions disappear instead of plotting as a solid value.

    Parameters
    ----------
    input_path : str
        Path to a ``.tif``/``.tiff`` file.
    band : int, default 1
        1-based band index to read.

    Raises
    ------
    ValueError
        If rasterio is unavailable or ``band`` is out of range.
    """
    try:
        import rasterio
    except ImportError as exc:
        raise ValueError(
            "Reading GeoTIFF input requires rasterio; install it (e.g. "
            "'pip install rasterio' or the zyra processing extras)"
        ) from exc
    import numpy as np

    with rasterio.open(input_path) as ds:
        if band < 1 or band > ds.count:
            raise ValueError(
                f"--band {band} is out of range: file has {ds.count} band(s)"
            )
        arr = ds.read(band).astype("float32")
        nodata = ds.nodata
    if nodata is not None and not np.isnan(nodata):
        arr[arr == np.float32(nodata)] = np.nan
    return arr


def load_data_array(
    input_path: str,
    *,
    var: str | None = None,
    xarray_engine: str | None = None,
    band: int = 1,
):
    """Load a 2D array from a ``.nc``/``.nc4``, ``.npy``, or GeoTIFF file.

    Parameters
    ----------
    input_path : str
        Path to a NetCDF (``.nc``/``.nc4``), NumPy (``.npy``), or GeoTIFF
        (``.tif``/``.tiff``) file.
    var : str, optional
        Variable name to extract; required for NetCDF inputs.
    xarray_engine : str, optional
        Engine passed to :func:`xarray.open_dataset` (e.g., ``netcdf4``,
        ``h5netcdf``, ``scipy``).
    band : int, default 1
        Band to read for GeoTIFF inputs (nodata is mapped to NaN).

    Returns
    -------
    numpy.ndarray
        The loaded array.

    Raises
    ------
    ValueError
        If ``var`` is missing for NetCDF inputs, or the file type is
        unsupported.
    """
    lower = str(input_path).lower()
    if lower.endswith((".nc", ".nc4")):
        if not var:
            raise ValueError("--var is required when reading from NetCDF")
        import xarray as xr

        ds = (
            xr.open_dataset(input_path, engine=xarray_engine)
            if xarray_engine
            else xr.open_dataset(input_path)
        )
        try:
            return ds[var].values
        finally:
            ds.close()
    if lower.endswith(".npy"):
        import numpy as np

        return np.load(input_path)
    if lower.endswith((".tif", ".tiff")):
        return load_geotiff_array(input_path, band=band)
    raise ValueError("Unsupported input file; use .nc, .nc4, .npy, .tif, or .tiff")


def load_palette_spec(path: str) -> dict:
    """Load and validate a palette (``--cmap-file``).

    Accepts a local path, ``-`` (stdin), or an ``http(s)://`` / ``s3://``
    URL — the same forms every other zyra input takes, so a palette can
    be referenced as a shared, versioned asset instead of a file the
    caller has to stage locally first.

    Two shapes are accepted (see ColormapManager, which consumes them):

    - ``{"type": "classified", "entries": [{"Color": [R,G,B(,A)],
      "Upper Bound": n}, ...]}`` — fixed color bands.
    - ``{"type": "continuous", "base": "YlOrBr", "transparent_range": 2,
      "blend_range": 8, "overall_alpha": 0.9}`` — a named base colormap
      with an optional transparency ramp.

    Raises
    ------
    ValueError
        On unreadable files or URLs, invalid JSON, or a spec that fails
        validation. Handlers surface these as exit code 2.
    """
    import json

    from zyra.utils.io_utils import read_bytes_any

    try:
        # read_bytes_any raises RuntimeError for a missing path, an
        # unsupported scheme, and any fetch failure; the palette
        # contract is ValueError, which handlers map to exit 2.
        raw = read_bytes_any(path).decode("utf-8")
    except RuntimeError as exc:
        raise ValueError(f"Cannot read palette file {path}: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise ValueError(f"Palette file {path} is not UTF-8 text: {exc}") from exc
    try:
        spec = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Palette file {path} is not valid JSON: {exc}") from exc
    if not isinstance(spec, dict):
        raise ValueError("Palette file must contain a JSON object")

    ptype = spec.get("type")
    if ptype == "classified":
        entries = spec.get("entries")
        if not isinstance(entries, list) or len(entries) < 2:
            raise ValueError(
                "Classified palette requires at least 2 entries "
                "(N entries define N-1 color bins)"
            )
        bounds: list[float] = []
        for i, entry in enumerate(entries):
            if not isinstance(entry, dict) or "Color" not in entry:
                raise ValueError(f"Palette entry {i} must have a 'Color' key")
            color = entry["Color"]
            if (
                not isinstance(color, list)
                or len(color) not in (3, 4)
                or not all(isinstance(c, (int, float)) and 0 <= c <= 255 for c in color)
            ):
                raise ValueError(
                    f"Palette entry {i}: 'Color' must be [R,G,B] or [R,G,B,A] "
                    "with values in 0-255"
                )
            if "Upper Bound" not in entry:
                raise ValueError(f"Palette entry {i} must have an 'Upper Bound' key")
            try:
                bound = float(entry["Upper Bound"])
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"Palette entry {i}: 'Upper Bound' must be numeric"
                ) from exc
            # Store the coerced value so numeric strings ("10") reach
            # BoundaryNorm as numbers, not strings.
            entry["Upper Bound"] = bound
            bounds.append(bound)
        if any(b2 <= b1 for b1, b2 in zip(bounds, bounds[1:])):
            raise ValueError("Classified palette bounds must be strictly increasing")
        return spec

    if ptype == "continuous":
        base = spec.get("base")
        if not isinstance(base, str) or not base:
            raise ValueError("Continuous palette requires a 'base' colormap name")
        for key in ("transparent_range", "blend_range"):
            v = spec.get(key)
            if v is not None and (not isinstance(v, int) or v < 0):
                raise ValueError(f"Palette '{key}' must be a non-negative integer")
        alpha = spec.get("overall_alpha")
        if alpha is not None and (
            not isinstance(alpha, (int, float)) or not 0.0 <= float(alpha) <= 1.0
        ):
            raise ValueError("Palette 'overall_alpha' must be between 0 and 1")
        if spec.get("transparent_range", 1) + spec.get("blend_range", 8) > 256:
            raise ValueError(
                "Palette 'transparent_range' + 'blend_range' must not exceed "
                "256 (the colormap lookup table size)"
            )
        return spec

    raise ValueError("Palette 'type' must be 'classified' or 'continuous'")


def cmap_norm_from_palette(spec: dict):
    """Build ``(cmap, norm_or_None)`` from a validated palette spec.

    Classified specs return a ``(ListedColormap, BoundaryNorm)`` pair;
    continuous specs return ``(LinearSegmentedColormap, None)``.
    """
    from zyra.visualization.colormap_manager import ColormapManager

    cm = ColormapManager()
    if spec["type"] == "classified":
        cmap, norm = cm.render(spec["entries"])
        # Values below the first bound render transparent (radar-palette
        # semantics: below-scale is "no signal", not the first band —
        # otherwise no-echo floods the frame with the lowest band color).
        cmap.set_under((0.0, 0.0, 0.0, 0.0))
        return cmap, norm
    return (
        cm.render(
            spec["base"],
            transparent_range=spec.get("transparent_range", 1),
            blend_range=spec.get("blend_range", 8),
            overall_alpha=spec.get("overall_alpha", 1.0),
        ),
        None,
    )


def resolve_cmap_args(ns):
    """Resolve ``(cmap, norm)`` from the ``--cmap``/``--cmap-file`` flags.

    Returns the plain colormap name with no norm when no palette file is
    given. Classified palettes reject ``--vmin``/``--vmax`` — the bounds
    come from the palette table.
    """
    cmap_file = getattr(ns, "cmap_file", None)
    if not cmap_file:
        return getattr(ns, "cmap", None), None
    spec = load_palette_spec(cmap_file)
    if spec["type"] == "classified" and (
        getattr(ns, "vmin", None) is not None or getattr(ns, "vmax", None) is not None
    ):
        raise ValueError(
            "--vmin/--vmax are not valid with a classified palette; "
            "bounds come from the palette table"
        )
    return cmap_norm_from_palette(spec)


def write_legend(
    output_path: str,
    *,
    cmap,
    norm=None,
    vmin=None,
    vmax=None,
    label: str | None = None,
    orientation: str = "horizontal",
) -> str:
    """Write a standalone colorbar legend image (``--legend-file``).

    Renders only the colorbar (transparent background) so globe/sphere
    display targets can place it as screen-space UI instead of baking it
    into the frame, where it would wrap onto the globe.

    Raises
    ------
    ValueError
        If neither a norm nor both ``vmin``/``vmax`` are given — the
        legend must reflect the scale actually used for the render, and
        a data-derived auto-scale is not visible here.
    """
    if norm is None and (vmin is None or vmax is None):
        raise ValueError(
            "--legend-file requires --vmin and --vmax (or a classified "
            "--cmap-file) so the legend matches the rendered scale"
        )
    import sys

    if "matplotlib.pyplot" not in sys.modules:
        # Backend selection must happen before pyplot is imported; when a
        # render already imported it (CLI path), leave the backend alone.
        import matplotlib

        matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import cm as mpl_cm
    from matplotlib import colors as mpl_colors

    if norm is None:
        norm = mpl_colors.Normalize(vmin=float(vmin), vmax=float(vmax))
    figsize = (8, 1.1) if orientation == "horizontal" else (1.4, 8)
    fig, ax = plt.subplots(figsize=figsize, dpi=128)
    cbar = fig.colorbar(
        mpl_cm.ScalarMappable(norm=norm, cmap=cmap), cax=ax, orientation=orientation
    )
    if label:
        cbar.set_label(label)
    fig.savefig(output_path, bbox_inches="tight", transparent=True)
    plt.close(fig)
    return output_path


def resolve_extent(ns) -> list[float]:
    """Validate and default the ``--extent`` value on a parsed namespace.

    The extent flags are declared with ``action="extend"``/``nargs="+"``
    so both the CLI spelling (``--extent w e s n``) and the Domain API's
    repeated-flag expansion (``--extent w --extent e ...``) accumulate
    into one list; the parser can no longer enforce the length, so it is
    validated here. Returns the full-globe default
    (``styles.DEFAULT_EXTENT``) when unset.

    Exits with code 2 (message on stderr via logging) on a wrong-length
    value. The numeric exit code keeps the failure a clean exit-status
    signal rather than relying on the Domain API executor's message-string
    handling.
    """
    extent = getattr(ns, "extent", None)
    if extent is None:
        return list(DEFAULT_EXTENT)
    if len(extent) != 4:
        import logging

        logging.error("--extent takes exactly 4 values: west east south north")
        raise SystemExit(2)
    return [float(v) for v in extent]


def features_from_ns(ns) -> list[str] | None:
    """Build a features list from argparse namespace flags.

    Honors ``--features`` (CSV) and negation flags ``--no-coastline``,
    ``--no-borders``, and ``--no-gridlines``. Falls back to
    ``MAP_STYLES["features"]`` when not explicitly provided.
    """
    features = None
    if getattr(ns, "features", None):
        features = [f.strip() for f in (ns.features.split(",")) if f.strip()]
    else:
        features = list(MAP_STYLES.get("features", []) or [])
    if getattr(ns, "no_coastline", False) and "coastline" in features:
        features = [f for f in features if f != "coastline"]
    if getattr(ns, "no_borders", False) and "borders" in features:
        features = [f for f in features if f != "borders"]
    if getattr(ns, "no_gridlines", False) and "gridlines" in features:
        features = [f for f in features if f != "gridlines"]
    return features


def resolve_basemap_ref(
    ref: Optional[str],
) -> tuple[str | None, contextlib.ExitStack | None]:
    """Resolve a basemap reference to a filesystem path.

    Supports three forms:
      - Absolute/relative filesystem path (returned unchanged)
      - Bare filename under packaged assets/images (e.g., "earth_vegetation.jpg")
      - Packaged reference using ``pkg:`` scheme:
        - ``pkg:package/resource`` or ``pkg:package:resource``

    Returns a tuple of (path, guard). If a temporary path context is used, a
    contextlib.ExitStack is returned and must be kept alive until the path is
    no longer needed. Call ``guard.close()" when finished.
    """
    if not ref:
        return None, None
    s = str(ref).strip()
    # pkg: resolver
    if s.startswith("pkg:"):
        es = contextlib.ExitStack()
        try:
            spec = s[4:]
            if ":" in spec and "/" not in spec:
                pkg, res = spec.split(":", 1)
            else:
                parts = spec.split("/", 1)
                pkg = parts[0]
                res = parts[1] if len(parts) > 1 else ""
            if not res:
                es.close()
                return None, None
            path = importlib_resources.files(pkg).joinpath(res)
            p = es.enter_context(importlib_resources.as_file(path))
            return str(p), es
        except Exception:
            es.close()
            return None, None
    # Bare filename under packaged assets/images
    if "/" not in s and "\\" not in s:
        try:
            res = (
                importlib_resources.files("zyra.assets").joinpath("images").joinpath(s)
            )
            if getattr(res, "is_file", None) and res.is_file():  # type: ignore[attr-defined]
                es = contextlib.ExitStack()
                p = es.enter_context(importlib_resources.as_file(res))
                return str(p), es
        except Exception:
            pass
    # Relative resource path under packaged assets (e.g., 'images/earth_vegetation.jpg')
    if s.startswith("images/"):
        try:
            res = importlib_resources.files("zyra.assets").joinpath(s)
            if getattr(res, "is_file", None) and res.is_file():  # type: ignore[attr-defined]
                es = contextlib.ExitStack()
                p = es.enter_context(importlib_resources.as_file(res))
                return str(p), es
        except Exception:
            pass
    # Fallback: treat as filesystem path
    return s, None
