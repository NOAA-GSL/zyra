"""Packaged image resources (basemaps, overlays, examples).

Contains image files used by visualization utilities and sample pipelines,
including global basemaps and overlays. Access these resources via
``importlib.resources`` to avoid hard-coded filesystem paths.

Examples
--------
Obtain a path-like object to a packaged image::

    from importlib.resources import files, as_file

    resource = files("zyra.assets").joinpath("images/earth_vegetation.jpg")
    with as_file(resource) as p:
        path = str(p)
"""
