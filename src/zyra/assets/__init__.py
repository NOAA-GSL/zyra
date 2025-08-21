"""Static assets for Zyra (images, templates, styles, and more).

Provides a central, importable location for all non-code resources used by
Zyra. Assets are packaged with the library so they can be discovered
consistently at runtime across environments (sdist/wheel, editable installs,
and CI).

Examples
--------
Access an image file using :mod:`importlib.resources`::

    from importlib.resources import files, as_file

    resource = files("zyra.assets").joinpath("images/earth_vegetation.jpg")
    with as_file(resource) as p:
        path = str(p)  # pass to libraries that require a filesystem path
"""
