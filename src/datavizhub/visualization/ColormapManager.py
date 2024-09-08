import matplotlib.pyplot as plt
from matplotlib.colors import BoundaryNorm, LinearSegmentedColormap, ListedColormap


class ColormapManager:
    """
    A class to manage colormaps in a plot.
    """

    def __init__(self):
        """
        Initialize the ColormapManager with default settings.
        """
        pass

    def create_custom_classified_cmap(colormap_data):
        """
        Creates a custom classified colormap and normalizer from the provided colormap data.

        Parameters:
        - colormap_data (list of dict): A list of dictionaries where each dictionary contains
                                        "Color" (RGBA values) and "Upper Bound" (upper boundary value).
        Example:
        colormap_data = [
            {"Label": 0.05, "Upper Bound": 5e-07, "Color": [255, 255, 229, 0]},
            {"Label": 0.1, "Upper Bound": 1e-06, "Color": [255, 250, 205, 51]},
            {"Label": 0.2, "Upper Bound": 2e-06, "Color": [254, 244, 181, 102]},
            {"Label": 0.5, "Upper Bound": 5e-06, "Color": [254, 232, 157, 153]},
            {"Label": 1.0, "Upper Bound": 1e-05, "Color": [254, 218, 126, 204]},
            {"Label": 2.0, "Upper Bound": 2e-05, "Color": [254, 200, 88, 240]},
            {"Label": 3.0, "Upper Bound": 3e-05, "Color": [254, 177, 62, 240]},
            {"Label": 4.0, "Upper Bound": 4e-05, "Color": [254, 153, 41, 240]},
            {"Label": 5.0, "Upper Bound": 5e-05, "Color": [243, 129, 29, 240]},
            {"Label": 7.5, "Upper Bound": 7.5e-05, "Color": [231, 106, 17, 240]},
            {"Label": 10.0, "Upper Bound": 0.0001, "Color": [213, 86, 7, 240]},
            {"Label": 20.0, "Upper Bound": 0.0002, "Color": [189, 69, 2, 240]},
            {"Label": 30.0, "Upper Bound": 0.0003, "Color": [131, 45, 4, 240]},
            {"Label": 40.0, "Upper Bound": 0.0004, "Color": [102, 37, 6, 240]},
        ]

        Returns:
        - cmap (ListedColormap): A matplotlib ListedColormap object.
        - norm (BoundaryNorm): A matplotlib BoundaryNorm object.
        """
        # Extract the colors and boundaries
        colors = [entry["Color"] for entry in colormap_data]  # Use RGBA values
        bounds = [entry["Upper Bound"] for entry in colormap_data]

        # Normalize the colors (from 0-255 range to 0-1 range)
        norm_colors = [[c / 255 for c in color] for color in colors]

        # Create the colormap and the normalizer
        cmap = ListedColormap(norm_colors, name='custom_colormap')
        norm = BoundaryNorm(bounds, len(bounds) - 1)  # Correctly set the number of boundaries

        return cmap, norm

    def create_custom_cmap(
        base_cmap="YlOrBr", transparent_range=1, blend_range=8, overall_alpha=1.0
    ):
        """
        Creates a custom colormap based on a base colormap, with specified transparency at the beginning,
        a blending range, and an optional overall transparency level.

        :param base_cmap: The name of the base colormap to use.
        :param transparent_range: The number of entries at the start of the colormap to make fully transparent.
        :param blend_range: The number of entries following the transparent range over which the transparency
                            should linearly increase to fully opaque.
        :param overall_alpha: The overall transparency level for the entire colormap (1.0 is fully opaque,
                              and 0.0 is fully transparent).
        :return: A custom LinearSegmentedColormap.
        """
        # Get the base colormap
        color_array = plt.get_cmap(base_cmap)(range(256))

        # Adjust the alpha values for the transparent and blend ranges
        color_array[:transparent_range, -1] = 0  # Fully transparent
        color_array[
            transparent_range : transparent_range + blend_range, -1
        ] = np.linspace(0.0, 1.0, blend_range)

        # Apply the overall transparency level to the entire colormap
        if overall_alpha < 1.0:
            # Scale alpha values to not exceed the overall_alpha value
            color_array[:, -1] = color_array[:, -1] * overall_alpha

        # Create and return the custom colormap
        custom_cmap = LinearSegmentedColormap.from_list(
            name="custom_cmap", colors=color_array
        )

        return custom_cmap
