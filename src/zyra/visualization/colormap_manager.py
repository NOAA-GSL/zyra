"""Colormap utilities for classified and continuous rendering.

This module exposes :class:`ColormapManager`, a lightweight renderer that
produces colormap objects (e.g., :class:`matplotlib.colors.ListedColormap`,
and a matching :class:`matplotlib.colors.BoundaryNorm` for classified data).
"""

from zyra.visualization.base import Renderer


class ColormapManager(Renderer):
    """Produce colormaps for use in plots.

    Visualization Type
    ------------------
    - Classified colormap from a list of color/boundary entries.
    - Continuous colormap with transparency ramp and optional overall alpha.

    Examples
    --------
    Create a classified colormap and norm::

        from zyra.visualization.colormap_manager import ColormapManager

        cm = ColormapManager()
        data = [
            {"Color": [255, 255, 229, 0], "Upper Bound": 5e-07},
            {"Color": [255, 250, 205, 51], "Upper Bound": 1e-06},
        ]
        cmap, norm = cm.render(data)  # returns (cmap, norm)

    Create a continuous colormap::

        cmap = cm.render(
            "YlOrBr", transparent_range=2, blend_range=8, overall_alpha=0.8
        )
    """

    def __init__(self):
        self._last = None

    # Renderer API
    def configure(self, **kwargs):  # no-op for now
        return None

    def render(self, data, **kwargs):
        """Render a colormap from classified or continuous specifications.

        Parameters
        ----------
        data : list or str
            - If ``list`` of dict entries with keys "Color" and "Upper Bound",
              a classified colormap and norm are returned.
            - If ``str``, treat as a base cmap name and return a continuous
              colormap customized by kwargs.
        transparent_range : int, optional
            Number of entries at the start to set fully transparent (continuous).
        blend_range : int, optional
            Number of entries over which alpha ramps to fully opaque (continuous).
        overall_alpha : float, optional
            Overall transparency multiplier for the colormap (continuous).

        Returns
        -------
        tuple or matplotlib.colors.LinearSegmentedColormap
            ``(cmap, norm)`` for classified, or a continuous colormap.
        """
        # Lazy imports

        if isinstance(data, list):
            cmap, norm = self.create_custom_classified_cmap(data)
            self._last = (cmap, norm)
            return self._last
        else:
            base_cmap = str(data) if data else "YlOrBr"
            transparent_range = kwargs.get("transparent_range", 1)
            blend_range = kwargs.get("blend_range", 8)
            overall_alpha = kwargs.get("overall_alpha", 1.0)
            cmap = self.create_custom_cmap(
                base_cmap=base_cmap,
                transparent_range=transparent_range,
                blend_range=blend_range,
                overall_alpha=overall_alpha,
            )
            self._last = cmap
            return cmap

    def save(self, output_path=None):  # not applicable
        return None

    # Original helpers
    @staticmethod
    def create_custom_classified_cmap(colormap_data):
        """Create a classified colormap and normalizer from colormap data.

        Parameters
        ----------
        colormap_data : list of dict
            Each entry contains a "Color" RGBA list (0–255) and an "Upper Bound".

        Returns
        -------
        (ListedColormap, BoundaryNorm)
            The classified colormap and its corresponding normalizer.
        """
        # Lazy imports
        from matplotlib.colors import BoundaryNorm, ListedColormap

        colors = [entry["Color"] for entry in colormap_data]
        bounds = [entry["Upper Bound"] for entry in colormap_data]
        norm_colors = [[c / 255 for c in color] for color in colors]
        cmap = ListedColormap(norm_colors, name="custom_colormap")
        norm = BoundaryNorm(bounds, len(bounds) - 1)
        return cmap, norm

    @staticmethod
    def create_custom_cmap(
        base_cmap="YlOrBr", transparent_range=1, blend_range=8, overall_alpha=1.0
    ):
        """Create a continuous colormap with transparency ramp and overall alpha.

        Parameters
        ----------
        base_cmap : str
            Name of the base colormap.
        transparent_range : int
            Number of entries to set fully transparent at the start.
        blend_range : int
            Number of entries over which alpha ramps to fully opaque.
        overall_alpha : float
            Overall transparency multiplier (0.0–1.0).

        Returns
        -------
        matplotlib.colors.LinearSegmentedColormap
            The customized continuous colormap.
        """
        # Lazy imports
        import matplotlib.pyplot as plt
        import numpy as np
        from matplotlib.colors import LinearSegmentedColormap

        color_array = plt.get_cmap(base_cmap)(range(256))
        color_array[:transparent_range, -1] = 0
        color_array[
            transparent_range : transparent_range + blend_range, -1
        ] = np.linspace(0.0, 1.0, blend_range)
        if overall_alpha < 1.0:
            color_array[:, -1] = color_array[:, -1] * overall_alpha
        custom_cmap = LinearSegmentedColormap.from_list(
            name="custom_cmap", colors=color_array
        )
        return custom_cmap
