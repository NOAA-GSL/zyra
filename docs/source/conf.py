import os
import sys
from datetime import datetime

# -- Path setup --------------------------------------------------------------

ROOT = os.path.abspath(os.path.join(__file__, "..", "..", ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

# -- Project information -----------------------------------------------------

project = "DataVizHub"
author = "NOAA-GSL"
copyright = f"{datetime.now():%Y}, {author}"

# -- General configuration ---------------------------------------------------

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# Napoleon settings for NumPy-style docstrings
napoleon_google_docstring = False
napoleon_numpy_docstring = True
napoleon_include_init_with_doc = True
napoleon_include_private_with_doc = False
napoleon_include_special_with_doc = False
napoleon_use_admonition_for_examples = False
napoleon_use_admonition_for_notes = False
napoleon_use_admonition_for_references = False
napoleon_use_ivar = False
napoleon_use_param = True
napoleon_use_rtype = True

# -- Options for HTML output -------------------------------------------------

html_theme = "alabaster"
html_static_path = ["_static"]

# Mock optional heavy dependencies to allow building API docs without extras
autodoc_mock_imports = [
    "boto3",
    "botocore",
    "vimeo",
    "requests",
    "cartopy",
    "matplotlib",
    "numpy",
    "pygrib",
    "siphon",
    "scipy",
    "netcdf4",
    "xarray",
    "ffmpeg",
    "ffmpeg_python",
    "ffmpeg-python",
]
