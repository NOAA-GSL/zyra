from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional


class Renderer(ABC):
    """Abstract base for visualization components in the Zyra pipeline.

    A renderer is the visualization stage that takes processed data from the
    processing layer and produces a visual artifact (e.g., a figure, image, or
    colormap). This base class standardizes three phases:

    - ``configure(**kwargs)``: set renderer options/resources
    - ``render(data, **kwargs)``: draw or produce a visual artifact from data
    - ``save(output_path=None)``: persist the rendered artifact

    Parameters
    ----------
    ...
        Concrete renderers define their own constructor parameters (e.g.,
        basemap, overlays, figure size, or colormap options).

    Examples
    --------
    Typical usage pattern::

        from zyra.visualization.plot_manager import PlotManager

        renderer = PlotManager(basemap="/path/to/basemap.jpg")
        renderer.configure(image_extent=[-180, 180, -90, 90])
        fig = renderer.render(data_array)
        renderer.save("./output.png")
    """

    @abstractmethod
    def configure(self, **kwargs: Any) -> None:
        """Configure renderer options.

        Parameters
        ----------
        **kwargs : Any
            Implementation-specific options (e.g., colormap, size, resources).
        """

    @abstractmethod
    def render(self, data: Any, **kwargs: Any) -> Any:
        """Render the given data.

        Parameters
        ----------
        data : Any
            Input data for rendering (e.g., 2D array, colormap spec).
        **kwargs : Any
            Implementation-specific options that influence rendering.

        Returns
        -------
        Any
            A rendered artifact (e.g., Matplotlib figure, colormap objects).
        """

    @abstractmethod
    def save(self, output_path: Optional[str] = None) -> Optional[str]:
        """Save the rendered artifact to a path and return the path if written.

        Parameters
        ----------
        output_path : str, optional
            Destination file path. If omitted, implementations may choose a
            default path or skip saving.

        Returns
        -------
        str or None
            The output path on success, or ``None`` if nothing was written.
        """
