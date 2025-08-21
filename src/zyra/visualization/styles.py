"""Centralized visualization styles and defaults.

These values are intentionally conservative and can be overridden via
Renderer.configure or function parameters.
"""

from __future__ import annotations

DEFAULT_EXTENT: list[float] = [-180.0, 180.0, -90.0, 90.0]
DEFAULT_CMAP: str = "YlOrBr"
FIGURE_DPI: int = 96


MAP_STYLES: dict[str, object] = {
    "border_color": "#333333CC",
    "coastline_color": "#333333CC",
    "linewidth": 1.0,
    "features": ["coastline", "borders"],
}

FONT_SIZES: dict[str, int] = {
    "title": 12,
    "labels": 10,
}


def apply_matplotlib_style():
    """Apply minimal Matplotlib rcParams for consistent styling.

    Safe to call multiple times. Only sets a handful of parameters to avoid
    surprising downstream consumers.
    """
    try:
        import matplotlib as mpl

        mpl.rcParams.update(
            {
                "font.size": FONT_SIZES["labels"],
                "axes.titlesize": FONT_SIZES["title"],
                "figure.dpi": FIGURE_DPI,
            }
        )
    except Exception:
        # Matplotlib not available or running headless without MPL installed.
        pass


def timestamp_anchor(loc: str):
    """Map a location keyword to axes-relative position and alignment.

    Returns (x, y, ha, va).
    """
    loc = (loc or "").lower().strip()
    mapping = {
        "upper_left": (0.01, 0.98, "left", "top"),
        "upper_right": (0.99, 0.98, "right", "top"),
        "lower_left": (0.01, 0.02, "left", "bottom"),
        "lower_right": (0.99, 0.02, "right", "bottom"),
    }
    return mapping.get(loc, mapping["lower_right"])  # default lower-right
